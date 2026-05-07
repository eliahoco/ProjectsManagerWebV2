"""
Park "AI Execution Cost Optimization — Token Burn Mitigation" as a single
top-level FEATURE in CodeBoard with BACKLOG status + parked-future label.

Per Eli's instruction (2026-05-07): the full plan is approved as a future
work item but not now. The detailed 8-epic / ~28-story / ~80-task plan
lives in `docs/plans/2026-05-07-ai-execution-cost-optimization.md`.
When the new "Feature Backlog Board" feature ships, this entry will be
promoted to that board.

Per Bible Rule 27 — durable plan stays in docs/plans/, not /tmp/.
Per Bible Rule 29 — this script lives in backend/scripts/codeboard/, not /tmp/.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
PLAN_PATH = "docs/plans/2026-05-07-ai-execution-cost-optimization.md"
LABEL = "parked-future,ai-cost-optimization"

DESCRIPTION = """## Status: PARKED — future work

Eli requested this feature be parked for later (2026-05-07). The full
plan with 8 EPICs, ~28 STORIEs, ~80 TASKs, architecture diagrams,
risk register, KPI targets, and phased rollout is documented in:

**`docs/plans/2026-05-07-ai-execution-cost-optimization.md`**

## Why parked

Working on two new precursor features first:
1. Feature Studio (chat-based feature planning interface)
2. Feature Backlog Board (pre-CodeBoard staging area with priority + scheduler)

Once the Feature Backlog Board ships, this entry will be promoted to
that board where it belongs.

## TL;DR — what this feature solves

PMv2 AI execution from CodeBoard burns ~240× the tokens of a normal
Claude session per fire. One bug consumed 11% of the weekly Anthropic
quota. Six smoking guns identified:

1. `alwaysThinkingEnabled: true` in user settings (3-10× per turn)
2. Default model = Opus, no `--model` flag in `terminal_service.py` (5×)
3. Cache wipe on every feature switch (2-3×)
4. Mandatory 4-gate audit per Rule 18 (4×)
5. Claude Code 2.1.131 vs required 2.0.76 (possible 2× dup tool_use)
6. Zero token telemetry — blind to runaway

Plan delivers:
- Emergency cuts (E1) — 70% reduction in 1-2 hours
- Telemetry (E2) — V3 F-4 Metrics Collector slice
- Cache preservation (E3)
- Smart conditional audit gating (E4)
- Model tiering Haiku/Sonnet/Opus (E5)
- Cost dashboard UI (E6)
- Audits + tests + Chrome QA (E7)
- Rollout + soak + flag wrap (E8)

Target: 80-90% cost reduction. $5-15/fire → $0.20-2.00/fire.

## When to unpark

- After Feature Backlog Board ships and this can be tracked there
- OR if PMv2 AI cost burn becomes critical again
- OR after the two precursor features close (Feature Studio + Feature Backlog)

## Related markdown sources

- `docs/plans/2026-05-07-ai-execution-cost-optimization.md` — full plan
- `V3_AGENT_ARCHITECTURE.md:1156-1280` — F-2 Performance Monitor + F-4 Metrics Collector spec (this feature inherits from it)

## Linked

Inherits from V3 multi-agent plan (V3_AGENT_ARCHITECTURE.md). Touches
`backend/services/terminal_service.py`, `~/.claude/settings.json`,
`AutoPilotEvent`, future `ExecutionTokens` table.
"""


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} on {method} {path}: {body_txt[:500]}")
        raise


def main() -> None:
    body = {
        "title": "AI Execution Cost Optimization — Token Burn Mitigation",
        "description": DESCRIPTION,
        "type": "FEATURE",
        "priority": "HIGH",
        "reporter": "AI",
        "labels": LABEL,
        "status": "BACKLOG",
    }
    print(f"Creating parked FEATURE in project {PROJECT_ID} ...")
    result = http("POST", f"/projects/{PROJECT_ID}/issues", body)
    key = result.get("key")
    iid = result.get("id")
    print(f"OK — created {key} (id={iid})")
    print(f"Status: {result.get('status')} | Priority: {result.get('priority')} | Labels: {result.get('labels')}")
    print(f"Description points to: {PLAN_PATH}")


if __name__ == "__main__":
    main()
