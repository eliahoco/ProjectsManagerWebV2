"""
Verification Service - Chrome MCP verification runner for pipeline stages.

Architecture:
  The verification service does NOT call Chrome MCP tools directly. Instead it
  generates structured prompts that Claude Code executes using its Chrome MCP
  (or Playwright MCP) toolset.  The pipeline executor spawns a Claude Code
  session with the verification prompt, collects the output, and hands it back
  here for parsing.

Flow:
  1. Pipeline executor finishes an IMPLEMENT stage
  2. Calls verification_service.get_verification_rules(issue_type) to get the
     checks to run
  3. Calls verification_service.build_verification_prompt(...) to create the
     prompt that Claude Code will execute
  4. Spawns a Claude Code session with that prompt (via terminal_service)
  5. Claude Code uses Chrome MCP tools to navigate, screenshot, read console
  6. Calls verification_service.parse_verification_output(output_lines) to
     convert the raw output into a structured VerificationReport

Ticket refs: CB-1242 (config), CB-1243 (runner)
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VerificationType(str, Enum):
    """Type of verification check to perform."""
    VISUAL = "visual"          # Screenshot comparison / visual inspection
    FUNCTIONAL = "functional"  # Click/interact and check behavior
    CONSOLE = "console"        # Check for JavaScript errors in console
    CONTENT = "content"        # Check that specific page text/elements exist


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VerificationCheck:
    """A single check within a verification rule.

    Attributes:
        type: The kind of check (e.g. 'no_console_errors', 'page_not_blank',
              'screenshot', 'element_exists', 'text_contains', 'page_loads').
        severity: Minimum severity for console error checks ('error', 'warning').
        selector: CSS selector for element_exists checks.
        text: Expected text for text_contains checks.
        description: Human-readable description of what this check validates.
    """
    type: str
    severity: Optional[str] = None
    selector: Optional[str] = None
    text: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type}
        if self.severity:
            d["severity"] = self.severity
        if self.selector:
            d["selector"] = self.selector
        if self.text:
            d["text"] = self.text
        if self.description:
            d["description"] = self.description
        return d


@dataclass
class VerificationRule:
    """A named set of checks to run against a target URL.

    Rules are grouped by issue type. Each rule targets a specific URL and
    contains one or more checks to execute.
    """
    name: str
    type: VerificationType
    target_url: str
    checks: List[VerificationCheck] = field(default_factory=list)
    timeout_seconds: int = 30
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "target_url": self.target_url,
            "checks": [c.to_dict() for c in self.checks],
            "timeout_seconds": self.timeout_seconds,
            "description": self.description,
        }


@dataclass
class VerificationResult:
    """Result of a single verification check.

    Attributes:
        passed: Whether the check passed.
        rule_name: Name of the rule this result belongs to.
        check_name: Name of the specific check (e.g. 'no_console_errors').
        evidence: Supporting data (screenshots paths, captured text, etc.).
        error_message: Human-readable failure reason, if any.
        details: Additional detail string from Claude Code output.
        duration_seconds: How long the check took.
    """
    passed: bool
    rule_name: str
    check_name: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    details: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "rule_name": self.rule_name,
            "check_name": self.check_name,
            "evidence": self.evidence,
            "error_message": self.error_message,
            "details": self.details,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class VerificationReport:
    """Aggregate report produced after all verification checks complete.

    Used by the pipeline executor to decide whether to advance or retry.
    """
    passed: bool
    results: List[VerificationResult] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    raw_output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "results": [r.to_dict() for r in self.results],
            "screenshots": self.screenshots,
            "console_errors": self.console_errors,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ---------------------------------------------------------------------------
# Default verification rules per issue type
# ---------------------------------------------------------------------------

# These provide sensible defaults. Custom rules can be merged in via
# get_verification_rules(issue_type, custom_rules=...).

VERIFICATION_CONFIGS: Dict[str, List[VerificationRule]] = {
    "FEATURE": [
        VerificationRule(
            name="page_loads",
            type=VerificationType.FUNCTIONAL,
            target_url="http://localhost:3601",
            description="Verify the app loads without errors after feature implementation",
            checks=[
                VerificationCheck(
                    type="no_console_errors",
                    severity="error",
                    description="No JavaScript errors in console",
                ),
                VerificationCheck(
                    type="page_not_blank",
                    description="Page is not blank/white",
                ),
                VerificationCheck(
                    type="screenshot",
                    description="Capture screenshot as evidence",
                ),
            ],
            timeout_seconds=30,
        ),
    ],

    "STORY": [
        VerificationRule(
            name="component_renders",
            type=VerificationType.VISUAL,
            target_url="http://localhost:3601",
            description="Verify the story's UI component renders correctly",
            checks=[
                VerificationCheck(
                    type="no_console_errors",
                    severity="error",
                    description="No JavaScript errors in console",
                ),
                VerificationCheck(
                    type="page_not_blank",
                    description="Page is not blank/white",
                ),
                VerificationCheck(
                    type="screenshot",
                    description="Capture screenshot as evidence",
                ),
            ],
            timeout_seconds=30,
        ),
    ],

    "TASK": [
        VerificationRule(
            name="no_regressions",
            type=VerificationType.CONSOLE,
            target_url="http://localhost:3601",
            description="Verify no regressions introduced by the task",
            checks=[
                VerificationCheck(
                    type="no_console_errors",
                    severity="error",
                    description="No JavaScript errors in console",
                ),
                VerificationCheck(
                    type="page_loads",
                    description="Page loads without hanging or crashing",
                ),
            ],
            timeout_seconds=30,
        ),
    ],

    "BUG": [
        VerificationRule(
            name="bug_fix_verified",
            type=VerificationType.FUNCTIONAL,
            target_url="http://localhost:3601",
            description="Verify the bug fix resolves the reported issue",
            checks=[
                VerificationCheck(
                    type="no_console_errors",
                    severity="error",
                    description="No JavaScript errors in console",
                ),
                VerificationCheck(
                    type="page_not_blank",
                    description="Page renders content (not blank)",
                ),
                VerificationCheck(
                    type="screenshot",
                    description="Capture screenshot as evidence",
                ),
            ],
            timeout_seconds=30,
        ),
    ],

    "EPIC": [
        VerificationRule(
            name="epic_sanity_check",
            type=VerificationType.FUNCTIONAL,
            target_url="http://localhost:3601",
            description="Basic sanity check after epic-level changes",
            checks=[
                VerificationCheck(
                    type="no_console_errors",
                    severity="error",
                    description="No JavaScript errors in console",
                ),
                VerificationCheck(
                    type="page_not_blank",
                    description="Page renders content (not blank)",
                ),
                VerificationCheck(
                    type="screenshot",
                    description="Capture screenshot as evidence",
                ),
            ],
            timeout_seconds=45,
        ),
    ],
}


# ---------------------------------------------------------------------------
# Screenshot directory
# ---------------------------------------------------------------------------

# Screenshots are saved relative to the project root. The pipeline executor
# passes the project_path; we store evidence under
# <project_path>/.pipeline/screenshots/<execution_id>/
SCREENSHOT_DIR_NAME = ".pipeline/screenshots"


def _ensure_screenshot_dir(project_path: str, execution_id: str) -> str:
    """Create and return the screenshot directory for a pipeline run."""
    dir_path = os.path.join(project_path, SCREENSHOT_DIR_NAME, execution_id)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


# ---------------------------------------------------------------------------
# Verification Service
# ---------------------------------------------------------------------------

class VerificationService:
    """Generates verification prompts and parses Chrome MCP output.

    This service is designed to be called by the pipeline executor after an
    IMPLEMENT stage completes. It does NOT call Chrome MCP directly -- instead
    it generates a prompt that Claude Code will execute using its Chrome MCP
    (or Playwright MCP) tools, and then parses the structured JSON output that
    Claude Code returns.

    Typical usage in pipeline_executor:

        rules = verification_service.get_verification_rules(issue.type)
        prompt = verification_service.build_verification_prompt(
            issue_key=issue.key,
            issue_title=issue.title,
            issue_type=issue.type,
            implementation_summary=impl_summary,
            rules=rules,
        )
        # ... spawn Claude Code session with `prompt` ...
        report = verification_service.parse_verification_output(output_lines)
    """

    # ------------------------------------------------------------------
    # Rule resolution
    # ------------------------------------------------------------------

    def get_verification_rules(
        self,
        issue_type: str,
        custom_url: Optional[str] = None,
        custom_checks: Optional[List[Dict[str, Any]]] = None,
        extra_rules: Optional[List[VerificationRule]] = None,
    ) -> List[VerificationRule]:
        """Get verification rules for an issue type with optional overrides.

        Args:
            issue_type: Jira/PM issue type (FEATURE, STORY, TASK, BUG, EPIC).
            custom_url: Override the target URL for all rules.
            custom_checks: Additional check dicts to append to all rules.
            extra_rules: Fully formed extra VerificationRule objects to append.

        Returns:
            List of VerificationRule instances to execute.
        """
        # Start with defaults; fall back to TASK if unknown type
        base = VERIFICATION_CONFIGS.get(issue_type, VERIFICATION_CONFIGS["TASK"])

        # Deep-copy so mutations don't affect the module-level config
        rules: List[VerificationRule] = []
        for r in base:
            rule = VerificationRule(
                name=r.name,
                type=r.type,
                target_url=custom_url or r.target_url,
                checks=list(r.checks),
                timeout_seconds=r.timeout_seconds,
                description=r.description,
            )
            # Append custom checks
            if custom_checks:
                for cc in custom_checks:
                    rule.checks.append(VerificationCheck(
                        type=cc.get("type", "custom"),
                        severity=cc.get("severity"),
                        selector=cc.get("selector"),
                        text=cc.get("text"),
                        description=cc.get("description"),
                    ))
            rules.append(rule)

        # Append extra rules
        if extra_rules:
            rules.extend(extra_rules)

        return rules

    # ------------------------------------------------------------------
    # Prompt generation
    # ------------------------------------------------------------------

    def build_verification_prompt(
        self,
        issue_key: str,
        issue_title: str,
        issue_type: str,
        implementation_summary: str,
        target_url: str = "http://localhost:3601",
        rules: Optional[List[VerificationRule]] = None,
        execution_id: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> str:
        """Build a prompt for Claude Code to run verification using Chrome MCP.

        The resulting prompt instructs Claude Code to:
          1. Navigate to the target URL
          2. Wait for the page to load
          3. Check the browser console for errors
          4. Take screenshots as evidence
          5. Run each check described in the rules
          6. Output a structured JSON result block

        Args:
            issue_key: The issue identifier (e.g. 'CB-1243').
            issue_title: Human-readable issue title.
            issue_type: Issue type (FEATURE, STORY, TASK, BUG).
            implementation_summary: Summary of what was implemented.
            target_url: Base URL to verify against.
            rules: Verification rules to execute. If None, defaults are used.
            execution_id: Pipeline execution ID (for screenshot naming).
            project_path: Project root path (for screenshot storage).

        Returns:
            A complete prompt string ready to send to Claude Code.
        """
        if rules is None:
            rules = self.get_verification_rules(issue_type, custom_url=target_url)

        # Build the checks list for the prompt
        checks_section = self._format_checks_for_prompt(rules)

        # Screenshot directory hint
        screenshot_hint = ""
        if project_path and execution_id:
            screenshot_dir = os.path.join(
                project_path, SCREENSHOT_DIR_NAME, execution_id
            )
            screenshot_hint = (
                f"\nSave screenshots to: {screenshot_dir}\n"
                f"Use descriptive filenames like `01-page-load.png`, `02-after-interaction.png`.\n"
            )

        prompt = f"""You are a QA verification agent. Your job is to verify that the implementation of {issue_key}: {issue_title} is working correctly in the browser.

## What was implemented
{implementation_summary}

## Verification Rules
{checks_section}

## Verification Steps

Follow these steps in order:

1. **Navigate** to {target_url} and wait for the page to fully load (wait up to 10 seconds).
   - Use `mcp__claude-in-chrome__navigate` or `mcp__playwright__browser_navigate`.

2. **Check console** for JavaScript errors.
   - Use `mcp__claude-in-chrome__read_console_messages` with `onlyErrors: true`.
   - Alternatively use `mcp__playwright__browser_console_messages` with `level: "error"`.
   - Ignore React hydration warnings and non-critical deprecation notices.

3. **Take a screenshot** of the current page state.
   - Use `mcp__claude-in-chrome__computer` with `action: "screenshot"`.
   - Or use `mcp__playwright__browser_take_screenshot`.
{screenshot_hint}
4. **Verify page content**:
   - Confirm the page is not blank (has visible text/elements).
   - Use `mcp__claude-in-chrome__read_page` or `mcp__playwright__browser_snapshot` to read the page structure.
   - Check that no user-visible error messages are displayed.

5. **Run specific checks** listed in the rules above.
   - For `element_exists` checks: verify the CSS selector matches an element.
   - For `text_contains` checks: verify the expected text is present on the page.
   - For `page_loads` checks: confirm the page loaded without timeout.

6. If the implementation involved a **specific page or component**, navigate to it directly and repeat the checks.

## Output Format

After completing all checks, output EXACTLY one JSON block with your results. The JSON must be wrapped in a markdown code fence:

```json
{{
  "passed": true,
  "checks": [
    {{"name": "page_loads", "passed": true, "details": "Page loaded in 2.1s"}},
    {{"name": "no_console_errors", "passed": true, "details": "No errors found"}},
    {{"name": "page_not_blank", "passed": true, "details": "Page has 47 visible elements"}},
    {{"name": "visual_check", "passed": true, "details": "Screenshot captured"}}
  ],
  "console_errors": [],
  "screenshots": ["01-page-load.png"],
  "summary": "All checks passed. Page loads correctly with no JS errors."
}}
```

**Important rules:**
- Set `"passed": false` at the top level if ANY check fails.
- Include ALL console errors in the `console_errors` array (even if you pass overall).
- Be thorough but practical: if the page loads, has content, and has no JS errors, that is a pass for basic verification.
- Do NOT fabricate results. If a tool call fails, report it as a failed check.
"""
        return prompt

    def build_targeted_verification_prompt(
        self,
        issue_key: str,
        issue_title: str,
        implementation_summary: str,
        target_page: str,
        elements_to_check: List[str],
        interactions: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Build a more targeted verification prompt for specific UI features.

        Use this when the issue modifies a specific page/component and you want
        to verify particular elements or interactions beyond basic page-load checks.

        Args:
            issue_key: Issue identifier.
            issue_title: Issue title.
            implementation_summary: What was implemented.
            target_page: Full URL of the specific page to check.
            elements_to_check: List of element descriptions to verify
                (e.g. ["filter dropdown", "project cards grid", "status badges"]).
            interactions: Optional list of interactions to perform, each a dict
                with keys 'action' and 'description'
                (e.g. [{"action": "click the filter dropdown", "description": "Verify dropdown opens"}]).

        Returns:
            A prompt string for Claude Code.
        """
        elements_list = "\n".join(f"   - {e}" for e in elements_to_check)

        interactions_section = ""
        if interactions:
            steps = []
            for i, interaction in enumerate(interactions, 1):
                steps.append(
                    f"   {i}. **{interaction['action']}** — {interaction.get('description', 'Verify behavior')}"
                )
            interactions_section = (
                "\n## Interactions to Verify\n"
                + "\n".join(steps)
                + "\n\nAfter each interaction, take a screenshot and verify the expected behavior.\n"
            )

        prompt = f"""You are a QA verification agent performing targeted UI checks for {issue_key}: {issue_title}.

## What was implemented
{implementation_summary}

## Target Page
Navigate to: {target_page}

## Elements to Verify
Check that each of these elements exists and renders correctly:
{elements_list}
{interactions_section}
## Steps

1. Navigate to {target_page} and wait for full page load.
2. Check console for JavaScript errors.
3. Take a screenshot of the initial state.
4. For each element listed above:
   a. Verify it exists on the page (use read_page / snapshot).
   b. Verify it is visible (not hidden or zero-size).
   c. Note any rendering issues.
5. If interactions are listed, perform each one and screenshot the result.
6. Output your results as a JSON block.

## Output Format

```json
{{
  "passed": true,
  "checks": [
    {{"name": "element_name", "passed": true, "details": "Element found and visible"}}
  ],
  "console_errors": [],
  "screenshots": [],
  "summary": "Brief summary"
}}
```

Set `"passed": false` at the top level if ANY check fails.
"""
        return prompt

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def parse_verification_output(
        self,
        output_lines: List[str],
    ) -> VerificationReport:
        """Parse Claude Code's verification output into a VerificationReport.

        Looks for a JSON result block in the output. The block should contain
        keys: passed, checks, console_errors, screenshots, summary.

        Falls back to heuristic text analysis if no valid JSON is found.

        Args:
            output_lines: Raw output lines from the Claude Code session.

        Returns:
            A populated VerificationReport.
        """
        report = VerificationReport(
            passed=False,
            started_at=datetime.utcnow(),
        )

        # Store raw output for debugging
        raw_text = "\n".join(output_lines)
        report.raw_output = raw_text[:10000]  # cap at 10K chars

        # --- Strategy 1: Extract JSON block from markdown code fence ---
        json_data = self._extract_json_block(raw_text)

        if json_data is not None:
            report = self._build_report_from_json(json_data, report)
        else:
            # --- Strategy 2: Look for inline JSON (no code fence) ---
            json_data = self._extract_inline_json(output_lines)
            if json_data is not None:
                report = self._build_report_from_json(json_data, report)
            else:
                # --- Strategy 3: Heuristic text analysis ---
                report = self._build_report_from_heuristics(output_lines, report)

        report.completed_at = datetime.utcnow()
        return report

    # ------------------------------------------------------------------
    # Internal: prompt formatting
    # ------------------------------------------------------------------

    def _format_checks_for_prompt(self, rules: List[VerificationRule]) -> str:
        """Format verification rules into readable text for the prompt."""
        sections = []
        for rule in rules:
            lines = [f"### Rule: {rule.name}"]
            if rule.description:
                lines.append(f"_{rule.description}_")
            lines.append(f"- **Type:** {rule.type.value}")
            lines.append(f"- **URL:** {rule.target_url}")
            lines.append(f"- **Timeout:** {rule.timeout_seconds}s")
            lines.append("- **Checks:**")
            for check in rule.checks:
                desc = check.description or check.type
                detail_parts = []
                if check.severity:
                    detail_parts.append(f"severity={check.severity}")
                if check.selector:
                    detail_parts.append(f"selector=`{check.selector}`")
                if check.text:
                    detail_parts.append(f"text=\"{check.text}\"")
                detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
                lines.append(f"  - `{check.type}`: {desc}{detail}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Internal: JSON extraction
    # ------------------------------------------------------------------

    def _extract_json_block(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON block from markdown code fences in the text.

        Handles ```json ... ``` and ``` ... ``` formats.
        Returns the parsed dict or None.
        """
        # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
        pattern = r"```(?:json)?\s*\n(\{[\s\S]*?\})\s*\n```"
        matches = re.findall(pattern, text)

        for match in matches:
            try:
                data = json.loads(match)
                # Validate it looks like a verification result
                if "passed" in data:
                    return data
            except json.JSONDecodeError:
                continue

        return None

    def _extract_inline_json(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Try to find an inline JSON object across output lines.

        Handles cases where JSON appears without code fences.
        """
        json_block = ""
        brace_depth = 0
        in_json = False

        for line in lines:
            stripped = line.strip()

            if not in_json:
                # Look for the start of a JSON object containing "passed"
                if stripped.startswith("{") and '"passed"' in stripped:
                    in_json = True
                    json_block = stripped
                    brace_depth = stripped.count("{") - stripped.count("}")
                    if brace_depth == 0:
                        # Complete JSON on one line
                        break
                continue

            # Accumulating multi-line JSON
            json_block += "\n" + stripped
            brace_depth += stripped.count("{") - stripped.count("}")

            if brace_depth <= 0:
                break

        if json_block:
            # Clean up: remove markdown artifacts
            clean = json_block.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\s*", "", clean)
            if clean.endswith("```"):
                clean = clean[:-3].strip()

            try:
                data = json.loads(clean)
                if "passed" in data:
                    return data
            except json.JSONDecodeError:
                logger.debug(
                    "Found potential JSON block but failed to parse: %s",
                    clean[:200],
                )

        return None

    # ------------------------------------------------------------------
    # Internal: report building
    # ------------------------------------------------------------------

    def _build_report_from_json(
        self,
        data: Dict[str, Any],
        report: VerificationReport,
    ) -> VerificationReport:
        """Populate a VerificationReport from parsed JSON data."""
        report.passed = bool(data.get("passed", False))
        report.console_errors = data.get("console_errors", [])
        report.screenshots = data.get("screenshots", [])

        checks = data.get("checks", [])
        report.total_checks = len(checks)
        report.passed_checks = sum(1 for c in checks if c.get("passed"))
        report.failed_checks = report.total_checks - report.passed_checks

        for check in checks:
            result = VerificationResult(
                passed=bool(check.get("passed", False)),
                rule_name=check.get("name", "unknown"),
                check_name=check.get("name", "unknown"),
                details=check.get("details", ""),
                evidence={"details": check.get("details", "")},
            )
            if not result.passed:
                result.error_message = check.get("details", "Check failed")
            report.results.append(result)

        # If there are console errors and the report says passed, but we have
        # actual JS errors (not warnings), flag it
        if report.passed and report.console_errors:
            real_errors = [
                e for e in report.console_errors
                if not self._is_ignorable_console_message(e)
            ]
            if real_errors:
                logger.warning(
                    "Verification passed but %d real console errors found",
                    len(real_errors),
                )
                # Don't override Claude's judgment, but log it

        summary = data.get("summary", "")
        if summary:
            logger.info("Verification summary: %s", summary)

        return report

    def _build_report_from_heuristics(
        self,
        output_lines: List[str],
        report: VerificationReport,
    ) -> VerificationReport:
        """Fall back to heuristic text analysis when no JSON block is found.

        Scans the output for keywords that indicate pass/fail.
        """
        all_text = " ".join(output_lines).lower()

        # Count failure and success signals
        failure_signals = [
            "error", "failed", "broken", "crash", "exception",
            "blank page", "not found", "timeout", "500",
        ]
        success_signals = [
            "pass", "success", "working", "loaded", "renders",
            "no errors", "looks good", "all checks passed",
        ]

        failure_count = sum(1 for s in failure_signals if s in all_text)
        success_count = sum(1 for s in success_signals if s in all_text)

        if failure_count > success_count:
            report.passed = False
            report.results.append(VerificationResult(
                passed=False,
                rule_name="heuristic_analysis",
                check_name="output_analysis",
                error_message="Verification output indicates failure (heuristic: no JSON found)",
                details=f"Found {failure_count} failure signals, {success_count} success signals",
            ))
        elif success_count > 0:
            report.passed = True
            report.results.append(VerificationResult(
                passed=True,
                rule_name="heuristic_analysis",
                check_name="output_analysis",
                details=f"Found {success_count} success signals, {failure_count} failure signals",
            ))
        else:
            # Ambiguous output -- fail safe
            report.passed = False
            report.results.append(VerificationResult(
                passed=False,
                rule_name="heuristic_analysis",
                check_name="output_analysis",
                error_message="Could not determine verification result from output",
                details="No JSON block found and no clear pass/fail signals",
            ))

        report.total_checks = len(report.results)
        report.passed_checks = sum(1 for r in report.results if r.passed)
        report.failed_checks = report.total_checks - report.passed_checks

        return report

    # ------------------------------------------------------------------
    # Internal: console message filtering
    # ------------------------------------------------------------------

    @staticmethod
    def _is_ignorable_console_message(message: str) -> bool:
        """Check if a console message can be safely ignored.

        Filters out known noisy messages that don't indicate real problems:
        - React hydration warnings
        - Next.js development mode warnings
        - Browser extension noise
        - Deprecation notices
        """
        ignorable_patterns = [
            "hydration",
            "hydrat",
            "react-dom",
            "next-dev",
            "fast refresh",
            "hot module",
            "hmr",
            "deprecated",
            "deprecation",
            "extension",
            "chrome-extension",
            "moz-extension",
            "favicon.ico",
            "serviceworker",
            "workbox",
            "manifest.json",
            "source map",
            "sourcemap",
            # ChromaDB heartbeat 410 (known non-blocking issue)
            "410",
            "heartbeat",
        ]
        msg_lower = message.lower()
        return any(p in msg_lower for p in ignorable_patterns)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

verification_service = VerificationService()
