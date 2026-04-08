#!/bin/bash
# Scenario A — fresh-install via the one-liner setup script.
#
# Validates the documented one-liner end-to-end:
#   curl -fsSL .../setup-opentranscribe.sh | bash
#
# REQUIRES the live deployment to be stopped first (./opentr.sh stop) so the
# default container names and ports are available. The one-liner runs with
# its NORMAL defaults — same container names, same ports — so this is a
# faithful test of what a brand-new user would see.
#
# The only post-setup patching is to pin the locally-built :${LOCAL_IMAGE_TAG}
# image (because we haven't pushed 0.4.0 to Docker Hub yet) and force
# pull_policy: never. After Phase 5 of the release pipeline pushes the new
# tag to Docker Hub, this patching could be skipped entirely.
#
# Idempotent: phases are tracked under $TEST_ROOT/.phase/<phase>.done so
# re-running picks up where it left off. Pass --force to clear them.

set -euo pipefail

# ─── Locate library ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ─── Tunables (overridable via env) ─────────────────────────────────────────
TEST_SCENARIO="fresh-install"
TEST_PROJECT_NAME="${TEST_PROJECT_NAME:-ot-reltest-fresh}"
TEST_ROOT="${TEST_ROOT:-/mnt/nvm/opentranscribe-test-runs/${TEST_PROJECT_NAME}-$(date +%Y%m%d-%H%M%S)}"
TEST_LABEL="com.opentranscribe.release-test=${TEST_SCENARIO}"

TO_BRANCH="${TO_BRANCH:-master}"
LOCAL_IMAGE_TAG="${LOCAL_IMAGE_TAG:-0.4.0}"

# GPU policy: pin to GPU 1 (RTX 3080 Ti, free) — leaves GPU 0 (A6000) and
# GPU 2 (A6000, busy with LLM) untouched. Override with TEST_USE_GPU=false.
TEST_USE_GPU="${TEST_USE_GPU:-true}"
TEST_GPU_DEVICE_ID="${TEST_GPU_DEVICE_ID:-1}"
export TEST_USE_GPU TEST_GPU_DEVICE_ID

# Use the one-liner's default ports (5173-5180) since the live deployment
# is stopped. Override only if you have other services squatting these.
TEST_FRONTEND_PORT="${FRONTEND_PORT:-5173}"
TEST_BACKEND_PORT="${BACKEND_PORT:-5174}"
TEST_FLOWER_PORT="${FLOWER_PORT:-5175}"
TEST_POSTGRES_PORT="${POSTGRES_PORT:-5176}"
TEST_REDIS_PORT="${REDIS_PORT:-5177}"
TEST_MINIO_PORT="${MINIO_PORT:-5178}"
TEST_MINIO_CONSOLE_PORT="${MINIO_CONSOLE_PORT:-5179}"
TEST_OPENSEARCH_PORT="${OPENSEARCH_PORT:-5180}"
TEST_PORTS="$TEST_FRONTEND_PORT $TEST_BACKEND_PORT $TEST_FLOWER_PORT $TEST_POSTGRES_PORT $TEST_REDIS_PORT $TEST_MINIO_PORT $TEST_MINIO_CONSOLE_PORT $TEST_OPENSEARCH_PORT"

# Test admin user
TEST_ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-reltest-fresh@opentranscribe.local}"
TEST_ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-ReleaseTest!2026}"

# Cleanup mode
DO_CLEANUP=0
DO_FORCE=0

# ─── Argument parsing ───────────────────────────────────────────────────────
while (( $# > 0 )); do
    case "$1" in
        --cleanup)   DO_CLEANUP=1 ;;
        --force)     DO_FORCE=1 ;;
        --yes)       export OT_RELEASE_TEST_YES=1 ;;
        --help|-h)
            cat <<EOF
Usage: $0 [--cleanup] [--force] [--yes]

Prerequisite: stop the live deployment first with \`./opentr.sh stop\`.
After the test, restart it with \`./opentr.sh start dev\` (or whichever
mode you were using).

Env:
  TEST_PROJECT_NAME      default ot-reltest-fresh  (used as label namespace)
  TEST_ROOT              default /mnt/nvm/opentranscribe-test-runs/<name>-<ts>
  TO_BRANCH              default master  (branch the one-liner pulls files from)
  LOCAL_IMAGE_TAG        default 0.4.0   (locally built tag the test pins)
  TEST_USE_GPU           default true
  TEST_GPU_DEVICE_ID     default 1       (RTX 3080 Ti, leaves A6000 free)
EOF
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

export TEST_SCENARIO TEST_PROJECT_NAME TEST_ROOT TEST_LABEL
export TEST_FRONTEND_PORT TEST_BACKEND_PORT TEST_FLOWER_PORT TEST_POSTGRES_PORT \
       TEST_REDIS_PORT TEST_MINIO_PORT TEST_MINIO_CONSOLE_PORT TEST_OPENSEARCH_PORT \
       TEST_PORTS

# ─── Source library ─────────────────────────────────────────────────────────
# shellcheck source=lib/guardrails.sh
source "$LIB_DIR/guardrails.sh"
# shellcheck source=lib/compose-patch.sh
source "$LIB_DIR/compose-patch.sh"
# shellcheck source=lib/api-client.sh
source "$LIB_DIR/api-client.sh"
# shellcheck source=lib/assertions.sh
source "$LIB_DIR/assertions.sh"

# ─── Cleanup mode ───────────────────────────────────────────────────────────
if (( DO_CLEANUP == 1 )); then
    gr_log "cleanup requested"
    gr_cleanup
    exit 0
fi

# ─── Phase tracking ─────────────────────────────────────────────────────────
PHASE_DIR="$TEST_ROOT/.phase"
phase_done()  { mkdir -p "$PHASE_DIR"; touch "$PHASE_DIR/$1.done"; }
phase_check() { [[ -f "$PHASE_DIR/$1.done" && $DO_FORCE -eq 0 ]]; }
phase()       { local n="$1"; shift
                if phase_check "$n"; then
                    echo -e "\033[0;33m[skip]\033[0m phase $n already complete"
                    return
                fi
                echo -e "\n\033[1;34m═══ phase $n ═══\033[0m"
                "$@"
                phase_done "$n"
              }

# ─── Helpers ────────────────────────────────────────────────────────────────
ensure_secrets_file() {
    local f="$SCRIPT_DIR/.env.test-secrets"
    if [[ ! -f "$f" ]]; then
        cp "$SCRIPT_DIR/.env.test-secrets.example" "$f"
        chmod 600 "$f"
        gr_die "created template at $f — fill in HUGGINGFACE_TOKEN and re-run"
    fi
    # shellcheck disable=SC1090
    source "$f"
    if [[ -z "${HUGGINGFACE_TOKEN:-}" ]]; then
        gr_die "HUGGINGFACE_TOKEN missing in $f — required for PyAnnote model download"
    fi
    export HUGGINGFACE_TOKEN
}

ensure_live_deployment_stopped() {
    # Refuse to run if any opentranscribe-* container is still up — would
    # collide with the one-liner's default container names.
    local running
    running=$(docker ps --format '{{.Names}}' --filter 'name=^opentranscribe-' || true)
    if [[ -n "$running" ]]; then
        gr_die "live deployment is still running:
$running

Stop it first with: ./opentr.sh stop
(this preserves all data — postgres bind mount, NAS minio, named volumes)"
    fi
    # Also refuse if there are stopped opentranscribe-* containers (would
    # collide on container_name during create).
    local stopped
    stopped=$(docker ps -a --format '{{.Names}}' --filter 'name=^opentranscribe-' || true)
    if [[ -n "$stopped" ]]; then
        gr_warn "removing stopped (already-down) live containers to free names: $stopped"
        docker rm $stopped >/dev/null
    fi
    gr_ok "no opentranscribe-* containers exist; safe to start the test stack"
}

# ─── Phase implementations ──────────────────────────────────────────────────

phase_00_preflight() {
    ensure_secrets_file
    gr_preflight
    ensure_live_deployment_stopped
}

phase_01_build_local_images() {
    # Intentionally tag ONLY :${LOCAL_IMAGE_TAG}, never :latest.
    if docker image inspect "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" >/dev/null 2>&1; then
        gr_ok "backend image davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG} already present"
    else
        gr_log "building backend (this can take ~5-10 min)"
        docker build \
            -t "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" \
            -f "$REPO_ROOT/backend/Dockerfile.prod" \
            "$REPO_ROOT/backend"
    fi
    if docker image inspect "davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG}" >/dev/null 2>&1; then
        gr_ok "frontend image davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG} already present"
    else
        gr_log "building frontend"
        docker build \
            -t "davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG}" \
            -f "$REPO_ROOT/frontend/Dockerfile.prod" \
            "$REPO_ROOT/frontend"
    fi
    docker image inspect "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" \
        --format 'backend digest: {{.Id}}' | tee "$TEST_ROOT/image-digests.txt"
    docker image inspect "davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG}" \
        --format 'frontend digest: {{.Id}}' | tee -a "$TEST_ROOT/image-digests.txt"
}

phase_02_run_one_liner() {
    local install_dir="$TEST_ROOT/install"
    mkdir -p "$install_dir"
    pushd "$install_dir" >/dev/null

    gr_log "running setup-opentranscribe.sh from branch $TO_BRANCH in unattended mode"
    OPENTRANSCRIBE_BRANCH="$TO_BRANCH" \
    OPENTRANSCRIBE_UNATTENDED=1 \
    HUGGINGFACE_TOKEN="$HUGGINGFACE_TOKEN" \
    WHISPER_MODEL="${WHISPER_MODEL:-large-v3-turbo}" \
    OPENSEARCH_MODELS="${OPENSEARCH_MODELS:-all-MiniLM-L6-v2}" \
    GPU_DEVICE_ID="$TEST_GPU_DEVICE_ID" \
    bash "$REPO_ROOT/setup-opentranscribe.sh" || gr_die "one-liner failed"

    popd >/dev/null
}

phase_03_pin_local_image() {
    # Minimal post-setup patch: pin :${LOCAL_IMAGE_TAG}, force pull_policy: never,
    # inject the release-test label so cleanup can find managed resources.
    # No name/port/volume rewrites — the one-liner's defaults are used as-is
    # because the live deployment is stopped.
    local target="$TEST_ROOT/install/opentranscribe"
    [[ -d "$target" ]] || target="$TEST_ROOT/install"
    [[ -f "$target/docker-compose.prod.yml" ]] || gr_die "no docker-compose.prod.yml under $target"

    cp "$target/docker-compose.prod.yml" "$target/docker-compose.prod.yml.bak"

    cp_force_pull_policy "$target/docker-compose.prod.yml" never
    cp_inject_labels "$target/docker-compose.prod.yml" "$TEST_LABEL"
    cp_pin_image_tag "$target/docker-compose.prod.yml" backend "$LOCAL_IMAGE_TAG"
    cp_pin_image_tag "$target/docker-compose.prod.yml" frontend "$LOCAL_IMAGE_TAG"
    for svc in celery-worker celery-cpu-worker celery-nlp-worker celery-embedding-worker celery-download-worker celery-beat flower; do
        cp_pin_image_tag "$target/docker-compose.prod.yml" "$svc" "$LOCAL_IMAGE_TAG" 2>/dev/null || true
    done

    # Also label the base file's services for cleanup symmetry
    cp "$target/docker-compose.yml" "$target/docker-compose.yml.bak"
    cp_inject_labels "$target/docker-compose.yml" "$TEST_LABEL"

    # Override GPU_DEVICE_ID in the .env if a non-default was requested
    if [[ "$TEST_GPU_DEVICE_ID" != "0" ]]; then
        if grep -q '^GPU_DEVICE_ID=' "$target/.env"; then
            sed -i.bak "s|^GPU_DEVICE_ID=.*|GPU_DEVICE_ID=$TEST_GPU_DEVICE_ID|" "$target/.env"
            rm -f "$target/.env.bak"
        else
            echo "GPU_DEVICE_ID=$TEST_GPU_DEVICE_ID" >> "$target/.env"
        fi
        gr_ok "pinned GPU_DEVICE_ID=$TEST_GPU_DEVICE_ID in .env"
    fi
    gr_ok "image tag pinned to :${LOCAL_IMAGE_TAG}, pull_policy=never, label injected"
}

phase_04_start_stack() {
    local target="$TEST_ROOT/install/opentranscribe"
    [[ -d "$target" ]] || target="$TEST_ROOT/install"
    pushd "$target" >/dev/null
    local compose_args=(-f docker-compose.yml -f docker-compose.prod.yml)
    if [[ "$TEST_USE_GPU" == "true" && -f docker-compose.gpu.yml ]]; then
        compose_args+=(-f docker-compose.gpu.yml)
        gr_log "docker compose up -d (base + prod + gpu, GPU_DEVICE_ID=$TEST_GPU_DEVICE_ID)"
    else
        gr_log "docker compose up -d (base + prod, CPU)"
    fi
    docker compose "${compose_args[@]}" up -d
    popd >/dev/null
}

phase_05_wait_for_health() {
    API_BASE="http://localhost:${TEST_BACKEND_PORT}/api"
    export API_BASE
    ac_wait_for_health 900
}

phase_06_api_smoke() {
    API_BASE="http://localhost:${TEST_BACKEND_PORT}/api"
    export API_BASE
    TEST_REPORT_FILE="$TEST_ROOT/REPORT.md"
    : > "$TEST_REPORT_FILE"
    {
        echo "# Release Test Report — $TEST_SCENARIO"
        echo ""
        echo "- Project: $TEST_PROJECT_NAME"
        echo "- Test root: $TEST_ROOT"
        echo "- Branch: $TO_BRANCH"
        echo "- Image tag: $LOCAL_IMAGE_TAG"
        echo "- Started: $(date -Iseconds)"
        echo ""
        echo "| Status | Assertion | Detail |"
        echo "|---|---|---|"
    } >> "$TEST_REPORT_FILE"
    export TEST_REPORT_FILE

    ac_register_admin "$TEST_ADMIN_EMAIL" "$TEST_ADMIN_PASSWORD"
    ac_login "$TEST_ADMIN_EMAIL" "$TEST_ADMIN_PASSWORD"

    local fe_code
    fe_code=$(curl -o /dev/null -s -w '%{http_code}' "http://localhost:${TEST_FRONTEND_PORT}/")
    as_assert_http "frontend GET /" 200 "$fe_code"

    local api_code
    api_code=$(curl -o /dev/null -s -w '%{http_code}' "http://localhost:${TEST_BACKEND_PORT}/docs")
    as_assert_http "backend GET /docs" 200 "$api_code"

    local urls_file="$SCRIPT_DIR/fixtures/test-urls.txt"
    if [[ -f "$urls_file" ]]; then
        local file_ids=()
        while IFS= read -r url; do
            [[ -z "$url" || "$url" == \#* ]] && continue
            local fid
            fid=$(ac_upload_from_url "$url") || { as_record FAIL "upload $url"; continue; }
            file_ids+=("$fid")
            as_record PASS "upload accepted: $url (file_id=$fid)"
        done < "$urls_file"

        for fid in "${file_ids[@]}"; do
            if ac_wait_for_file_status "$fid" 1800; then
                as_record PASS "transcription completed for file $fid"
                local seg_count
                seg_count=$(ac_get_transcript "$fid" | python3 -c '
import sys, json
data = json.load(sys.stdin)
segs = data.get("segments") or data.get("transcript_segments") or []
print(len(segs))
' 2>/dev/null || echo 0)
                as_assert_ge "segments[] non-empty for $fid" "$seg_count" 1
            else
                as_record FAIL "transcription for file $fid"
            fi
        done

        local hits
        hits=$(ac_search "the" | python3 -c 'import sys, json; print(len((json.load(sys.stdin).get("hits") or json.load(sys.stdin).get("results") or [])))' 2>/dev/null || echo 0)
        as_assert_ge "hybrid search returns hits" "$hits" 1
    else
        as_record FAIL "missing fixtures/test-urls.txt"
    fi

    # Alembic head check (one-liner uses the standard 'opentranscribe-postgres' name)
    local alembic_head expected_head
    alembic_head=$(docker exec opentranscribe-postgres \
        psql -U postgres -d opentranscribe -tAc \
        "SELECT version_num FROM alembic_version" 2>/dev/null || echo "")
    expected_head=$(grep -hE "^revision[[:space:]]*=" "$REPO_ROOT/backend/alembic/versions/"*.py \
        | tail -1 | awk -F'"' '{print $2}')
    as_assert_eq "alembic head" "$expected_head" "$alembic_head"

    as_summary | tee -a "$TEST_REPORT_FILE"
    {
        echo ""
        echo "Finished: $(date -Iseconds)"
    } >> "$TEST_REPORT_FILE"
}

# ─── Driver ─────────────────────────────────────────────────────────────────
mkdir -p "$TEST_ROOT"
exec > >(tee -a "$TEST_ROOT/run.log") 2>&1

echo "OpenTranscribe Release Test — Scenario A (fresh install)"
echo "Started: $(date -Iseconds)"
echo "Repo:    $REPO_ROOT (commit $(git -C "$REPO_ROOT" rev-parse --short HEAD))"
echo

phase 00 phase_00_preflight
phase 01 phase_01_build_local_images
phase 02 phase_02_run_one_liner
phase 03 phase_03_pin_local_image
phase 04 phase_04_start_stack
phase 05 phase_05_wait_for_health
phase 06 phase_06_api_smoke

echo
echo "Done. Report: $TEST_ROOT/REPORT.md"
echo "Stack left running for inspection. Tear down with: $0 --cleanup"
echo "Then restart your live deployment with: ./opentr.sh start dev"
