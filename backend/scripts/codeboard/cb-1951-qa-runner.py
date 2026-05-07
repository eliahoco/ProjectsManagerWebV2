"""
CB-1951 QA Runner — orchestrate the QA Board test execution and report
PASS/FAIL back to the board.

Reads the spec map from `docs/cb-1951/id-map.json` (created by the push
script) and a curated TEST_MAPPING below to know which pytest/vitest/
chrome recipe corresponds to each QA-task. For automated tests, runs
the command and PATCHes the QA task with PASS/FAILED + truncated output.
For manual tasks, prints the recipe and waits for the operator to run
report() programmatically with the result.

Usage:
    python scripts/codeboard/cb-1951-qa-runner.py --suite repository
    python scripts/codeboard/cb-1951-qa-runner.py --suite all
    python scripts/codeboard/cb-1951-qa-runner.py --list
    python scripts/codeboard/cb-1951-qa-runner.py --skip-passed   # only re-run failures
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from typing import Optional

BASE = "http://localhost:8401/api"
ID_MAP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "docs", "cb-1951", "id-map.json"
)
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


# ---------------------------------------------------------------------------
# Test mapping: QA label → (suite, runner type, command/recipe)
# ---------------------------------------------------------------------------
# Suites: "repository", "persistence", "detection", "reset_time",
# "scheduler", "regression", "frontend", "chrome", "manual"
# Runner type: "pytest" | "vitest" | "chrome" | "manual" | "shell"
# Command: shell command to execute (for pytest/vitest/shell)

TEST_MAPPING = {
    # Repository (E1.2.2)
    "QA-A01": ("repository", "pytest", "pytest tests/test_autopilot_repository.py::test_save_queue_roundtrip -q"),
    "QA-A02": ("repository", "pytest", "pytest tests/test_autopilot_repository.py::test_load_active_queue_filters_terminal -q"),
    "QA-A03": ("repository", "pytest", "pytest tests/test_autopilot_repository.py::test_save_queue_roundtrip -q"),
    "QA-A04": ("repository", "pytest", "pytest tests/test_autopilot_repository.py::test_record_event_appends -q"),
    "QA-A05": ("repository", "pytest", "pytest tests/test_autopilot_repository.py::test_save_queue_update_idempotent -q"),
    # Persistence E2E (E1.3 / E2)
    "QA-A06": ("persistence", "pytest", "pytest tests/test_autopilot_persistence.py::test_rehydrate_recovers_running_queue -q"),
    "QA-A07": ("persistence", "pytest", "pytest tests/test_autopilot_persistence.py::test_rehydrate_recovers_running_queue -q"),
    "QA-A08": ("persistence", "pytest", "pytest tests/test_autopilot_persistence.py::test_rehydrate_recovers_running_queue -q"),
    "QA-A09": ("persistence", "pytest", "pytest tests/test_autopilot_repository.py::test_save_queue_update_idempotent -q"),
    # Token-exhaustion detection (E3.1.4)
    "QA-A10": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_pattern_out_of_extra_usage -q"),
    "QA-A11": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_pattern_rate_limit_exceeded -q"),
    "QA-A12": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_pattern_credit_low -q"),
    "QA-A13": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_pattern_rate_limit_error_stream_json -q"),
    "QA-A14": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_clean_exit_returns_false -q"),
    "QA-A15": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_unrelated_error_returns_false -q"),
    "QA-A16": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_case_insensitive_uppercase tests/test_token_exhaustion_detection.py::test_case_insensitive_mixed -q"),
    "QA-A17": ("detection", "pytest", "pytest tests/test_token_exhaustion_detection.py::test_pattern_in_output_tail_only tests/test_token_exhaustion_detection.py::test_pattern_in_output_too_far_back_returns_false -q"),
    # Reset time (E3.2.3)
    "QA-A18": ("reset_time", "pytest", "pytest tests/test_reset_time_extraction.py::test_iso_datetime_T_separator -q"),
    "QA-A19": ("reset_time", "pytest", "pytest tests/test_reset_time_extraction.py::test_iso_datetime_T_separator -q"),
    "QA-A20": ("reset_time", "pytest", "pytest tests/test_reset_time_extraction.py -k 'ampm or hhmm' -q"),
    "QA-A21": ("reset_time", "pytest", "pytest tests/test_reset_time_extraction.py::test_resets_at_already_past_rolls_to_tomorrow -q"),
    "QA-A22": ("reset_time", "pytest", "pytest tests/test_reset_time_extraction.py -k 'retry_after' -q"),
    "QA-A23": ("reset_time", "pytest", "pytest tests/test_reset_time_extraction.py -k 'returns_none or malformed or invalid' -q"),
    # Scheduler (E4.x)
    "QA-A24": ("scheduler", "pytest", "pytest tests/test_auto_resume_scheduler.py::test_schedule_auto_resume_arms_a_timer -q"),
    "QA-A25": ("scheduler", "pytest", "pytest tests/test_auto_resume_scheduler.py -k 'cancel' -q"),
    "QA-A26": ("scheduler", "pytest", "pytest tests/test_auto_resume_scheduler.py::test_abort_queue_cancels_pending_timer -q"),
    "QA-A27": ("scheduler", "pytest", "pytest tests/test_auto_resume_scheduler.py::test_rearm_token_exhaustion_arms_timer tests/test_auto_resume_scheduler.py::test_rearm_skips_crash_recovery -q"),
    "QA-A28": ("scheduler", "pytest", "pytest tests/test_auto_resume_scheduler.py::test_schedule_auto_resume_arms_a_timer -q"),
    # E2E
    "QA-A29": ("e2e", "pytest", "pytest tests/test_autopilot_persistence.py -q"),
    "QA-A30": ("e2e", "pytest", "pytest tests/test_autopilot_persistence.py::test_rehydrate_recovers_running_queue -q"),
    "QA-A31": ("e2e", "pytest", "pytest tests/test_autopilot_persistence.py -q"),
    "QA-A32": ("e2e", "pytest", "pytest tests/test_auto_resume_scheduler.py -k 'preflight' -q"),
    "QA-A33": ("e2e", "pytest", "pytest tests/test_auto_resume_scheduler.py::test_abort_queue_cancels_pending_timer -q"),
    # Regression
    "QA-A34": ("regression", "pytest", "pytest tests/test_cascade_in_progress_guard.py -q"),
    "QA-A35": ("regression", "pytest", "pytest -q --ignore=tests/test_qa_sequence.py --ignore=tests/test_schema_validation.py"),
    # Frontend (E5 — not yet shipped)
    "QA-A36": ("frontend", "vitest", "npm test -- AutoPilotFloatingBar.test.tsx -t WAITING_RESET"),
    "QA-A37": ("frontend", "vitest", "npm test -- AutoPilotFloatingBar.test.tsx -t crash_recovery"),
    "QA-A38": ("frontend", "vitest", "npm test -- AutoPilotFloatingBar.test.tsx -t resume_now_button"),
    "QA-A39": ("frontend", "vitest", "npm test -- AutoPilotFloatingBar.test.tsx -t countdown_ticks"),
    "QA-A40": ("frontend", "vitest", "npm test -- use-autopilot-events.test.tsx -t toast_on_event"),
    "QA-A41": ("frontend", "vitest", "npm test"),
    # Chrome — manual recipes via mcp__claude-in-chrome
    **{f"QA-C{i:02}": ("chrome", "chrome", f"see backend/docs/cb-1951/chrome-recipes.md QA-C{i:02}") for i in range(1, 13)},
    # Manual matrix
    **{f"QA-M{i:02}": ("manual", "manual", f"see backend/docs/AUTOPILOT_RUNBOOK.md M{i:02}") for i in range(1, 13)},
}


# ---------------------------------------------------------------------------
# QA Board API helpers
# ---------------------------------------------------------------------------


def _patch(qa_id: str, status: str, actual: str):
    body = {"status": status, "actualResult": actual[:4000]}
    req = urllib.request.Request(
        f"{BASE}/qa/tasks/{qa_id}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code} on PATCH: {body_txt[:200]}")
        return None


def _get_qa(qa_id: str) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"{BASE}/qa/tasks/{qa_id}", timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_pytest_or_shell(cmd: str) -> tuple[bool, str]:
    """Execute a shell command from BACKEND_DIR using the venv. Returns
    (passed, captured_output_truncated)."""
    venv_python = os.path.join(BACKEND_DIR, "venv", "bin", "python3")
    if cmd.startswith("pytest"):
        cmd = f"{venv_python} -m {cmd}"
    proc = subprocess.run(
        cmd, shell=True, cwd=BACKEND_DIR,
        capture_output=True, text=True, timeout=300,
    )
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return (proc.returncode == 0, output[-3500:])


def run_vitest(cmd: str) -> tuple[bool, str]:
    """Run from frontend/ dir."""
    frontend_dir = os.path.join(BACKEND_DIR, "..", "frontend")
    proc = subprocess.run(
        cmd, shell=True, cwd=frontend_dir,
        capture_output=True, text=True, timeout=300,
    )
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return (proc.returncode == 0, output[-3500:])


def execute_label(label: str, id_map: dict, skip_passed: bool = False, dry_run: bool = False) -> str:
    """Returns "PASS", "FAILED", "SKIPPED", or "MANUAL"."""
    spec = TEST_MAPPING.get(label)
    if not spec:
        print(f"[{label}] no mapping; skipping")
        return "SKIPPED"
    suite, runner, cmd = spec
    qa = id_map.get("qa_tasks", {}).get(label)
    if not qa or "id" not in qa:
        print(f"[{label}] no QA-task id in id-map; skipping")
        return "SKIPPED"
    qa_id = qa["id"]
    qa_key = qa["key"]

    # Skip if already PASS and --skip-passed
    if skip_passed:
        live = _get_qa(qa_id)
        if live and live.get("status") == "PASS":
            print(f"[{qa_key}] {label} already PASS — skipping")
            return "SKIPPED"

    if dry_run:
        print(f"[{qa_key}] {label} ({suite}/{runner}): {cmd}")
        return "SKIPPED"

    if runner == "manual" or runner == "chrome":
        print(f"[{qa_key}] {label} ({runner}): MANUAL — {cmd}")
        return "MANUAL"

    print(f"[{qa_key}] {label} ({suite}/{runner}) → executing...")
    if runner == "pytest" or runner == "shell":
        passed, out = run_pytest_or_shell(cmd)
    elif runner == "vitest":
        passed, out = run_vitest(cmd)
    else:
        print(f"  unknown runner {runner}")
        return "SKIPPED"

    status = "PASS" if passed else "FAILED"
    actual = f"$ {cmd}\n\n{out}"
    _patch(qa_id, status, actual)
    print(f"  → {status}")
    return status


def report(label: str, status: str, actual: str, gif_path: str | None = None):
    """Programmatic API for the operator to feed manual/chrome results back."""
    with open(ID_MAP_PATH) as f:
        id_map = json.load(f)
    qa = id_map.get("qa_tasks", {}).get(label)
    if not qa or "id" not in qa:
        print(f"no QA id for {label}")
        return
    full = actual + (f"\n\nEvidence: {gif_path}" if gif_path else "")
    _patch(qa["id"], status, full)
    print(f"{qa['key']} {label} → {status}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", default="all",
                   help="repository|persistence|detection|reset_time|scheduler|"
                        "e2e|regression|frontend|chrome|manual|all")
    p.add_argument("--label", default=None, help="Single QA-task label (e.g. QA-A01)")
    p.add_argument("--list", action="store_true", help="List mappings and exit")
    p.add_argument("--skip-passed", action="store_true",
                   help="Skip QA tasks whose QA Board status is already PASS")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would run; PATCH nothing")
    args = p.parse_args()

    if args.list:
        for label, spec in sorted(TEST_MAPPING.items()):
            print(f"  {label:8}  {spec[0]:11}  {spec[1]:8}  {spec[2][:80]}")
        return 0

    with open(ID_MAP_PATH) as f:
        id_map = json.load(f)

    if args.label:
        labels = [args.label]
    elif args.suite == "all":
        labels = sorted(TEST_MAPPING.keys())
    else:
        labels = sorted(
            label for label, spec in TEST_MAPPING.items()
            if spec[0] == args.suite
        )

    counts = {"PASS": 0, "FAILED": 0, "SKIPPED": 0, "MANUAL": 0}
    for label in labels:
        result = execute_label(label, id_map,
                               skip_passed=args.skip_passed,
                               dry_run=args.dry_run)
        counts[result] = counts.get(result, 0) + 1

    print(f"\nSummary: {counts}")
    return 0 if counts.get("FAILED", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
