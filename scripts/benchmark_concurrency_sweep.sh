#!/bin/bash
# Automated concurrency sweep benchmark
#
# Cycles through GPU_CONCURRENT_REQUESTS=1,2,4,6,10, restarts the GPU worker
# for each, runs the parallel benchmark with matched files, and saves results.
#
# Usage:
#   source backend/venv/bin/activate
#   bash scripts/benchmark_concurrency_sweep.sh
#
# Prerequisites:
#   - All services running (./opentr.sh start dev)
#   - ENABLE_BENCHMARK_TIMING=true in .env
#   - ENABLE_VRAM_PROFILING=true in .env
#   - backend/venv activated

set -uo pipefail
# Note: NOT using set -e — grep/docker commands may return non-zero without being fatal

REDIS_URL="redis://:CHANGE_ME_auto_generated_on_install@localhost:5177/0"
OUTPUT_BASE="benchmarks/sweep_$(date +%Y%m%d_%H%M%S)"
GPU_ID=0
COOLDOWN=15

# Matched files (~2.72-2.78hr each) — up to 10 for concurrent=10
FILES_2="132e858d-ee84-4d41-b152-24c7c0783c92,23ac4642-cf42-4c37-884e-e67ac0acb2f4"
FILES_4="$FILES_2,2fd923ab-b16a-48b9-90ed-8e26d557f6aa,e37539b0-d05a-4884-b214-19d23deeab26"
FILES_6="$FILES_4,d1f806a0-7e08-44b5-9df7-42be6bf71340,43cfa426-de2d-4e11-bb90-e13815ce944c"
FILES_8="$FILES_6,24bfea92-814e-4df4-8e02-4bbff554c1d8,871ae397-108f-4a70-ab25-53674d8c432d"
FILES_10="$FILES_8,01b7bded-d60a-4307-a59f-2e4dcde3b59f,ff9e540d-754f-4240-95aa-a752aa4135d2"
FILES_12="$FILES_10,10c1638b-ff67-4712-ac90-33f537702797,472e1207-f927-4d5e-b7d6-d8dea4b51e87"

# All UUIDs for reset
ALL_UUIDS="132e858d-ee84-4d41-b152-24c7c0783c92,23ac4642-cf42-4c37-884e-e67ac0acb2f4,2fd923ab-b16a-48b9-90ed-8e26d557f6aa,e37539b0-d05a-4884-b214-19d23deeab26,d1f806a0-7e08-44b5-9df7-42be6bf71340,43cfa426-de2d-4e11-bb90-e13815ce944c,24bfea92-814e-4df4-8e02-4bbff554c1d8,871ae397-108f-4a70-ab25-53674d8c432d,01b7bded-d60a-4307-a59f-2e4dcde3b59f,ff9e540d-754f-4240-95aa-a752aa4135d2,10c1638b-ff67-4712-ac90-33f537702797,472e1207-f927-4d5e-b7d6-d8dea4b51e87"

# Duration curve files (5min to 4.5hr)
DURATION_CURVE_UUIDS="ce3a4142-1b72-473c-9fbd-53b3432fb80a,d103bf27-bdaf-4913-8f4c-a3b1dd874e9e,31ba0be4-dac6-4b59-a6d7-b55db79dee7a,858ea1e4-6d31-4351-aa45-2aaced31e181,8cef44e5-6fc6-42c6-8418-371ad86e5350,d18b186a-8f15-4f87-943e-3dac555dcd5f,813f19c8-c98e-4d54-a906-d2c31ece6b75,d89f4118-2a40-4e63-bca9-e18da286c2cc,f7a00bd1-a4cc-413f-8933-bb627d0c11d9,4453258e-9637-4d33-aae0-fba3444b1c9b,3e313bbd-924f-4a4b-9584-fa24532b9a01"

CONCURRENCY_LEVELS="1 2 4 6 8 10 12"

mkdir -p "$OUTPUT_BASE"
LOG="$OUTPUT_BASE/sweep.log"

echo "================================================================" | tee "$LOG"
echo "CONCURRENCY SWEEP BENCHMARK" | tee -a "$LOG"
echo "Started: $(date)" | tee -a "$LOG"
echo "Output: $OUTPUT_BASE" | tee -a "$LOG"
echo "Levels: $CONCURRENCY_LEVELS" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"

reset_files() {
    local uuid_list
    uuid_list=$(echo "$ALL_UUIDS" | sed "s/,/','/g")
    docker exec opentranscribe-postgres psql -U postgres -d opentranscribe -c \
        "UPDATE media_file SET retry_count = 0, status = 'completed', last_error_message = NULL, error_category = NULL WHERE uuid IN ('$uuid_list');" \
        > /dev/null 2>&1
}

set_concurrency() {
    local conc=$1
    echo "[$(date +%H:%M:%S)] Setting GPU_CONCURRENT_REQUESTS=$conc..." | tee -a "$LOG"

    # Update .env file with new concurrency value
    sed -i "s/^GPU_CONCURRENT_REQUESTS=.*/GPU_CONCURRENT_REQUESTS=$conc/" .env

    # Restart the GPU worker using opentr.sh which handles all compose overlays correctly.
    # We update .env first, then use the project's own restart mechanism.
    docker exec opentranscribe-redis redis-cli -a CHANGE_ME_auto_generated_on_install DEL gpu > /dev/null 2>&1 || true
    ./opentr.sh stop > /dev/null 2>&1
    sleep 3
    ./opentr.sh start dev > /dev/null 2>&1

    # opentr.sh start dev waits for healthy services. Just give the GPU worker
    # a few extra seconds to finish model preloading after the container is "healthy".
    echo "[$(date +%H:%M:%S)] Waiting for GPU worker models..." | tee -a "$LOG"
    sleep 15

    # Verify the actual concurrency
    sleep 2
    local actual
    actual=$(docker exec opentranscribe-celery-worker env 2>/dev/null | grep GPU_CONCURRENT_REQUESTS | cut -d= -f2 || echo "?")
    echo "[$(date +%H:%M:%S)] Worker ready: GPU_CONCURRENT_REQUESTS=$actual (requested $conc)" | tee -a "$LOG"

    # Verify concurrency in worker logs
    docker compose logs celery-worker --tail 3 2>&1 | grep -E "concurrent|ready" | tail -2 | tee -a "$LOG"

    # Record GPU memory baseline
    local gpu_mem
    gpu_mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id=$GPU_ID 2>/dev/null || echo "?")
    echo "[$(date +%H:%M:%S)] GPU memory baseline: ${gpu_mem} MiB" | tee -a "$LOG"

    # Record GPU processes
    nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader --id=$GPU_ID 2>/dev/null | tee -a "$LOG"
}

run_benchmark() {
    local conc=$1
    local files=$2
    local output_dir="$OUTPUT_BASE/conc${conc}"

    echo "" | tee -a "$LOG"
    echo "================================================================" | tee -a "$LOG"
    echo "[$(date +%H:%M:%S)] BENCHMARK: concurrent=$conc" | tee -a "$LOG"
    echo "================================================================" | tee -a "$LOG"

    # Reset files
    reset_files

    # Run benchmark
    python scripts/benchmark_parallel.py \
        --batches "$conc" \
        --gpu-id "$GPU_ID" \
        --file-uuids "$files" \
        --output "$output_dir" \
        --cooldown 10 \
        2>&1 | tee -a "$LOG"

    # Record GPU memory after
    local gpu_mem
    gpu_mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id=$GPU_ID 2>/dev/null || echo "?")
    echo "[$(date +%H:%M:%S)] GPU memory after: ${gpu_mem} MiB" | tee -a "$LOG"

    # Record per-process GPU memory
    echo "GPU processes:" | tee -a "$LOG"
    nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader --id=$GPU_ID 2>/dev/null | tee -a "$LOG"
}

# Also run single-file baseline with benchmark_e2e.py
run_single_baseline() {
    echo "" | tee -a "$LOG"
    echo "================================================================" | tee -a "$LOG"
    echo "[$(date +%H:%M:%S)] BASELINE: single file, 3 iterations" | tee -a "$LOG"
    echo "================================================================" | tee -a "$LOG"

    reset_files

    python scripts/benchmark_e2e.py \
        --file-uuid 132e858d-ee84-4d41-b152-24c7c0783c92 \
        --iterations 3 \
        --detailed \
        --redis-url "$REDIS_URL" \
        --output "$OUTPUT_BASE/e2e_baseline.csv" \
        2>&1 | tee -a "$LOG"
}

# ── Main ──────────────────────────────────────────────────────────────

# Step 1: Single-file baseline (concurrent=1)
set_concurrency 1
run_single_baseline

echo "" | tee -a "$LOG"
echo "[$(date +%H:%M:%S)] Cooling down ${COOLDOWN}s before concurrency tests..." | tee -a "$LOG"
sleep "$COOLDOWN"

# Step 2: Concurrency sweep
for conc in $CONCURRENCY_LEVELS; do
    # Select the right number of files
    case $conc in
        1) files="${FILES_2:0:36}" ;;  # Just the first UUID
        2) files="$FILES_2" ;;
        4) files="$FILES_4" ;;
        6) files="$FILES_6" ;;
        8) files="$FILES_8" ;;
        10) files="$FILES_10" ;;
        12) files="$FILES_12" ;;
        *) files="$FILES_2" ;;
    esac

    set_concurrency "$conc"
    sleep 5
    run_benchmark "$conc" "$files"

    echo "" | tee -a "$LOG"
    echo "[$(date +%H:%M:%S)] Cooling down ${COOLDOWN}s..." | tee -a "$LOG"
    sleep "$COOLDOWN"
done

# Step 3: Duration curve (concurrent=1, 11 files of varying length)
echo "" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"
echo "[$(date +%H:%M:%S)] DURATION CURVE: 11 files, 5min to 4.5hr" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"

set_concurrency 1
sleep 5

# Reset duration curve files
DC_LIST=$(echo "$DURATION_CURVE_UUIDS" | sed "s/,/','/g")
docker exec opentranscribe-postgres psql -U postgres -d opentranscribe -c \
    "UPDATE media_file SET retry_count = 0, status = 'completed', last_error_message = NULL, error_category = NULL WHERE uuid IN ('$DC_LIST');" \
    > /dev/null 2>&1

python scripts/benchmark_parallel.py \
    --sequential \
    --gpu-id "$GPU_ID" \
    --file-uuids "$DURATION_CURVE_UUIDS" \
    --output "$OUTPUT_BASE/duration_curve" \
    --cooldown 5 \
    2>&1 | tee -a "$LOG"

# Step 4: Diarization batch size test (concurrent=1, single file)
# Test if reducing diarization embedding batch_size lowers VRAM at cost of speed
echo "" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"
echo "[$(date +%H:%M:%S)] DIARIZATION BATCH SIZE TEST" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"

for DIAR_BATCH in 32 16 8; do
    echo "" | tee -a "$LOG"
    echo "[$(date +%H:%M:%S)] Testing DIARIZATION_EMBEDDING_BATCH_SIZE=$DIAR_BATCH" | tee -a "$LOG"

    # Update .env and restart
    sed -i "s/^GPU_CONCURRENT_REQUESTS=.*/GPU_CONCURRENT_REQUESTS=1/" .env
    # Add or update DIARIZATION_EMBEDDING_BATCH_SIZE in .env
    if grep -q "^DIARIZATION_EMBEDDING_BATCH_SIZE=" .env; then
        sed -i "s/^DIARIZATION_EMBEDDING_BATCH_SIZE=.*/DIARIZATION_EMBEDDING_BATCH_SIZE=$DIAR_BATCH/" .env
    else
        echo "DIARIZATION_EMBEDDING_BATCH_SIZE=$DIAR_BATCH" >> .env
    fi
    ./opentr.sh stop > /dev/null 2>&1
    sleep 3
    ./opentr.sh start dev > /dev/null 2>&1

    # Wait for ready
    for _i in $(seq 1 60); do
        if docker compose logs celery-worker --tail 1 2>&1 | grep -q "ready\." 2>/dev/null; then break; fi
        sleep 2
    done
    sleep 5

    reset_files

    python scripts/benchmark_e2e.py \
        --file-uuid 132e858d-ee84-4d41-b152-24c7c0783c92 \
        --iterations 1 \
        --detailed \
        --redis-url "$REDIS_URL" \
        --output "$OUTPUT_BASE/diar_batch_${DIAR_BATCH}.csv" \
        2>&1 | tee -a "$LOG"

    # Record VRAM
    gpu_mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --id=$GPU_ID 2>/dev/null || echo "?")
    echo "[$(date +%H:%M:%S)] DIAR_BATCH=$DIAR_BATCH GPU memory after: ${gpu_mem} MiB" | tee -a "$LOG"

    sleep "$COOLDOWN"
done

# Step 5: Reset to concurrent=1, remove diarization batch override
sed -i '/^DIARIZATION_EMBEDDING_BATCH_SIZE=/d' .env
set_concurrency 1

echo "" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"
echo "SWEEP COMPLETE" | tee -a "$LOG"
echo "Finished: $(date)" | tee -a "$LOG"
echo "Results: $OUTPUT_BASE/" | tee -a "$LOG"
echo "================================================================" | tee -a "$LOG"

# Print summary
echo "" | tee -a "$LOG"
echo "SUMMARY" | tee -a "$LOG"
echo "-------" | tee -a "$LOG"
for conc in $CONCURRENCY_LEVELS; do
    dir="$OUTPUT_BASE/conc${conc}"
    for csv_file in "$dir"/benchmark_summary_*.csv; do
        if [ -f "$csv_file" ]; then
            echo "concurrent=$conc:" | tee -a "$LOG"
            cat "$csv_file" | tee -a "$LOG"
            echo "" | tee -a "$LOG"
            break
        fi
    done
done
