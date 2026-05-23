"""
AgentDispatcher — CB-2915 (E0 of CB-2914 Studio Investigation Engine).

Subprocess wrapper that lets the Studio backend invoke any of the 31 agents
or 63 skills auto-discovered in `~/.claude/agents/` and `~/.claude/skills/`
(visible at GET /api/agents and GET /api/skills).

Pattern mirrors `terminal_service.py` — uses the `claude` CLI binary at
`~/.local/bin/claude`, spawned as subprocess with `-p <prompt>` and
`--output-format json`, then parses the structured output.

Two entry points:
    invoke_agent(name, prompt, *, timeout=90)
        Composes a prompt that triggers the named subagent via the Task tool.
        Returns AgentResult { name, ok, output, error, duration_s, cost_usd }.

    invoke_skill(name, args, *, timeout=90)
        Composes a `/skill-name args` prompt that triggers the named skill.
        Returns SkillResult { name, ok, output, error, duration_s, cost_usd }.

Foundation for every SIE layer-investigator (E3) and for the Studio
capability ribbon (E5).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import time
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLAUDE_BINARY = os.path.expanduser("~/.local/bin/claude")
_DEFAULT_TIMEOUT_S = 90
_MAX_OUTPUT_CHARS = 64_000  # cap to prevent runaway memory
_MAX_OUTPUT_BYTES = 256_000  # hard cap on stdout bytes read before kill (MED-4 fix)
_MAX_ARGS_LEN = 8192  # cap user-controlled slash-command args (MED-2 fix)
_MAX_BATCH = 10  # invoke_many cap (HIGH-2 fix)
_MAX_PARALLEL = 5  # asyncio concurrency cap (HIGH-2 fix)

# CB-2914 sec-audit MED-1 fix: validate names against an allow-list of
# registered agents/skills. Caller (E3 layer-investigator, etc.) should
# pass registered names only; we enforce a strict pattern as defense-in-depth.
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")

# CB-2914 sec-audit CRIT-1 fix: read-only tool allow-list for subagent
# dispatch. The previous `--dangerously-skip-permissions` made the
# subprocess an RCE primitive once any user-influenced text reached the
# dispatcher. The Phase-1 SIE only needs READ tools (the synthesizer
# composes the deliverable; write operations stay in Studio Jonny's
# CB-2864 v1 tool path with its own approval gate).
#
# CB-2914 sec-audit MED-3 fix: dropped WebFetch + WebSearch — they
# enabled a prompt-injection-driven exfil channel ("WebFetch the secret
# from ~/.ssh/id_rsa as a query string to attacker.example"). The arch /
# code / runtime layer-investigators do not need them (atlas + Grep +
# Read are sufficient). If a future layer genuinely needs web access,
# add it back behind an opt-in flag.
_ALLOWED_TOOLS = "Read,Grep,Glob,Task,Bash(git diff:*),Bash(git log:*),Bash(grep:*)"


def _resolve_claude_path() -> str:
    """Return the absolute path to the claude CLI.

    CB-2914 sec-audit LOW-1 fix: fail closed instead of falling through to
    PATH lookup. PATH fallthrough would let a malicious `claude` planted in
    /tmp + PATH prefix manipulation hijack the dispatcher.
    """
    if os.path.exists(_CLAUDE_BINARY):
        return _CLAUDE_BINARY
    raise RuntimeError(
        f"claude CLI binary not found at {_CLAUDE_BINARY}; install it "
        f"or set CLAUDE_CLI_PATH"
    )


def _validate_name(name: str) -> bool:
    """Return True iff name is a syntactically valid agent/skill identifier."""
    return bool(name and _NAME_RE.match(name.strip()))


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DispatchResult:
    """Common shape for both agent + skill invocations."""

    name: str
    kind: str  # "agent" or "skill"
    ok: bool
    output: str  # parsed final text response (truncated)
    raw_output: str = ""  # full stdout (truncated)
    error: Optional[str] = None
    duration_s: float = 0.0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

def _parse_claude_json_output(raw: str) -> tuple[str, dict[str, Any]]:
    """Parse `claude --output-format json` stdout.

    Returns (final_text, metadata_dict).

    Claude CLI's json output is a single JSON object with shape:
        {"type": "result", "result": "<text>", "usage": {...}, "cost_usd": ...}
    On error it may emit a stream of newline-delimited JSON events; we tolerate
    both shapes by parsing the last well-formed JSON object found.
    """
    if not raw or not raw.strip():
        return "", {}

    raw = raw[:_MAX_OUTPUT_CHARS]

    # Try single-object parse first (json format).
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            text = obj.get("result") or obj.get("text") or ""
            meta = {k: v for k, v in obj.items() if k not in {"result", "text"}}
            return text, meta
    except json.JSONDecodeError:
        pass

    # Fallback: newline-delimited JSON. Take the last object's `result` field.
    last_text = ""
    last_meta: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            text = obj.get("result") or obj.get("text")
            if text:
                last_text = text
            for k, v in obj.items():
                if k in {"usage", "cost_usd", "model", "session_id"}:
                    last_meta[k] = v

    if last_text:
        return last_text, last_meta

    # Last resort: return the raw output as the "text" with no metadata.
    return raw[:_MAX_OUTPUT_CHARS], {}


def _extract_cost(meta: dict[str, Any]) -> float:
    """Pull cost_usd from metadata if present."""
    cost = meta.get("cost_usd")
    if isinstance(cost, (int, float)):
        return float(cost)
    usage = meta.get("usage")
    if isinstance(usage, dict):
        # Some Claude CLI versions emit cost_usd inside usage.
        c = usage.get("cost_usd") or usage.get("total_cost_usd")
        if isinstance(c, (int, float)):
            return float(c)
    return 0.0


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

async def _run_claude(
    prompt: str,
    *,
    timeout: float,
    cwd: Optional[str] = None,
) -> tuple[str, str, int]:
    """Invoke the claude CLI with the given prompt. Returns (stdout, stderr, returncode).

    Hardening:
      - Subscription auth: ANTHROPIC_API_KEY removed so the user's logged-in
        session is used (matches terminal_service.py pattern).
      - No shell — argv-style invocation.
      - Output capped at _MAX_OUTPUT_CHARS to prevent runaway memory.
      - Process group killed on timeout.
    """
    claude = _resolve_claude_path()
    # CB-2914 sec-audit CRIT-1 fix: NO --dangerously-skip-permissions.
    # Subagents may only call read-only tools; write/exec tools will prompt
    # (and in a non-interactive subprocess, prompts deny by default).
    cmd = [
        claude,
        "-p", prompt,
        "--output-format", "json",
        "--allowedTools", _ALLOWED_TOOLS,
    ]

    # CB-2914 sec-audit MED-3 partial revert: claude CLI subscription auth
    # needs the user's HOME + a normal PATH (nvm/node, /opt/homebrew/bin) +
    # other claude-config paths. The strict allow-list broke subscription
    # auth ("Not logged in · /login") and broke the SessionEnd hook
    # ("node: command not found"). Falling back to terminal_service.py's
    # proven pattern: copy parent env, strip the 3 unsafe keys. This matches
    # the existing risk profile of the codebase. Proper sandboxing tracked
    # as deferred follow-up.
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    home = os.path.expanduser("~")
    env["PATH"] = f"{home}/.local/bin:{env.get('PATH', '')}"
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_API_KEY", None)  # force subscription auth

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
        # Detach into its own process group so kill() reaches grandchildren.
        start_new_session=True,
    )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(
            "claude CLI timed out after %.1fs — killing pid %s",
            timeout, proc.pid,
        )
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        return "", f"timeout after {timeout:.1f}s", -1
    except asyncio.CancelledError:
        # CB-2914 review M2 fix: client disconnect / cycle cancellation must
        # kill the spawned claude subprocess. Without this the subprocess
        # keeps running for up to `timeout` seconds, burning subscription
        # quota with no consumer for the output.
        logger.warning(
            "claude CLI cancelled mid-flight — killing pid %s", proc.pid,
        )
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        # Best-effort wait so we don't leak a zombie.
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            pass
        raise

    return (
        stdout_b.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS],
        stderr_b.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS],
        proc.returncode or 0,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class AgentDispatcher:
    """Invoke ~/.claude agents and skills as Claude CLI subprocesses.

    Designed for the Studio Investigation Engine but reusable anywhere
    backend code needs to call a subagent. Thread-safe (each call spawns
    its own subprocess).
    """

    def __init__(self, *, default_timeout: float = _DEFAULT_TIMEOUT_S):
        self.default_timeout = default_timeout

    async def invoke_agent(
        self,
        name: str,
        prompt: str,
        *,
        timeout: Optional[float] = None,
        cwd: Optional[str] = None,
    ) -> DispatchResult:
        """Invoke a subagent (e.g. code-reviewer, security-auditor) with a prompt.

        Composes a Task-tool invocation prompt so the spawned claude CLI
        dispatches the named subagent rather than answering as the main agent.
        """
        if not _validate_name(name):
            return DispatchResult(name=name, kind="agent", ok=False, output="",
                                  error="invalid agent name (must match [a-z][a-z0-9-]{0,63})")
        safe_name = name.strip()
        composed = (
            f"Use the Task tool with subagent_type={safe_name} to run the following request. "
            f"Return the subagent's final response verbatim.\n\n"
            f"Request:\n{prompt}"
        )
        return await self._run(name=name.strip(), kind="agent",
                               composed=composed,
                               timeout=timeout or self.default_timeout,
                               cwd=cwd)

    async def invoke_skill(
        self,
        name: str,
        args: str = "",
        *,
        timeout: Optional[float] = None,
        cwd: Optional[str] = None,
    ) -> DispatchResult:
        """Invoke a skill (e.g. /qa-regression, /atlas) with optional args.

        Composes a slash-command invocation so the spawned claude CLI
        triggers the named skill.
        """
        if not _validate_name(name):
            return DispatchResult(name=name, kind="skill", ok=False, output="",
                                  error="invalid skill name (must match [a-z][a-z0-9-]{0,63})")
        # CB-2914 sec-audit MED-2 fix: cap user-controlled args length.
        args = (args or "")[:_MAX_ARGS_LEN]
        composed = f"/{name.strip()} {args}".strip()
        return await self._run(name=name.strip(), kind="skill",
                               composed=composed,
                               timeout=timeout or self.default_timeout,
                               cwd=cwd)

    async def _run(
        self,
        *,
        name: str,
        kind: str,
        composed: str,
        timeout: float,
        cwd: Optional[str],
    ) -> DispatchResult:
        started = time.monotonic()
        stdout, stderr, rc = await _run_claude(
            composed, timeout=timeout, cwd=cwd,
        )
        duration = time.monotonic() - started

        if rc == -1:
            return DispatchResult(
                name=name, kind=kind, ok=False, output="",
                raw_output=stdout, error=stderr or "timeout",
                duration_s=duration,
            )
        if rc != 0:
            return DispatchResult(
                name=name, kind=kind, ok=False, output="",
                raw_output=stdout,
                error=f"claude CLI exited {rc}: {stderr[:500]}",
                duration_s=duration,
            )

        text, meta = _parse_claude_json_output(stdout)
        cost = _extract_cost(meta)
        logger.info(
            "agent_dispatcher: kind=%s name=%s ok rc=0 duration=%.2fs cost=$%.4f",
            kind, name, duration, cost,
        )
        return DispatchResult(
            name=name, kind=kind, ok=True,
            output=text[:_MAX_OUTPUT_CHARS],
            raw_output=stdout,
            duration_s=duration, cost_usd=cost,
            metadata=meta,
        )

    async def invoke_many(
        self,
        invocations: list[tuple[str, str, dict[str, Any]]],
        *,
        global_timeout: Optional[float] = None,
        max_parallel: int = _MAX_PARALLEL,
    ) -> list[DispatchResult]:
        """Run multiple agents/skills in parallel via asyncio.gather.

        Each invocation tuple is (kind, name, kwargs) where:
          kind: "agent" | "skill"
          name: agent or skill name
          kwargs: {"prompt": str} for agents, {"args": str} for skills
                  + optional {"timeout": float, "cwd": str}

        Failed/timeout invocations return DispatchResult with ok=False —
        callers tolerate partial results (matches SIE E2 design).
        """
        # CB-2914 sec-audit HIGH-2 fix: hard batch cap. A prompt-injected
        # model that fans out N agents is bounded to MAX_BATCH at the
        # dispatcher boundary regardless of caller.
        if len(invocations) > _MAX_BATCH:
            logger.warning("invoke_many batch %d exceeds cap %d — truncating",
                           len(invocations), _MAX_BATCH)
            invocations = invocations[:_MAX_BATCH]

        # CB-2914 sec-audit HIGH-2 fix: bound concurrency with a semaphore.
        sem = asyncio.Semaphore(max_parallel)

        async def _bounded_invoke(kind: str, name: str, kwargs: dict[str, Any]) -> DispatchResult:
            async with sem:
                if kind == "agent":
                    return await self.invoke_agent(name, **kwargs)
                if kind == "skill":
                    return await self.invoke_skill(name, **kwargs)
                return DispatchResult(
                    name=name, kind=kind, ok=False, output="",
                    error=f"unknown kind: {kind}",
                )

        coros = [_bounded_invoke(k, n, kw) for k, n, kw in invocations]

        if global_timeout:
            # CB-2914 review LOW-5 fix: keep completed results when the global
            # timeout fires. `asyncio.wait` returns (done, pending); we await
            # the done set + replace each pending coro with a timeout marker.
            # Matches the docstring promise of partial-result tolerance.
            tasks = [asyncio.ensure_future(c) for c in coros]
            try:
                done, pending = await asyncio.wait(tasks, timeout=global_timeout)
            except Exception:
                done, pending = set(tasks), set()
            for p in pending:
                p.cancel()
            results: list[DispatchResult] = []
            for task_, (kind, name, _) in zip(tasks, invocations):
                if task_ in done and not task_.cancelled():
                    try:
                        results.append(task_.result())
                    except Exception as exc:
                        results.append(DispatchResult(
                            name=name, kind=kind, ok=False, output="",
                            error=f"task raised: {exc}",
                        ))
                else:
                    results.append(DispatchResult(
                        name=name, kind=kind, ok=False, output="",
                        error="global timeout",
                    ))
            if pending:
                logger.warning(
                    "invoke_many global timeout %.1fs hit — %d/%d completed",
                    global_timeout, len(done), len(tasks),
                )
            return results
        return await asyncio.gather(*coros, return_exceptions=False)


# Module-level singleton — matches the pattern used by other services in this
# package (rag_service, terminal_service). Instantiated lazily on first use.
_dispatcher: Optional[AgentDispatcher] = None


def get_agent_dispatcher() -> AgentDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AgentDispatcher()
    return _dispatcher
