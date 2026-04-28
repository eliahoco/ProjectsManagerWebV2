#!/bin/bash
# Watchdog regression test runner
# Runs T1, T2, T3 and reports a pass/fail summary.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TESTS=(
    "test_slow_backend_no_kill.sh"
    "test_real_crash_restart.sh"
    "test_no_reload_no_restart.sh"
)

PASS=0
FAIL=0
SKIP=0
RESULTS=()

run_test() {
    local name="$1"
    local script="$SCRIPT_DIR/$name"

    if [ ! -f "$script" ]; then
        echo "  [MISSING] $name"
        RESULTS+=("MISSING  $name")
        FAIL=$((FAIL + 1))
        return
    fi

    chmod +x "$script"
    echo ""
    echo "--- Running: $name ---"

    local output
    local rc=0
    output=$(bash "$script" 2>&1) || rc=$?

    echo "$output"

    if echo "$output" | grep -q '^SKIP:'; then
        RESULTS+=("SKIP     $name")
        SKIP=$((SKIP + 1))
    elif [ $rc -eq 0 ] && echo "$output" | grep -q '^PASS:'; then
        RESULTS+=("PASS     $name")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL     $name  (exit $rc)")
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================"
echo "  Watchdog Regression Tests"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

for t in "${TESTS[@]}"; do
    run_test "$t"
done

echo ""
echo "========================================"
echo "  Summary"
echo "========================================"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Passed: $PASS  Failed: $FAIL  Skipped: $SKIP"
echo "========================================"

[ $FAIL -eq 0 ] && exit 0 || exit 1
