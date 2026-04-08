#!/bin/bash
# Thin curl wrappers around the OpenTranscribe REST API.
#
# All functions assume:
#   API_BASE              e.g. http://localhost:6174/api
#   API_TOKEN             JWT (set after ac_login)
#   API_TIMEOUT           connect timeout, default 10 s
#
# These helpers print structured progress to stderr and parsed JSON to stdout
# so they can be composed in `var=$(ac_func ...)` style.

set -euo pipefail

: "${API_TIMEOUT:=10}"

ac_log()  { echo -e "\033[0;34m[api]\033[0m $*" >&2; }
ac_warn() { echo -e "\033[1;33m[api]\033[0m $*" >&2; }
ac_die()  { echo -e "\033[0;31m[api] FATAL:\033[0m $*" >&2; exit 1; }

ac_curl() {
    # Wrapper that always sets sensible defaults and the auth header if present.
    local args=(--silent --show-error --fail-with-body --max-time 60 --connect-timeout "$API_TIMEOUT")
    if [[ -n "${API_TOKEN:-}" ]]; then
        args+=(-H "Authorization: Bearer $API_TOKEN")
    fi
    curl "${args[@]}" "$@"
}

ac_wait_for_health() {
    # Poll /api/health until 200 or timeout (default 15 minutes).
    local timeout="${1:-900}"
    local deadline=$(( $(date +%s) + timeout ))
    ac_log "waiting up to ${timeout}s for $API_BASE/health"
    while (( $(date +%s) < deadline )); do
        if curl -fsS --max-time 5 "$API_BASE/health" >/dev/null 2>&1; then
            ac_log "backend healthy"
            return 0
        fi
        sleep 5
    done
    ac_die "backend never reached healthy state within ${timeout}s"
}

ac_register_admin() {
    # First-user registration becomes super-admin. Idempotent: returns silently
    # if registration fails because the user already exists.
    local email="$1"
    local password="$2"
    local username="${3:-admin}"
    ac_log "registering $email"
    local payload
    payload=$(printf '{"email":"%s","password":"%s","username":"%s","full_name":"Release Test"}' \
        "$email" "$password" "$username")
    if ! curl -fsS -X POST "$API_BASE/auth/register" \
        -H "Content-Type: application/json" \
        -d "$payload" >/dev/null 2>&1; then
        ac_warn "register returned non-2xx (probably already exists) — continuing"
    fi
}

ac_login() {
    local email="$1"
    local password="$2"
    ac_log "logging in $email"
    local body
    body=$(curl -fsS -X POST "$API_BASE/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=${email}&password=${password}")
    API_TOKEN=$(echo "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
    export API_TOKEN
    [[ -n "$API_TOKEN" ]] || ac_die "login failed: no access_token in response"
    ac_log "login OK (token len $(echo -n "$API_TOKEN" | wc -c))"
}

ac_upload_from_url() {
    # POST /files/upload-from-url
    # Echoes the file_id of the new task.
    local url="$1"
    ac_log "uploading via URL: $url"
    local body
    body=$(ac_curl -X POST "$API_BASE/files/upload-from-url" \
        -H "Content-Type: application/json" \
        -d "$(printf '{"url":"%s"}' "$url")")
    echo "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("id") or json.load(sys.stdin).get("file_id"))'
}

ac_wait_for_file_status() {
    # Poll /files/<id> until status == completed (or error/timeout).
    local file_id="$1"
    local timeout="${2:-1800}"  # 30 min default for CPU transcription
    local deadline=$(( $(date +%s) + timeout ))
    local status=""
    while (( $(date +%s) < deadline )); do
        status=$(ac_curl "$API_BASE/files/$file_id" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status",""))' 2>/dev/null || echo "")
        case "$status" in
            completed)
                ac_log "file $file_id reached status=completed"
                return 0
                ;;
            error|failed)
                ac_die "file $file_id ended in status=$status"
                ;;
        esac
        ac_log "  file $file_id status=$status (waiting)"
        sleep 10
    done
    ac_die "file $file_id never reached completed status within ${timeout}s"
}

ac_get_file() {
    ac_curl "$API_BASE/files/$1"
}

ac_get_transcript() {
    # Returns full transcript JSON for a file.
    ac_curl "$API_BASE/files/$1/transcript" 2>/dev/null \
        || ac_curl "$API_BASE/files/$1/segments"
}

ac_list_files() {
    ac_curl "$API_BASE/files/" 2>/dev/null \
        || ac_curl "$API_BASE/files"
}

ac_list_speakers() {
    ac_curl "$API_BASE/speakers/" 2>/dev/null \
        || ac_curl "$API_BASE/speakers"
}

ac_search() {
    local q="$1"
    ac_curl -X POST "$API_BASE/search/" \
        -H "Content-Type: application/json" \
        -d "$(printf '{"query":"%s","page":1,"page_size":10}' "$q")"
}
