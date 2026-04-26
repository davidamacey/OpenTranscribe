# Upload-Speed-Improvement Benchmark — Agent Handoff

> **Purpose of this file:** A self-contained briefing so a fresh agent (Sonnet or otherwise) can pick up the upload-speed A/B benchmark **without any prior conversation context**. Every command, every expected output, every decision point is spelled out below. If something here is unclear, stop and ask David before improvising.

---

## 📍 Where this document lives — and how to get here

**This file only exists on the `feat/upload-speed-improvement` branch.** If you're reading it, you're already on that branch. Good.

After the host reboot, the checked-out branch will be `feat/upload-speed-improvement` (commit `73b9aa5` or later). David's instruction to the new agent is: **"Read `docs/UPLOAD_SPEED_BENCHMARK_HANDOFF.md`"**.

The benchmark work starts by switching to `master` for the baseline run — but that's **Step 7.2**, AFTER you've finished reading this whole document. Do NOT run `git checkout master` before finishing the read, or you'll lose access to this doc and the scripts it describes.

Verify you're on the right branch before doing anything else:

```bash
cd /mnt/nvm/repos/transcribe-app
git branch --show-current                          # → feat/upload-speed-improvement
ls docs/UPLOAD_SPEED_BENCHMARK_HANDOFF.md          # → file exists
ls scripts/benchmark_upload_baseline.py scripts/benchmark_upload_matrix.py   # → both exist
```

If any of those checks fail, stop and tell David — the tree state doesn't match this doc.

---

## ⚠️ STOP — READ THIS FIRST

**Two reboots have already happened on this machine because of CUDA misuse.** This is the single most important rule:

| Rule | Why |
|---|---|
| **Never `pkill`, `kill -9`, or `docker kill` any container/process that uses CUDA.** | Abrupt process death leaves CUDA contexts half-destroyed → XID fault → host reboot |
| Use `docker stop <container>` or `./opentr.sh stop` and let it drain. | Graceful shutdown flushes CUDA contexts cleanly |
| **Never run NVIDIA driver-recovery commands** (`nvidia-smi -r`, `rmmod nvidia_uvm`, `modprobe`, anything in `/sys/bus/pci/`). | Suggest them to David. He runs them. |
| **For this benchmark, dispatch is sequential — one fixture at a time.** | Concurrent GPU runs are valid for OTHER tests (`benchmark_concurrent_uploads.py`). Not this one. |
| **Run `nvidia-smi` before any benchmark and between iterations.** | Catch a faulted GPU before sending more work into a corrupt context |
| **When a GPU job crashes, STOP.** | Tell David, share the log + `nvidia-smi` output. Do not retry. Do not "try to recover". |

Full rules: `/home/superdave/.claude/projects/-mnt-nvm-repos-transcribe-app/memory/feedback_gpu_safety.md`

---

## 1. Why we're running this benchmark

The branch `feat/upload-speed-improvement` (12 commits since master HEAD `fdfde5b`) implements:

- **Phase 1**: end-to-end wall-clock instrumentation (Redis `benchmark:{task_id}` hash + durable `file_pipeline_timing` table)
- **Phase 2**: ten distinct optimizations across the upload + processing pipeline (presigned uploads, shared-memory handoff, parallel preprocess, deferred thumbnails, etc.)

David needs **real numbers** answering: "Is the branch actually faster end-to-end, by how much, and where do the gains come from?"

This requires an **apples-to-apples A/B comparison**:
1. **Baseline** — same hardware, same fixtures, master HEAD code. Measure user-perceived wall-clock.
2. **After** — same hardware, same fixtures, branch HEAD code. Same measurement.
3. **Compare** — speedup ratio per fixture; per-stage breakdown (branch only, since master has no instrumentation).

The ONLY thing the comparison needs from both sides is the end-to-end wall-clock from POST `/api/files` to status=completed. The branch's per-stage breakdown is a bonus — it tells us *where* the gains came from, but the headline question is answered by the wall-clock alone.

---

## 2. Codebase orientation (skip if you already know this)

- **Repo root:** `/mnt/nvm/repos/transcribe-app`
- **Stack:** FastAPI backend + Svelte frontend + PostgreSQL + MinIO + OpenSearch + Redis + Celery workers, all in Docker Compose
- **Convenience wrapper:** `./opentr.sh` (handles compose file selection, NAS overlays, GPU detection)
- **Dev mode:** `./opentr.sh start dev --nas` (auto-loads `docker-compose.override.yml`, mounts source at `/app` in the backend container, hot-reloads via uvicorn `--reload`)
- **NAS overlay:** `--nas` flag mounts MinIO data on the NAS and DB/OpenSearch on the NVMe (paths from `.env`)
- **Backend Python venv:** `backend/venv/` — activate with `source backend/venv/bin/activate` for any Python tooling on the host
- **Test credentials:** `admin@example.com` / `password`
- **Backend API:** `http://localhost:5174`
- **Postgres:** `docker exec opentranscribe-postgres psql -U postgres -d opentranscribe`
- **MinIO admin (host):** uses `mc` inside the `opentranscribe-minio` container, alias `local`

**Hardware (from CLAUDE.md):**
- **GPU 0** (RTX A6000 #1, 49GB, PCIe `03:00.0`) — assigned to `opentranscribe-celery-worker` (transcription)
- **GPU 1** (RTX 3080 Ti, 12GB, PCIe `04:00.0`) — usually idle, runs Xorg
- **GPU 2** (RTX A6000 #2, 49GB, PCIe `84:00.0`) — runs David's LLM (~47GB resident). **Do not touch.**

---

## 3. The 12 commits on the branch (read top-down for chronology)

```
bb3ad85 fix(scratch): chown pipeline_scratch volume to appuser (UID 1000)
5ab6296 fix(compose): add celery-cloud-asr-worker to all overlay files
06bcadf perf(timing): register new markers + consolidate DB work + doc refresh
88c0770 perf(pipeline): URL-ingest parity + parallel preprocess + diarizer overlap
1e87b8a feat(resilience): orphan sweeper + retry timing + error-path flush
656e808 perf(upload): streaming validation + single commit + dup short-circuit
cb53d34 perf(infra): tune MinIO part size, DB pool, and OS refresh
e7600d0 perf(pipeline): defer thumbnail + full-doc indexing off hot paths
ca27632 perf(pipeline): shared-memory handoff for preprocessed WAV
5494c77 perf(upload): eliminate duplicate I/O on preprocess path
9d2f0f3 feat(upload): presigned direct-to-MinIO uploads + imohash + worker split
16e7d53 feat(timing): add end-to-end pipeline wall-clock instrumentation
```

| Commit | Theme | What changed |
|---|---|---|
| `16e7d53` | **Phase 1 instrumentation** | `app/utils/benchmark_timing.py` (mark/stage helpers), Redis hash, Alembic v360 + `app/models/pipeline_timing.py`, `_TIMESTAMP_MARKERS` registry in `app/services/pipeline_timing_service.py`, admin endpoints, `scripts/benchmark_e2e.py`, `scripts/benchmark_concurrent_uploads.py`, `docs/PIPELINE_TIMING.md` |
| `9d2f0f3` | Presigned uploads + imohash + worker split | New `/files/prepare-upload` + `/files/complete-upload`, `app/services/imohash_service.py` (Alembic v361 adds `media_file.imohash`), Web Worker SHA-256 in frontend, separate `celery-cloud-asr-worker` |
| `5494c77` | Eliminate duplicate I/O | `waveform.py` reads preprocessed WAV not original, video metadata via ffprobe remote URL (`metadata_extractor.extract_media_metadata_from_url`) |
| `ca27632` | Shared-memory handoff | `app/utils/scratch_volume.py` (atomic rename + hard-link), `pipeline_scratch` Docker volume, scratch janitor task |
| `e7600d0` | Defer non-critical work | Thumbnail dispatched to `generate_thumbnail_task` after DB commit, full-doc transcript indexing moved into `index_transcript_search_task` |
| `cb53d34` | MinIO + infra tuning | 64 MiB multipart parts (`upload_file_tuned`), `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` env vars, OpenSearch `refresh_interval=-1` for large transcripts, download concurrency default 3→5 |
| `656e808` | Critical-path compression | `create_media_file_record` flush instead of commit (single-commit upload), streaming first-chunk magic-byte validation, duplicate short-circuit on `client_file_hash` in legacy POST |
| `1e87b8a` | Resilience | `cleanup.orphan_upload_sweeper`, `benchmark_timing.record_retry`, error-path timing flush in `on_pipeline_error` |
| `88c0770` | URL-ingest parity + D11 + D12 + D14 | `youtube_processing` + `media_download_service` instrumentation + imohash + thumbnail defer; ThreadPoolExecutor for ffmpeg+ffprobe in preprocess; diarizer preload thread; `bulk_add_speaker_embeddings_v4` |
| `06bcadf` | Audit follow-ups | Add `imohash_*`, `url_download_*`, `prepare_upload_end`, `pipeline_error_end` to `_TIMESTAMP_MARKERS`; Alembic v362 adds matching DB columns; remove redundant `db.refresh()` in `complete_upload`; consolidate `search_indexing_task` to one session_scope; doc updates |
| `5ab6296` | Compose fix | Add `celery-cloud-asr-worker` to `docker-compose.{override,prod,local,offline}.yml` — base file declared the service but no overlay supplied image/build, so dev mode failed with "neither an image nor a build context specified" |
| `bb3ad85` | Scratch perm fix | `fix_pipeline_scratch_permissions()` in `scripts/common.sh`, called from `opentr.sh` start/reset/rebuild — chowns the named volume to UID 1000 (matches the existing model-cache fix pattern) |

**Plan file (full design + rationale):** `/home/superdave/.claude/plans/i-need-a-full-snoopy-popcorn.md`

---

## 4. Test fixtures — same as the PyAnnote benchmarks

```
/mnt/nvm/repos/transcribe-app/benchmark/test_audio/
├── 0.5h_1899s.wav   58 MB    1899 s  (30 min)
├── 1.0h_3758s.wav  115 MB    3758 s  (1.0 h)
├── 2.2h_7998s.wav  244 MB    7998 s  (2.2 h)
├── 3.2h_11495s.wav 351 MB   11495 s  (3.2 h)
└── 4.7h_17044s.wav 521 MB   17044 s  (4.7 h)
```

These are real-speech recordings. **Do not use synthetic sine-wave audio** — Whisper's VAD rejects pure tones with "No audio content could be detected" (verified the hard way; cost an iteration earlier in this work).

**Originals are safe at the path above.** When David's library accumulates fixture-rows from the benchmark, those go in `media_file` + MinIO `user_1/file_<id>/`, NOT in this directory.

---

## 5. State at the moment of handoff

The reboot was triggered because GPU 0 hit an XID fault during the master-baseline run. State persisted across the reboot:

- **Branch checked out (post-reboot):** `feat/upload-speed-improvement` at commit `73b9aa5` — this is where the handoff doc and scripts live, so the tree is left here so you can read them. You'll switch to `master` in Step 7.2 after finishing the read.
- **Stack:** stopped (must be restarted post-reboot — see Step 7.2)
- **Alembic version in DB:** `v355_add_diarization_settings` (was stamped back so master could run cleanly; stays at v355 until you flip to the branch for the after-run in Step 7.8)
- **Fixture rows:** zero — all benchmark test uploads were cleaned out before the reboot
- **The benchmark commit on branch:** `73b9aa5 docs(benchmark): handoff doc + persist upload-benchmark scripts`
- **Already-collected AFTER results (branch):**

  ```
  fixture            size_mb  audio_s  user_perceived_s  realtime_x
  0.5h_1899s.wav        58      1899          50.5         37.4×
  1.0h_3758s.wav       115      3758          94.5         39.8×
  2.2h_7998s.wav       244      7998         196.8         40.6×
  3.2h_11495s.wav      351     11495         283.5         40.5×
  4.7h_17044s.wav      521     17044         567.3         30.0×
  ```

  These were captured into `/tmp/after_timings.csv` BEFORE the host reboot — that file is gone now (`/tmp` doesn't survive reboot). **Treat the table above as authoritative for the AFTER side**; the per-stage breakdown can be re-collected by re-running on the branch (Step 7 below). The numbers are reproducible.

**Tasks open in the task list:**
- `#50 Baseline benchmark on master HEAD` — `in_progress`. This is the entire focus of the handoff.

---

## 6. Scripts you'll use (all committed at handoff)

### `scripts/benchmark_upload_baseline.py` — the apples-to-apples script

**Works on master AND branch.** Self-contained: only talks to the REST API. No dependency on `file_pipeline_timing`. This is the script that gives you the headline number.

```bash
# Auth + env + invocation
source backend/venv/bin/activate
BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \
  python3 scripts/benchmark_upload_baseline.py <fixtures_dir> <output_csv>
```

**What it does, step-by-step:**
1. Logs in via `POST /api/auth/login` with the env credentials
2. Sorts fixtures by size ascending (so smallest goes first)
3. For each fixture:
   - Computes SHA-256 client-side (matches the real frontend behavior + lets backend dedup work)
   - POSTs to `/api/files` with multipart form data and the `X-File-Hash` header
   - Polls `GET /api/files/{uuid}` every 3 seconds until status is `completed` or `error`
   - Records `client_hash_s`, `http_put_s`, `end_to_end_wall_s`, status
4. Writes a CSV at `<output_csv>` with one row per fixture
5. Prints a summary table to stdout

**Key knobs (constants near the top):** `POLL_INTERVAL=3`, `POLL_TIMEOUT=7200` (2 hr per file).

### `scripts/benchmark_upload_matrix.py` — branch-only, full stage breakdown

**Branch-only** (depends on `file_pipeline_timing` table). Same upload flow as baseline, but additionally pulls per-stage rows from the timing table after each fixture completes. Use this for the *deep* per-stage table after the A/B comparison is in hand.

```bash
source backend/venv/bin/activate
BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \
  python3 scripts/benchmark_upload_matrix.py --fixtures-dir <dir> --output <csv>
```

### `scripts/benchmark_e2e.py` — reprocess-only (NOT for this comparison)

Triggers `/reprocess` on an existing UUID. Skips HTTP ingress entirely. Useful for transcription-only measurements but **not** apples-to-apples for upload speed. Don't use it for this task.

### `scripts/benchmark_concurrent_uploads.py` — concurrency contention (out of scope here)

Launches N copies of one fixture in parallel. Save it for after the A/B if David asks for a contention test.

---

## 7. The recovery procedure — step by step

### Step 7.1 — Sanity-check the host post-reboot

```bash
nvidia-smi
```

**Expected:** All three GPUs show clean state. No "Unknown Error". GPU 2 will show ~47 GB used (David's LLM); that's fine. GPU 0 and GPU 1 should show low usage from Xorg/idle.

```bash
cd /mnt/nvm/repos/transcribe-app
git branch --show-current
```

**Expected:** `feat/upload-speed-improvement`. The tree was intentionally left here so this doc and the benchmark scripts are readable.

```bash
git status
```

**Expected:**
```
On branch feat/upload-speed-improvement
nothing to commit, working tree clean
```

(or a few local-only files you may have created during this session — that's fine.)

```bash
git log -1 --oneline
```

**Expected:** `73b9aa5 docs(benchmark): handoff doc + persist upload-benchmark scripts` (or later).

```bash
docker ps -a | head
```

**Expected:** Containers may show "Exited" status from before the reboot. That's normal — we'll restart fresh.

```bash
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe -t \
  -c "SELECT version_num FROM alembic_version;" 2>&1 | head -5
```

**Expected:** ` v355_add_diarization_settings ` (with leading space — psql formatting). If the postgres container isn't running yet, this fails — start the stack first (Step 7.2 sub-step A), then check.

If the stamp is wrong (showing `v362_add_pipeline_timing_markers` instead of v355), fix it so master can boot cleanly:

```bash
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe \
  -c "UPDATE alembic_version SET version_num='v355_add_diarization_settings';"
```

### Step 7.2 — Switch to master AND start the stack

Now you can safely check out master — you've read the handoff.

**Important:** the benchmark scripts exist only on the branch (`feat/upload-speed-improvement`). Master's `scripts/` directory does NOT contain them. Before switching to master, copy the baseline script to `/tmp` so you can invoke it during the master run:

```bash
# While still on feat/upload-speed-improvement, copy the baseline script.
# (benchmark_upload_matrix.py is branch-only in any case — it reads
# file_pipeline_timing which master doesn't have — so don't bother with it.)
cp scripts/benchmark_upload_baseline.py /tmp/benchmark_upload_baseline.py
ls -l /tmp/benchmark_upload_baseline.py      # confirm the copy exists

# Now switch to master
git checkout master
git log -1 --oneline                          # → fdfde5b
ls scripts/benchmark_upload_baseline.py       # → "No such file" — expected
ls /tmp/benchmark_upload_baseline.py          # → present
```

**All master-side invocations of the baseline script use `/tmp/benchmark_upload_baseline.py`**, NOT `scripts/benchmark_upload_baseline.py`. This is called out again in Step 7.5 and Step 7.7. When you switch back to the branch in Step 7.8, you'll be back to using `scripts/...`.

Start the stack on master:

```bash
./opentr.sh start dev --nas
```

This rebuilds the dev images. Because we only switched code (no requirements changed), Docker layer caching makes this fast (~2-5 min). Watch the output for:
- "✅ NVIDIA GPU detected"
- "✅ NVIDIA Container Toolkit available"
- "💾 Adding custom storage overlay (docker-compose.nas.yml)"
- "Container status:" table — wait until all show `Up X seconds` not `(unhealthy)` or `Restarting`

After it returns, give it ~60 seconds for healthchecks to settle, then:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep opentranscribe | head -15
```

**Expected:** All containers `(healthy)` except possibly `opentranscribe-flower` (it sometimes shows `(unhealthy)` even when working — non-critical for this task). On master, `opentranscribe-celery-cloud-asr-worker` will NOT exist (correct — it's a branch-only service).

### Step 7.3 — Sanity check before benchmarking

```bash
# GPU still healthy?
nvidia-smi
```

If GPU 0 shows "Unknown Error" again, **STOP** and tell David.

```bash
# Backend reachable + auth works?
curl -s -X POST http://localhost:5174/api/auth/login \
  -d "username=admin@example.com&password=password" | head -c 100
```

**Expected:** JSON containing `"access_token":"eyJ..."`. If it's a 4xx/5xx, check `docker logs opentranscribe-backend --tail 50`.

```bash
# Benchmark flag set in container?
docker exec opentranscribe-backend printenv ENABLE_BENCHMARK_TIMING
```

**Expected:** `true`. (Master has no instrumentation, so the flag doesn't change behavior — but having it set is harmless.)

### Step 7.4 — Decide pilot vs full matrix

Two paths. **Recommend pilot first.**

| Option | Time | Files | Why |
|---|---|---|---|
| **A. Pilot** | ~2 min | Just `0.5h_1899s.wav` | Confirm master is meaningfully slower than 50.5s (the branch number) before committing to a full 25-min run |
| **B. Full matrix** | ~25-30 min | All 5 fixtures | Final comparison data. Only do this if pilot shows a directional win |

If the pilot shows master and branch within ~5%, **stop and tell David** before running the full matrix. That would be a real finding (the branch isn't actually faster), and we shouldn't spend GPU time confirming it on bigger files.

### Step 7.5 — Run the pilot baseline (Option A)

```bash
mkdir -p /tmp/bench_pilot
cp benchmark/test_audio/0.5h_1899s.wav /tmp/bench_pilot/
ls -lh /tmp/bench_pilot/
```

**Expected:** One 58 MB WAV file.

```bash
source backend/venv/bin/activate
BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \
  python3 /tmp/benchmark_upload_baseline.py /tmp/bench_pilot /tmp/master_pilot.csv
```

Note the `/tmp/benchmark_upload_baseline.py` path — on master, the script doesn't exist in `scripts/` (it's branch-only). Step 7.2 copied it to `/tmp` for this reason.

**Expected stdout (rough):**
```
Authenticated against http://localhost:5174

▶ 0.5h_1899s.wav (58.0 MB)
  hash 0.23s
  http 1.7s  uuid abcd1234…
    … processing (30s)
    … processing (60s)
  ✓ done in <some_seconds>s

CSV: /tmp/master_pilot.csv

fixture                  size    hash    http   end-to-end  status
0.5h_1899s.wav         58.0MB   0.23s   1.7s     <X.XX>s    ok
```

**Expected end-to-end on master:** 60-90 s. The branch did it in 50.5s, so master should be at least 10-20% slower. If master is within ±5% of the branch number, that's worth a discussion before continuing.

```bash
nvidia-smi
```

**Expected:** GPU 0 idle again, no errors.

### Step 7.6 — Decision point

After the pilot:
- **Master clearly slower (>10%)** → proceed to Step 7.7 (full master matrix)
- **Within 5% of the branch** → stop. Write the pilot result to `docs/UPLOAD_SPEED_BENCHMARK_RESULTS.md` and tell David it's a no-op. Don't run the full matrix.
- **Master FASTER than branch** → unlikely but possible (cold-start effects, contention). Stop. Tell David. Investigate before any more GPU time.
- **GPU error during pilot** → stop. Tell David. `nvidia-smi` output to David. Do not retry.

### Step 7.7 — Full master matrix (only if pilot succeeded)

First, clean up the pilot fixture so dedup doesn't 409:

```bash
PILOT_ID=$(docker exec opentranscribe-postgres psql -U postgres -d opentranscribe -tA \
  -c "SELECT id FROM media_file WHERE filename='0.5h_1899s.wav' ORDER BY id DESC LIMIT 1")
echo "Pilot ID: $PILOT_ID"
```

**Expected:** Some integer like `3140`. If empty, the upload didn't actually create a row — investigate.

```bash
# Cascade delete (transactions don't help; do it step by step like before)
for tbl in analytics task transcript_segment speaker; do
  docker exec opentranscribe-postgres psql -U postgres -d opentranscribe \
    -c "DELETE FROM $tbl WHERE media_file_id = $PILOT_ID;" 2>&1 | head -1
done
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe \
  -c "DELETE FROM media_file WHERE id = $PILOT_ID;"
```

```bash
# Remove from MinIO (must use the in-container mc client)
docker exec opentranscribe-minio sh -c "
  mc alias set local http://localhost:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" 2>&1 >/dev/null
  mc rm --recursive --force local/\$MEDIA_BUCKET_NAME/user_1/file_${PILOT_ID}/
"
```

Then run the full matrix (still on master, using the `/tmp` copy of the script):

```bash
BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \
  python3 /tmp/benchmark_upload_baseline.py benchmark/test_audio /tmp/master_full.csv
```

**Expected runtime:** ~25-30 minutes total (the script processes one at a time, smallest first). Do NOT background this — let it run in the foreground so you can react if a GPU error happens.

**Between fixtures, the script will print summary lines.** If you can manually run `nvidia-smi` in another terminal between fixtures, do — but don't pause the script's polling loop. It's fine to just let it run.

### Step 7.8 — Switch back to the branch

```bash
./opentr.sh stop
```

**Expected:** All containers stop cleanly. Wait for completion. Don't `pkill` anything.

```bash
# Stamp alembic forward to v362 so the branch can resume from where the DB is
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe \
  -c "UPDATE alembic_version SET version_num='v362_add_pipeline_timing_markers';"

git checkout feat/upload-speed-improvement
git log -1 --oneline
```

**Expected:** `bb3ad85 fix(scratch): chown pipeline_scratch volume to appuser (UID 1000)` (or later, if more commits land).

Clean up master's fixture rows so the branch's dedup doesn't 409:

```bash
# Find them
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe -t \
  -c "SELECT id FROM media_file WHERE filename ~ '^[0-9]+\\.[0-9]+h_[0-9]+s\\.wav$' ORDER BY id;"
```

For each ID listed, repeat the cascade delete + MinIO `mc rm` from Step 7.7.

```bash
# Bring the branch up
./opentr.sh start dev --nas
```

**Expected:** Same healthy state, BUT now `opentranscribe-celery-cloud-asr-worker` should appear in `docker ps`. The handoff's compose fix (`5ab6296`) ensures all overlays declare it; the scratch-perm fix (`bb3ad85`) ensures the named volume is writable by UID 1000.

### Step 7.9 — Run the AFTER matrix on the branch

```bash
BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \
  python3 scripts/benchmark_upload_baseline.py benchmark/test_audio /tmp/branch_after.csv
```

This re-collects what the AFTER table at the top of Section 5 already showed. Use the new run as the canonical AFTER number — fresh execution beats memory.

**Optional:** also run the deep per-stage matrix script (branch-only):

```bash
BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \
  python3 scripts/benchmark_upload_matrix.py \
    --fixtures-dir benchmark/test_audio \
    --output /tmp/branch_after_stages.csv
```

This produces a row-per-fixture × column-per-stage CSV from `file_pipeline_timing`. Use it for the breakdown analysis in Step 8.

### Step 7.10 — Build the comparison

Drop this into `scripts/compare_baseline.py` (commit it — David asked for all benchmark scripts saved):

```python
#!/usr/bin/env python3
"""Compare master baseline vs branch after for the upload-speed A/B."""
import csv
import sys

master_csv = sys.argv[1] if len(sys.argv) > 1 else "/tmp/master_full.csv"
branch_csv = sys.argv[2] if len(sys.argv) > 2 else "/tmp/branch_after.csv"

with open(master_csv) as f:
    master = {r["fixture"]: r for r in csv.DictReader(f)}
with open(branch_csv) as f:
    branch = {r["fixture"]: r for r in csv.DictReader(f)}

print(f"{'fixture':<24}{'size':>8}{'master_s':>10}{'branch_s':>10}{'speedup':>9}{'saved':>9}")
print("-" * 72)
for name in sorted(master, key=lambda n: float(master[n]["size_mb"])):
    if name not in branch:
        continue
    m = float(master[name]["end_to_end_wall_s"])
    b = float(branch[name]["end_to_end_wall_s"])
    speedup = m / b if b > 0 else 0
    saved = m - b
    print(f"{name:<24}{master[name]['size_mb']:>6}MB{m:>9.1f}s{b:>9.1f}s{speedup:>8.2f}×{saved:>+8.1f}s")
```

Run it:

```bash
python3 scripts/compare_baseline.py /tmp/master_full.csv /tmp/branch_after.csv
```

---

## 8. Final report — what to write where

Create `docs/UPLOAD_SPEED_BENCHMARK_RESULTS.md` with these sections (commit it on the branch):

1. **Headline result** — one-paragraph summary. "On 5 real-speech fixtures from 30 minutes to 4.7 hours, the branch is X.XX× faster on average. The biggest gain comes from {stage}, saving {Y} seconds on a 30-minute file."

2. **Hardware + environment**
   - Output of `nvidia-smi` (just the GPU table)
   - Driver + CUDA version
   - `cat .env | grep -E '^(MINIO_NAS|POSTGRES_DATA|OPENSEARCH_DATA|MODEL_CACHE)' | head` (paths only, no secrets)
   - Docker compose mode (`dev --nas`)

3. **Master baseline table** — fixture × end_to_end_wall_s × realtime_x

4. **Branch after table** — same shape. Pull from `/tmp/branch_after.csv` (and if available, the per-stage breakdown from `/tmp/branch_after_stages.csv`)

5. **Side-by-side speedup table** — output of `compare_baseline.py`

6. **Per-stage breakdown (branch only)** — preprocess / GPU / postprocess / async-index. Identify which stages contributed most to the gain. The Phase-2 commits map to specific stages (see Section 3); cross-reference where the savings actually land vs where the plan said they would.

7. **Caveats**
   - Cold-start effects (first task after a worker restart is slower because models load — `gpu_worker_cold` flag captures this)
   - What wasn't tested in this run: concurrent uploads, URL ingest path, presigned PUT flow, microphone recording (separate benchmarks exist for those)
   - GPU 0 had an XID fault during this work — host was rebooted before the master baseline run; numbers were collected on a clean post-reboot state

8. **Honest assessment** — if the branch isn't faster on some fixture, say so. If the gains are smaller than the plan predicted, say so. If a stage shows a regression, flag it.

---

## 9. Cleanup checklist

After everything's done and the report is written:

```bash
# 1. Find all benchmark fixture rows
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe \
  -c "SELECT id, filename FROM media_file WHERE filename ~ '^[0-9]+\\.[0-9]+h_[0-9]+s\\.wav$';"
```

For each ID returned:
- Cascade delete (analytics, task, transcript_segment, speaker, then media_file)
- `mc rm --recursive --force local/$MEDIA_BUCKET_NAME/user_1/file_<ID>/`

```bash
# 2. Purge stale Redis benchmark keys (TTL=-1 from old test runs)
REDIS_PW=$(docker exec opentranscribe-backend printenv REDIS_PASSWORD)
docker exec opentranscribe-redis sh -c \
  "redis-cli -a '$REDIS_PW' --no-auth-warning --scan --pattern 'benchmark:*' | xargs -r redis-cli -a '$REDIS_PW' --no-auth-warning del"

# 3. Confirm clean state
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe \
  -c "SELECT count(*) FROM media_file WHERE filename ~ '^[0-9]+\\.';"
```

**Originals at `/mnt/nvm/repos/transcribe-app/benchmark/test_audio/` stay untouched.** They are NOT in MinIO; they live on the host filesystem and are referenced by the fixtures-dir path. Don't delete them.

---

## 10. Failure recovery decision tree

| Symptom | Action |
|---|---|
| `nvidia-smi` shows "Unable to determine the device handle" on any GPU | STOP. Tell David. Do not run any benchmark, do not run any recovery command. |
| `docker ps` shows backend `(unhealthy)` or `Restarting` | `docker logs opentranscribe-backend --tail 100` — share the error with David |
| Alembic error "Can't locate revision identified by 'v362_...'" on master | Run the stamp-back command in Step 7.1 |
| Alembic error on branch saying revision missing | Run `UPDATE alembic_version SET version_num='v362_add_pipeline_timing_markers';` |
| Upload returns 409 Conflict | A prior fixture row exists with the same hash. Run the cleanup pattern. |
| Upload returns 422 Unprocessable Entity | Most likely a missing or malformed `file_hash` header. Check the script. |
| Pipeline status stays `processing` past 2× expected duration | `docker logs opentranscribe-celery-worker --tail 100` to see what the GPU is doing. If stuck, ask David — DO NOT pkill. |
| `benchmark_upload_baseline.py` errors with `redis: connection refused` | The matrix script needs Redis on `localhost:6379`. Baseline script doesn't — if you see this, you ran the wrong script. |
| `mc rm` fails with "object not found" | Already cleaned up. Continue. |
| Cascade DELETE fails with FK constraint | One of the child tables has rows. Check `analytics`, `task`, `transcript_segment`, `speaker` — delete from those before `media_file`. |
| Test run produces times much higher than expected | Check `gpu_worker_cold` field — first task after restart is slower (model load). Run a throwaway warm-up if needed. |
| GPU process crashes mid-benchmark | STOP. `nvidia-smi`. `docker logs opentranscribe-celery-worker --tail 200`. Tell David. |

---

## 11. Quick reference — file locations and commands

| Item | Path |
|---|---|
| Working directory | `/mnt/nvm/repos/transcribe-app` |
| Branch | `feat/upload-speed-improvement` (HEAD: `bb3ad85`) |
| Master | `master` (HEAD: `fdfde5b`) |
| Plan | `/home/superdave/.claude/plans/i-need-a-full-snoopy-popcorn.md` |
| Timing doc | `docs/PIPELINE_TIMING.md` |
| GPU rules | `~/.claude/projects/-mnt-nvm-repos-transcribe-app/memory/feedback_gpu_safety.md` |
| Project memory index | `~/.claude/projects/-mnt-nvm-repos-transcribe-app/memory/MEMORY.md` |
| Fixtures | `benchmark/test_audio/` |
| This handoff | `docs/UPLOAD_SPEED_BENCHMARK_HANDOFF.md` |
| Baseline script | `scripts/benchmark_upload_baseline.py` |
| Matrix script | `scripts/benchmark_upload_matrix.py` |
| Compose stack control | `./opentr.sh start dev --nas` / `./opentr.sh stop` |
| Backend URL | `http://localhost:5174` |
| Test creds | `admin@example.com` / `password` |
| Postgres | `docker exec opentranscribe-postgres psql -U postgres -d opentranscribe` |
| Redis (with auth) | `docker exec opentranscribe-redis redis-cli -a "$(docker exec opentranscribe-backend printenv REDIS_PASSWORD)" --no-auth-warning ...` |

---

## 12. The single message to David when you're done

End your work session by posting a single, concise summary to David. Format:

```
A/B benchmark complete.

Master baseline (5 fixtures, 30min-4.7h): {summary}
Branch after (same fixtures): {summary}
Headline speedup: {X.XX}× average ({range})

Biggest gains came from {stage(s)}.
Caveats: {anything}
Full report: docs/UPLOAD_SPEED_BENCHMARK_RESULTS.md
```

If the run wasn't completed or something went sideways, post:

```
Benchmark blocked at {step}: {reason}.
GPU state: {nvidia-smi summary}.
Recommend: {next action requiring David}.
```

That's it. Don't attempt to keep going past a blocker without David's go-ahead.

---

## 13. Don'ts (one more time)

- ❌ Don't `pkill` anything CUDA-related.
- ❌ Don't `kill -9` anything. Period.
- ❌ Don't run `nvidia-smi -r`, `rmmod`, `modprobe`, or any kernel-module commands.
- ❌ Don't dispatch concurrent GPU jobs unless the test is explicitly designed for it (this one isn't).
- ❌ Don't continue past a GPU error.
- ❌ Don't delete files in `benchmark/test_audio/`.
- ❌ Don't delete David's existing media files (anything in `media_file` not matching the fixture-name regex).
- ❌ Don't push commits without David's review.
- ❌ Don't change branch/Alembic state without the stamp-back/forward dance documented above.

When in doubt, **ask**.
