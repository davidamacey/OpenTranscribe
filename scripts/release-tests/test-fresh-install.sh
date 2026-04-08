#!/bin/bash
# Scenario A — fresh-install via the one-liner setup script.
#
# What this proves:
#   A brand-new user with no prior install can run the documented one-liner
#   (curl ... setup-opentranscribe.sh | bash) against the current release and
#   end up with a working stack: login, upload via URL, transcribe, search.
#
# Safety: hard-isolated from the live opentranscribe-* deployment via the
# guardrails harness. Read scripts/release-tests/lib/guardrails.sh and the
# README before running this for the first time.
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
LOCAL_IMAGE_TAG="${LOCAL_IMAGE_TAG:-0.4.0}"  # the tag built locally in Phase 3

# GPU policy: default to using GPU 1 (RTX 3080 Ti, free on this host).
# Override with TEST_USE_GPU=false to fall back to CPU-only.
TEST_USE_GPU="${TEST_USE_GPU:-true}"
TEST_GPU_DEVICE_ID="${TEST_GPU_DEVICE_ID:-1}"
export TEST_USE_GPU TEST_GPU_DEVICE_ID

# Ports — kept far away from the live 5173-5180 range
TEST_FRONTEND_PORT="${TEST_FRONTEND_PORT:-6173}"
TEST_BACKEND_PORT="${TEST_BACKEND_PORT:-6174}"
TEST_FLOWER_PORT="${TEST_FLOWER_PORT:-6175}"
TEST_POSTGRES_PORT="${TEST_POSTGRES_PORT:-6176}"
TEST_REDIS_PORT="${TEST_REDIS_PORT:-6177}"
TEST_MINIO_PORT="${TEST_MINIO_PORT:-6178}"
TEST_MINIO_CONSOLE_PORT="${TEST_MINIO_CONSOLE_PORT:-6179}"
TEST_OPENSEARCH_PORT="${TEST_OPENSEARCH_PORT:-6180}"
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
Env:
  TEST_PROJECT_NAME      default ot-reltest-fresh
  TEST_ROOT              default /mnt/nvm/opentranscribe-test-runs/<name>-<ts>
  TO_BRANCH              default master  (branch the one-liner pulls files from)
  LOCAL_IMAGE_TAG        default 0.4.0   (tag the test backend/frontend images use)
  TEST_FRONTEND_PORT..   default 6173-6180
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
# shellcheck source=lib/env-template.sh
source "$LIB_DIR/env-template.sh"
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

# ─── Helper: secrets file ───────────────────────────────────────────────────
ensure_secrets_file() {
    local f="$SCRIPT_DIR/.env.test-secrets"
    if [[ ! -f "$f" ]]; then
        cat > "$f" <<'EOF'
# Release-test secrets — gitignored. Fill in the keys below before running.
HUGGINGFACE_TOKEN=
# Optional LLM provider (leave blank to skip AI summarization assertions):
LLM_PROVIDER=
VLLM_BASE_URL=
VLLM_API_KEY=
VLLM_MODEL_NAME=
OPENAI_API_KEY=
OPENAI_MODEL_NAME=
EOF
        chmod 600 "$f"
        gr_die "created template at $f — fill it in (HUGGINGFACE_TOKEN required) and re-run"
    fi
    # shellcheck disable=SC1090
    source "$f"
    if [[ -z "${HUGGINGFACE_TOKEN:-}" ]]; then
        gr_die "HUGGINGFACE_TOKEN missing in $f — required for PyAnnote model download"
    fi
    export HUGGINGFACE_TOKEN
}

# ─── Phase implementations ──────────────────────────────────────────────────

phase_00_preflight() {
    ensure_secrets_file
    gr_preflight
}

phase_01_build_local_images() {
    # Intentionally tag ONLY :${LOCAL_IMAGE_TAG}, never :latest — retagging
    # :latest locally would affect the live production deployment on this host
    # if its containers ever restart.
    gr_log "checking for local image davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}"
    if docker image inspect "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" >/dev/null 2>&1; then
        gr_ok "backend image already present"
    else
        gr_log "building backend (this can take ~5-10 min)"
        docker build \
            -t "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" \
            -f "$REPO_ROOT/backend/Dockerfile.prod" \
            "$REPO_ROOT/backend"
    fi
    if docker image inspect "davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG}" >/dev/null 2>&1; then
        gr_ok "frontend image already present"
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
    bash "$REPO_ROOT/setup-opentranscribe.sh" || gr_die "one-liner failed"

    popd >/dev/null
}

phase_03_patch_compose() {
    local install_dir="$TEST_ROOT/install"
    # The one-liner installs into ./opentranscribe by default; relocate if needed.
    local target="$install_dir/opentranscribe"
    if [[ ! -d "$target" ]]; then
        # Some installs use the install_dir directly
        target="$install_dir"
    fi
    [[ -f "$target/docker-compose.yml" ]] || gr_die "no docker-compose.yml under $target"

    gr_log "patching compose files in $target"

    # Always work on copies; never edit upstream files
    cp "$target/docker-compose.yml" "$target/docker-compose.yml.bak"
    if [[ -f "$target/docker-compose.prod.yml" ]]; then
        cp "$target/docker-compose.prod.yml" "$target/docker-compose.prod.yml.bak"
    fi

    cp_apply_name_patch "$target/docker-compose.yml"
    cp_apply_volume_patch "$target/docker-compose.yml" \
        postgres_data minio_data redis_data opensearch_data flower_data
    cp_inject_labels "$target/docker-compose.yml" "$TEST_LABEL"
    cp_force_pull_policy "$target/docker-compose.yml" never

    # GPU overlay (optional): copy + label, no name patches needed because the
    # overlay only adds deploy.resources.devices stanzas to existing services.
    if [[ "$TEST_USE_GPU" == "true" && -f "$REPO_ROOT/docker-compose.gpu.yml" ]]; then
        cp "$REPO_ROOT/docker-compose.gpu.yml" "$target/docker-compose.gpu.yml"
        gr_ok "GPU overlay copied (will pin GPU $TEST_GPU_DEVICE_ID)"
    fi

    # Generate a fresh .env that overrides the one the installer wrote
    et_write_env "$target/.env"

    # Sanity-check every bind-mount source the patched compose will use
    python3 - "$target/docker-compose.yml" "$TEST_ROOT" <<'PY'
import sys, yaml
from pathlib import Path
data = yaml.safe_load(Path(sys.argv[1]).read_text())
test_root = Path(sys.argv[2]).resolve()
bad = []
for name, svc in (data.get("services") or {}).items():
    for vol in svc.get("volumes") or []:
        if isinstance(vol, dict):
            src = vol.get("source")
            kind = vol.get("type")
        elif isinstance(vol, str) and ":" in vol:
            src, _ = vol.split(":", 1)
            kind = "bind" if src.startswith(("/", ".")) else "volume"
        else:
            continue
        if kind == "bind" and src and src.startswith("/"):
            try:
                resolved = Path(src).resolve()
            except Exception:
                continue
            if not str(resolved).startswith(str(test_root)):
                bad.append(f"{name}: {src} → {resolved}")
if bad:
    print("ERROR: bind mounts escape TEST_ROOT:")
    for line in bad:
        print(" ", line)
    sys.exit(1)
PY
    gr_ok "compose patch passes mount-path firewall"
}

phase_04_start_stack() {
    local target="$TEST_ROOT/install/opentranscribe"
    [[ -d "$target" ]] || target="$TEST_ROOT/install"
    pushd "$target" >/dev/null
    local compose_args=(-f docker-compose.yml)
    if [[ "$TEST_USE_GPU" == "true" && -f docker-compose.gpu.yml ]]; then
        compose_args+=(-f docker-compose.gpu.yml)
        gr_log "docker compose up -d (GPU overlay enabled, GPU_DEVICE_ID=$TEST_GPU_DEVICE_ID)"
    else
        gr_log "docker compose up -d (CPU-only)"
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

    # Frontend smoke
    local fe_code
    fe_code=$(curl -o /dev/null -s -w '%{http_code}' "http://localhost:${TEST_FRONTEND_PORT}/")
    as_assert_http "frontend GET /" 200 "$fe_code"

    # API docs
    local api_code
    api_code=$(curl -o /dev/null -s -w '%{http_code}' "http://localhost:${TEST_BACKEND_PORT}/docs")
    as_assert_http "backend GET /docs" 200 "$api_code"

    # Upload from URL — read fixtures
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
                # Check transcript has segments
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

        # Search for a generic word
        local hits
        hits=$(ac_search "the" | python3 -c 'import sys, json; print(len((json.load(sys.stdin).get("hits") or json.load(sys.stdin).get("results") or [])))' 2>/dev/null || echo 0)
        as_assert_ge "hybrid search returns hits" "$hits" 1
    else
        as_record FAIL "missing fixtures/test-urls.txt"
    fi

    # Alembic head matches latest migration
    local alembic_head expected_head
    alembic_head=$(docker exec "${TEST_PROJECT_NAME}-postgres" \
        psql -U opentranscribe -d opentranscribe -tAc \
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
phase 03 phase_03_patch_compose
phase 04 phase_04_start_stack
phase 05 phase_05_wait_for_health
phase 06 phase_06_api_smoke

echo
echo "Done. Report: $TEST_ROOT/REPORT.md"
echo "Stack left running for inspection. Tear down with: $0 --cleanup"
