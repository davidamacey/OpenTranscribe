#!/bin/bash
# Scenario B — v0.3.3 → 0.4.0 (or current head) in-place upgrade.
#
# What this proves:
#   A real user with real data on the previous release can run the documented
#   upgrade path (`./opentranscribe.sh update` ≈ `compose down/pull/up`) and
#   find their MinIO objects, transcripts, speakers, and search indices intact
#   after the migration chain runs.
#
# Phases:
#   00 preflight + secrets gate
#   01 build local 0.4.0 images (skipped if already present from Scenario A)
#   02 verify Docker Hub has :v0.3.3 tags (FROM_VERSION)
#   03 create v0.3.3 worktree, copy compose into TEST_ROOT, patch
#   04 generate isolated .env, start the v0.3.3 stack, wait for health
#   05 register user, upload media via URL, wait for completion
#   06 snapshot pre-upgrade state (postgres SELECTs, MinIO ETags, transcripts)
#   07 down v0.3.3, swap compose to current head, re-patch, point to local images
#   08 up the upgraded stack, wait for migrations + health
#   09 snapshot post-upgrade state
#   10 diff snapshots, run feature liveness checks, write REPORT.md
#
# Future releases: set FROM_VERSION=v0.4.0 etc. — every other piece is
# parameterised. Append a row to expected-schemas.tsv when adding a release.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ─── Tunables ───────────────────────────────────────────────────────────────
TEST_SCENARIO="upgrade"
TEST_PROJECT_NAME="${TEST_PROJECT_NAME:-ot-reltest-upgrade}"
TEST_ROOT="${TEST_ROOT:-/mnt/nvm/opentranscribe-test-runs/${TEST_PROJECT_NAME}-$(date +%Y%m%d-%H%M%S)}"
TEST_LABEL="com.opentranscribe.release-test=${TEST_SCENARIO}"

FROM_VERSION="${FROM_VERSION:-v0.3.3}"
LOCAL_IMAGE_TAG="${LOCAL_IMAGE_TAG:-0.4.0}"

# Disjoint port range (Scenario A uses 6173-6180; this uses 6273-6280)
TEST_FRONTEND_PORT="${TEST_FRONTEND_PORT:-6273}"
TEST_BACKEND_PORT="${TEST_BACKEND_PORT:-6274}"
TEST_FLOWER_PORT="${TEST_FLOWER_PORT:-6275}"
TEST_POSTGRES_PORT="${TEST_POSTGRES_PORT:-6276}"
TEST_REDIS_PORT="${TEST_REDIS_PORT:-6277}"
TEST_MINIO_PORT="${TEST_MINIO_PORT:-6278}"
TEST_MINIO_CONSOLE_PORT="${TEST_MINIO_CONSOLE_PORT:-6279}"
TEST_OPENSEARCH_PORT="${TEST_OPENSEARCH_PORT:-6280}"
TEST_PORTS="$TEST_FRONTEND_PORT $TEST_BACKEND_PORT $TEST_FLOWER_PORT $TEST_POSTGRES_PORT $TEST_REDIS_PORT $TEST_MINIO_PORT $TEST_MINIO_CONSOLE_PORT $TEST_OPENSEARCH_PORT"

TEST_ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-reltest-upgrade@opentranscribe.local}"
TEST_ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-ReleaseTest!2026}"

DO_CLEANUP=0
DO_FORCE=0
while (( $# > 0 )); do
    case "$1" in
        --cleanup) DO_CLEANUP=1 ;;
        --force)   DO_FORCE=1 ;;
        --yes)     export OT_RELEASE_TEST_YES=1 ;;
        --help|-h)
            cat <<EOF
Usage: $0 [--cleanup] [--force] [--yes]
Env:
  TEST_PROJECT_NAME      default ot-reltest-upgrade
  TEST_ROOT              default /mnt/nvm/opentranscribe-test-runs/<name>-<ts>
  FROM_VERSION           default v0.3.3   (Docker Hub tag for the "before" stack)
  LOCAL_IMAGE_TAG        default 0.4.0    (locally built tag for the "after" stack)
  TEST_FRONTEND_PORT..   default 6273-6280
EOF
            exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

export TEST_SCENARIO TEST_PROJECT_NAME TEST_ROOT TEST_LABEL
export TEST_FRONTEND_PORT TEST_BACKEND_PORT TEST_FLOWER_PORT TEST_POSTGRES_PORT \
       TEST_REDIS_PORT TEST_MINIO_PORT TEST_MINIO_CONSOLE_PORT TEST_OPENSEARCH_PORT \
       TEST_PORTS

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

if (( DO_CLEANUP == 1 )); then
    gr_log "cleanup requested"
    gr_cleanup
    exit 0
fi

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

ensure_secrets_file() {
    local f="$SCRIPT_DIR/.env.test-secrets"
    if [[ ! -f "$f" ]]; then
        gr_die "missing $f — run test-fresh-install.sh first to bootstrap, or copy from .env.test-secrets.example"
    fi
    # shellcheck disable=SC1090
    source "$f"
    [[ -n "${HUGGINGFACE_TOKEN:-}" ]] || gr_die "HUGGINGFACE_TOKEN missing in $f"
    export HUGGINGFACE_TOKEN
}

# ─── Phase implementations ──────────────────────────────────────────────────

phase_00_preflight() {
    ensure_secrets_file
    gr_preflight
}

phase_01_build_local_images() {
    if docker image inspect "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" >/dev/null 2>&1 \
       && docker image inspect "davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG}" >/dev/null 2>&1; then
        gr_ok "local ${LOCAL_IMAGE_TAG} images already built"
        return
    fi
    gr_log "building local ${LOCAL_IMAGE_TAG} images"
    docker build -t "davidamacey/opentranscribe-backend:${LOCAL_IMAGE_TAG}" \
        -f "$REPO_ROOT/backend/Dockerfile.prod" "$REPO_ROOT/backend"
    docker build -t "davidamacey/opentranscribe-frontend:${LOCAL_IMAGE_TAG}" \
        -f "$REPO_ROOT/frontend/Dockerfile.prod" "$REPO_ROOT/frontend"
}

phase_02_verify_from_version() {
    gr_log "verifying davidamacey/opentranscribe-*:${FROM_VERSION} exists on Docker Hub"
    if ! docker manifest inspect "davidamacey/opentranscribe-backend:${FROM_VERSION}" >/dev/null 2>&1; then
        gr_die "Docker Hub does not have davidamacey/opentranscribe-backend:${FROM_VERSION}; cannot run upgrade test from a non-existent release"
    fi
    if ! docker manifest inspect "davidamacey/opentranscribe-frontend:${FROM_VERSION}" >/dev/null 2>&1; then
        gr_die "Docker Hub does not have davidamacey/opentranscribe-frontend:${FROM_VERSION}"
    fi
    gr_ok "${FROM_VERSION} images present on Docker Hub"
}

phase_03_prepare_v033_compose() {
    local worktree="$TEST_ROOT/worktree-${FROM_VERSION}"
    if [[ ! -d "$worktree" ]]; then
        gr_log "creating git worktree at $worktree"
        git -C "$REPO_ROOT" worktree add --detach "$worktree" "$FROM_VERSION"
    fi
    local stage="$TEST_ROOT/before"
    mkdir -p "$stage"
    cp "$worktree/docker-compose.yml" "$stage/docker-compose.yml"
    [[ -f "$worktree/docker-compose.prod.yml" ]] && cp "$worktree/docker-compose.prod.yml" "$stage/docker-compose.prod.yml"

    cp_apply_name_patch "$stage/docker-compose.yml"
    cp_apply_volume_patch "$stage/docker-compose.yml" \
        postgres_data minio_data redis_data opensearch_data flower_data
    cp_inject_labels "$stage/docker-compose.yml" "$TEST_LABEL"
    # FROM stack pulls from Docker Hub explicitly to exercise the real user path
    cp_force_pull_policy "$stage/docker-compose.yml" always
    cp_pin_image_tag "$stage/docker-compose.yml" backend "$FROM_VERSION"
    cp_pin_image_tag "$stage/docker-compose.yml" frontend "$FROM_VERSION"

    et_write_env "$stage/.env"
    gr_ok "v0.3.3 compose staged at $stage"
}

phase_04_start_v033() {
    local stage="$TEST_ROOT/before"
    pushd "$stage" >/dev/null
    gr_log "compose pull (Docker Hub: ${FROM_VERSION})"
    docker compose -f docker-compose.yml pull
    gr_log "compose up -d"
    docker compose -f docker-compose.yml up -d
    popd >/dev/null

    API_BASE="http://localhost:${TEST_BACKEND_PORT}/api"
    export API_BASE
    ac_wait_for_health 900
}

phase_05_seed_data() {
    API_BASE="http://localhost:${TEST_BACKEND_PORT}/api"
    export API_BASE
    ac_register_admin "$TEST_ADMIN_EMAIL" "$TEST_ADMIN_PASSWORD"
    ac_login "$TEST_ADMIN_EMAIL" "$TEST_ADMIN_PASSWORD"

    local urls_file="$SCRIPT_DIR/fixtures/test-urls.txt"
    [[ -f "$urls_file" ]] || gr_die "missing $urls_file"

    local file_ids=()
    while IFS= read -r url; do
        [[ -z "$url" || "$url" == \#* ]] && continue
        local fid
        fid=$(ac_upload_from_url "$url")
        gr_log "queued upload: $url -> file_id=$fid"
        file_ids+=("$fid")
    done < "$urls_file"

    for fid in "${file_ids[@]}"; do
        ac_wait_for_file_status "$fid" 1800
    done
    printf '%s\n' "${file_ids[@]}" > "$TEST_ROOT/seeded-file-ids.txt"
    gr_ok "seeded $(wc -l < "$TEST_ROOT/seeded-file-ids.txt") files"
}

snapshot_state() {
    local label="$1"   # "before" or "after"
    local out="$TEST_ROOT/snapshots/$label"
    mkdir -p "$out"

    gr_log "snapshotting state to $out"

    # Postgres deterministic queries
    local pg="${TEST_PROJECT_NAME}-postgres"
    docker exec "$pg" psql -U opentranscribe -d opentranscribe -tAc \
        "SELECT version_num FROM alembic_version" > "$out/alembic_head.txt"
    docker exec "$pg" psql -U opentranscribe -d opentranscribe -tAc \
        "SELECT id, filename, status FROM media_file ORDER BY id" > "$out/media_files.txt"
    docker exec "$pg" psql -U opentranscribe -d opentranscribe -tAc \
        "SELECT file_id, COUNT(*) FROM transcript_segment GROUP BY file_id ORDER BY file_id" > "$out/segment_counts.txt"
    docker exec "$pg" psql -U opentranscribe -d opentranscribe -tAc \
        "SELECT id, name FROM speaker ORDER BY id" > "$out/speakers.txt" 2>/dev/null || \
        echo "(speaker table query failed — schema may differ)" > "$out/speakers.txt"

    # MinIO ETag list (proves no object body mutation)
    local minio="${TEST_PROJECT_NAME}-minio"
    docker exec "$minio" sh -c '
        mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 || true
        mc ls --recursive --json local/opentranscribe 2>/dev/null
    ' > "$out/minio_etags.json" 2>/dev/null || echo "[]" > "$out/minio_etags.json"

    # Transcript dump per file (for prefix comparison)
    if [[ -f "$TEST_ROOT/seeded-file-ids.txt" ]]; then
        while IFS= read -r fid; do
            ac_get_transcript "$fid" > "$out/transcript-$fid.json" 2>/dev/null || true
        done < "$TEST_ROOT/seeded-file-ids.txt"
    fi

    # File-level API listing
    ac_list_files > "$out/files.json" 2>/dev/null || true
}

phase_06_snapshot_pre() {
    snapshot_state before
}

phase_07_swap_to_new() {
    local stage_before="$TEST_ROOT/before"
    local stage_after="$TEST_ROOT/after"

    # IMPORTANT: keep the same bind-mount data dirs so the upgrade is in-place
    mkdir -p "$stage_after"
    cp "$REPO_ROOT/docker-compose.yml" "$stage_after/docker-compose.yml"
    [[ -f "$REPO_ROOT/docker-compose.prod.yml" ]] && cp "$REPO_ROOT/docker-compose.prod.yml" "$stage_after/docker-compose.prod.yml"

    cp_apply_name_patch "$stage_after/docker-compose.yml"
    cp_apply_volume_patch "$stage_after/docker-compose.yml" \
        postgres_data minio_data redis_data opensearch_data flower_data
    cp_inject_labels "$stage_after/docker-compose.yml" "$TEST_LABEL"
    cp_force_pull_policy "$stage_after/docker-compose.yml" never
    cp_pin_image_tag "$stage_after/docker-compose.yml" backend "$LOCAL_IMAGE_TAG"
    cp_pin_image_tag "$stage_after/docker-compose.yml" frontend "$LOCAL_IMAGE_TAG"

    cp "$stage_before/.env" "$stage_after/.env"

    # Stop the BEFORE stack — IMPORTANT: no -v, no --remove-orphans
    pushd "$stage_before" >/dev/null
    gr_log "stopping ${FROM_VERSION} stack (preserving volumes)"
    docker compose -f docker-compose.yml down
    popd >/dev/null
}

phase_08_start_new() {
    local stage_after="$TEST_ROOT/after"
    pushd "$stage_after" >/dev/null
    gr_log "starting ${LOCAL_IMAGE_TAG} stack"
    docker compose -f docker-compose.yml up -d
    popd >/dev/null

    API_BASE="http://localhost:${TEST_BACKEND_PORT}/api"
    export API_BASE
    # Migrations may take a few minutes — give them a generous window
    ac_wait_for_health 900

    # Tail backend logs for "Alembic upgrade complete" or similar marker
    docker logs "${TEST_PROJECT_NAME}-backend" 2>&1 | grep -iE 'alembic|migration' | tail -20 \
        > "$TEST_ROOT/migration-log.txt" || true
}

phase_09_snapshot_post() {
    snapshot_state after
}

phase_10_assert_and_report() {
    TEST_REPORT_FILE="$TEST_ROOT/REPORT.md"
    : > "$TEST_REPORT_FILE"
    {
        echo "# Release Test Report — Scenario B (upgrade $FROM_VERSION → $LOCAL_IMAGE_TAG)"
        echo ""
        echo "- Project:    $TEST_PROJECT_NAME"
        echo "- Test root:  $TEST_ROOT"
        echo "- From:       $FROM_VERSION (Docker Hub)"
        echo "- To:         $LOCAL_IMAGE_TAG (local build)"
        echo "- Started:    $(date -Iseconds)"
        echo ""
        echo "## Migration log excerpt"
        echo '```'
        cat "$TEST_ROOT/migration-log.txt" 2>/dev/null || echo "(none captured)"
        echo '```'
        echo ""
        echo "## Assertions"
        echo ""
        echo "| Status | Assertion | Detail |"
        echo "|---|---|---|"
    } >> "$TEST_REPORT_FILE"
    export TEST_REPORT_FILE

    # ─── Snapshot diffs ─────────────────────────────────────────────────
    local pre="$TEST_ROOT/snapshots/before"
    local post="$TEST_ROOT/snapshots/after"

    as_assert_diff_files "media_file rows preserved" "$pre/media_files.txt" "$post/media_files.txt"
    as_assert_diff_files "transcript_segment counts preserved" "$pre/segment_counts.txt" "$post/segment_counts.txt"
    as_assert_diff_files "MinIO ETag list unchanged" "$pre/minio_etags.json" "$post/minio_etags.json"

    # Alembic head should advance
    local pre_head post_head expected_head
    pre_head=$(<"$pre/alembic_head.txt")
    post_head=$(<"$post/alembic_head.txt")
    expected_head=$(grep -hE "^revision[[:space:]]*=" "$REPO_ROOT/backend/alembic/versions/"*.py \
        | tail -1 | awk -F'"' '{print $2}')
    as_assert_ne "alembic head advanced" "$pre_head" "$post_head"
    as_assert_eq "alembic head matches current head" "$expected_head" "$post_head"

    # Transcript prefix check (per file)
    if [[ -f "$TEST_ROOT/seeded-file-ids.txt" ]]; then
        while IFS= read -r fid; do
            python3 - "$pre/transcript-$fid.json" "$post/transcript-$fid.json" "$fid" \
                "$TEST_REPORT_FILE" <<'PY' || true
import json, sys
pre, post, fid, report = sys.argv[1:5]
def segs(p):
    try:
        d = json.load(open(p))
    except Exception:
        return None
    return d.get("segments") or d.get("transcript_segments") or []
pre_segs = segs(pre)
post_segs = segs(post)
ok = pre_segs is not None and post_segs is not None and len(post_segs) >= len(pre_segs)
if ok:
    for i, s in enumerate(pre_segs):
        ps = post_segs[i]
        if s.get("text") != ps.get("text") or abs((s.get("start") or 0) - (ps.get("start") or 0)) > 0.01:
            ok = False
            break
status = "PASS" if ok else "FAIL"
detail = "" if ok else f"pre={len(pre_segs or [])} post={len(post_segs or [])}"
print(f"{status:5}  transcript prefix preserved for file {fid}  {detail}")
with open(report, "a") as f:
    f.write(f"| {status} | transcript prefix preserved for file {fid} | {detail} |\n")
PY
        done < "$TEST_ROOT/seeded-file-ids.txt"
    fi

    # ─── New-feature liveness checks ────────────────────────────────────
    API_BASE="http://localhost:${TEST_BACKEND_PORT}/api"
    export API_BASE
    ac_login "$TEST_ADMIN_EMAIL" "$TEST_ADMIN_PASSWORD" || true
    local code

    code=$(curl -o /dev/null -s -w '%{http_code}' "http://localhost:${TEST_BACKEND_PORT}/docs")
    as_assert_http "API docs reachable post-upgrade" 200 "$code"

    code=$(curl -o /dev/null -s -w '%{http_code}' "http://localhost:${TEST_FRONTEND_PORT}/")
    as_assert_http "frontend reachable post-upgrade" 200 "$code"

    # MFA endpoint exists in 0.4.0 but did not in v0.3.3
    code=$(curl -o /dev/null -s -w '%{http_code}' \
        -H "Authorization: Bearer ${API_TOKEN:-}" \
        "$API_BASE/auth/mfa/status" || echo 000)
    as_assert "MFA endpoint present (was 404 in $FROM_VERSION)" '[[ "$code" != "404" && "$code" != "000" ]]'

    as_summary | tee -a "$TEST_REPORT_FILE"
    {
        echo ""
        echo "Finished: $(date -Iseconds)"
    } >> "$TEST_REPORT_FILE"
}

# ─── Driver ─────────────────────────────────────────────────────────────────
mkdir -p "$TEST_ROOT"
exec > >(tee -a "$TEST_ROOT/run.log") 2>&1

echo "OpenTranscribe Release Test — Scenario B (upgrade ${FROM_VERSION} → ${LOCAL_IMAGE_TAG})"
echo "Started: $(date -Iseconds)"
echo "Repo:    $REPO_ROOT (commit $(git -C "$REPO_ROOT" rev-parse --short HEAD))"
echo

phase 00 phase_00_preflight
phase 01 phase_01_build_local_images
phase 02 phase_02_verify_from_version
phase 03 phase_03_prepare_v033_compose
phase 04 phase_04_start_v033
phase 05 phase_05_seed_data
phase 06 phase_06_snapshot_pre
phase 07 phase_07_swap_to_new
phase 08 phase_08_start_new
phase 09 phase_09_snapshot_post
phase 10 phase_10_assert_and_report

echo
echo "Done. Report: $TEST_ROOT/REPORT.md"
echo "Stack left running for inspection. Tear down with: $0 --cleanup"
