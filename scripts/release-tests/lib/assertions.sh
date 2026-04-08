#!/bin/bash
# Assertion helpers for release tests. All assertions print PASS/FAIL to
# stdout and append to $TEST_REPORT_FILE if set. Use as:
#
#   as_assert "backend health" '[[ "$status" == "ok" ]]'
#
# Or the typed helpers:
#
#   as_assert_eq    "alembic head"  "$expected" "$actual"
#   as_assert_ge    "doc count"     "$pre" "$post"
#   as_assert_http  "frontend"      200 "$(curl -o /dev/null -w '%{http_code}' http://localhost:6173/)"
#   as_assert_file  "transcript"    "$path"
#   as_assert_json_field "files[0].status"  "completed" "$response_json"

set -euo pipefail

: "${TEST_REPORT_FILE:=/dev/null}"

as_pass=0
as_fail=0

as_record() {
    local status="$1"
    local label="$2"
    local detail="${3:-}"
    if [[ "$status" == "PASS" ]]; then
        echo -e "\033[0;32m  PASS\033[0m  $label"
        as_pass=$((as_pass + 1))
    else
        echo -e "\033[0;31m  FAIL\033[0m  $label  ${detail}"
        as_fail=$((as_fail + 1))
    fi
    printf '| %s | %s | %s |\n' "$status" "$label" "$detail" >> "$TEST_REPORT_FILE"
}

as_assert() {
    local label="$1"
    shift
    if eval "$*"; then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "expression failed: $*"
    fi
}

as_assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "expected='$expected' actual='$actual'"
    fi
}

as_assert_ne() {
    local label="$1" unexpected="$2" actual="$3"
    if [[ "$unexpected" != "$actual" ]]; then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "value should not equal '$unexpected'"
    fi
}

as_assert_ge() {
    local label="$1" left="$2" right="$3"
    if (( left >= right )); then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "$left < $right"
    fi
}

as_assert_http() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "HTTP $actual (expected $expected)"
    fi
}

as_assert_file() {
    local label="$1" path="$2"
    if [[ -f "$path" && -s "$path" ]]; then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "missing or empty: $path"
    fi
}

as_assert_json_field() {
    # Usage: as_assert_json_field "label" "<jq path>" "<expected>" "<json>"
    local label="$1" path="$2" expected="$3" json="$4"
    local actual
    actual=$(echo "$json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for part in '$path'.split('.'):
    if part.endswith(']'):
        key, idx = part[:-1].split('[')
        data = (data.get(key) if key else data)[int(idx)]
    else:
        data = data.get(part) if isinstance(data, dict) else data
print(data)
" 2>/dev/null || echo "<error>")
    as_assert_eq "$label" "$expected" "$actual"
}

as_assert_diff_files() {
    # Asserts two text files have identical content. Useful for snapshot diffs.
    local label="$1" file_a="$2" file_b="$3"
    if diff -q "$file_a" "$file_b" >/dev/null 2>&1; then
        as_record PASS "$label"
    else
        as_record FAIL "$label" "$(diff -u "$file_a" "$file_b" | head -20 | tr '\n' ' ')"
    fi
}

as_summary() {
    local total=$((as_pass + as_fail))
    echo
    if (( as_fail == 0 )); then
        echo -e "\033[0;32m=== ${as_pass}/${total} assertions passed ===\033[0m"
        return 0
    else
        echo -e "\033[0;31m=== ${as_fail}/${total} assertions FAILED ===\033[0m"
        return 1
    fi
}
