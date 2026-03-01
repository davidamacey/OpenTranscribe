"""
Integration test for v3→v4 speaker embedding migration.

Runs against LIVE services (Redis, OpenSearch, MinIO, PostgreSQL) to verify
the full migration pipeline works end-to-end with real files from the database.

Usage:
    # From backend/ with venv activated and dev environment running:
    pytest tests/test_embedding_migration_integration.py -v -s

    # Run just the throughput benchmark (processes 10 files):
    pytest tests/test_embedding_migration_integration.py -v -s -k throughput

    # Run with custom sample size:
    MIGRATION_TEST_SAMPLE=20 pytest tests/test_embedding_migration_integration.py -v -s -k throughput

Requires:
    - Dev environment running (./opentr.sh start dev)
    - At least a few completed transcriptions in the database
    - GPU available for embedding extraction
"""

import logging
import os
import sys
import time
from pathlib import Path

import pytest

# Add backend dir to path
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# These tests require live services — skip if env vars disable them
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_REDIS", "").lower() == "true"
    or os.environ.get("SKIP_OPENSEARCH", "").lower() == "true"
    or os.environ.get("SKIP_S3", "").lower() == "true"
    or os.environ.get("TESTING", "").lower() == "true",
    reason="Requires live Redis, OpenSearch, MinIO (run outside pytest conftest)",
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def live_db_session():
    """Database session connected to the live dev database."""
    from dotenv import dotenv_values

    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        env_values = dotenv_values(env_file)
        for key in ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]:
            if key in env_values:
                os.environ[key] = env_values[key]

    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5176")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture(scope="module")
def completed_files(live_db_session):
    """Get completed media files from the live database."""
    from app.models.media import FileStatus
    from app.models.media import MediaFile

    files = (
        live_db_session.query(MediaFile)
        .filter(MediaFile.status == FileStatus.COMPLETED)
        .limit(50)
        .all()
    )
    return files


class TestMigrationLockLive:
    """Test migration lock against live Redis."""

    def test_activate_deactivate_cycle(self):
        from app.services.migration_lock_service import MigrationLockService

        lock = MigrationLockService()
        # Clean up any stale lock first
        lock.deactivate()

        assert lock.is_active() is False

        assert lock.activate() is True
        assert lock.is_active() is True

        # Second activate should fail (NX semantics)
        assert lock.activate() is False

        assert lock.deactivate() is True
        assert lock.is_active() is False

    def test_refresh_ttl(self):
        from app.services.migration_lock_service import MigrationLockService

        lock = MigrationLockService()
        lock.deactivate()  # Clean slate

        lock.activate()
        assert lock.refresh_ttl(ttl=60) is True
        lock.deactivate()

    def test_refresh_ttl_fails_without_lock(self):
        from app.services.migration_lock_service import MigrationLockService

        lock = MigrationLockService()
        lock.deactivate()

        assert lock.refresh_ttl() is False


class TestSkipLogicLive:
    """Test skip logic against live OpenSearch."""

    def test_get_already_migrated_file_ids(self):
        from app.tasks.embedding_migration_v4 import _get_already_migrated_file_ids

        # Should return a set (may be empty if no v4 index exists yet)
        result = _get_already_migrated_file_ids()
        assert isinstance(result, set)


class TestMigrationStatusLive:
    """Test migration status against live services."""

    def test_get_migration_status(self):
        from app.tasks.embedding_migration_v4 import get_migration_status

        status = get_migration_status()
        assert "current_mode" in status
        assert "v3_document_count" in status
        assert "v4_document_count" in status
        assert "migration_needed" in status
        assert "transcription_paused" in status
        print(f"\n  Current mode: {status['current_mode']}")
        print(f"  V3 docs: {status['v3_document_count']}")
        print(f"  V4 docs: {status['v4_document_count']}")
        print(f"  Migration needed: {status['migration_needed']}")
        print(f"  Transcription paused: {status['transcription_paused']}")


class TestPrepareFileForGpuLive:
    """Test I/O preparation with real files."""

    def test_prepare_single_file(self, completed_files):
        if not completed_files:
            pytest.skip("No completed files in database")

        from app.models.media import Speaker
        from app.services.minio_service import download_file
        from app.tasks.embedding_migration_v4 import _prepare_file_for_gpu
        from app.utils.uuid_helpers import get_file_by_uuid

        file = completed_files[0]
        file_uuid = str(file.uuid)

        start = time.time()
        prepared = _prepare_file_for_gpu(file_uuid, download_file, get_file_by_uuid, Speaker)
        elapsed = time.time() - start

        if prepared is None:
            print(f"\n  File {file_uuid} has no speakers (skipped)")
        else:
            print(f"\n  Prepared file {file_uuid} in {elapsed:.2f}s")
            print(f"    Speakers: {len(prepared.speakers)}")
            print(f"    Segment groups: {len(prepared.speaker_segments)}")
            print(f"    Audio source: {prepared.audio_source[:80]}...")
            assert prepared.audio_source.startswith("http")


class TestThroughputBenchmark:
    """Benchmark migration throughput with real files.

    This is the key test for understanding migration speed.
    Processes a sample of files through the full pipeline and reports timing.
    """

    def test_throughput_benchmark(self, completed_files):
        """Process a sample of files and measure throughput.

        Set MIGRATION_TEST_SAMPLE env var to control sample size (default: 10).
        """
        if not completed_files:
            pytest.skip("No completed files in database")

        from app.models.media import Speaker
        from app.services.embedding_mode_service import MODE_V4
        from app.services.minio_service import download_file
        from app.services.speaker_embedding_service import get_cached_embedding_service
        from app.tasks.embedding_migration_v4 import _gpu_extract_and_write
        from app.tasks.embedding_migration_v4 import _prepare_file_for_gpu
        from app.utils.uuid_helpers import get_file_by_uuid

        sample_size = int(os.environ.get("MIGRATION_TEST_SAMPLE", "10"))
        sample = completed_files[:sample_size]

        print(f"\n{'=' * 70}")
        print("  V3→V4 Migration Throughput Benchmark")
        print(f"  Sample size: {len(sample)} files")
        print(f"{'=' * 70}")

        # Phase 1: Measure model load time
        print("\n  Phase 1: Loading embedding model (one-time cost)...")
        model_start = time.time()
        embedding_service = get_cached_embedding_service(mode=MODE_V4)
        model_time = time.time() - model_start
        print(f"    Model load: {model_time:.1f}s")

        # Phase 2: Process files and measure each phase
        io_times = []
        gpu_times = []
        speaker_counts = []
        skipped = 0

        for i, file in enumerate(sample):
            file_uuid = str(file.uuid)

            # I/O phase: download + DB query
            io_start = time.time()
            try:
                prepared = _prepare_file_for_gpu(
                    file_uuid, download_file, get_file_by_uuid, Speaker
                )
            except Exception as e:
                print(f"    [{i + 1}/{len(sample)}] {file_uuid}: I/O FAILED - {e}")
                continue
            io_time = time.time() - io_start

            if prepared is None:
                skipped += 1
                print(f"    [{i + 1}/{len(sample)}] {file_uuid}: no speakers (skipped)")
                continue

            io_times.append(io_time)
            speaker_counts.append(len(prepared.speakers))

            # GPU phase: extract embeddings (no OpenSearch write in benchmark)
            gpu_start = time.time()
            try:
                count = _gpu_extract_and_write(prepared, embedding_service)
                gpu_time = time.time() - gpu_start
                gpu_times.append(gpu_time)
                total = io_time + gpu_time
                print(
                    f"    [{i + 1}/{len(sample)}] {file_uuid}: "
                    f"{len(prepared.speakers)} speakers, "
                    f"I/O={io_time:.2f}s GPU={gpu_time:.2f}s total={total:.2f}s"
                )
            except Exception as e:
                print(f"    [{i + 1}/{len(sample)}] {file_uuid}: GPU FAILED - {e}")

        # Summary
        print(f"\n{'=' * 70}")
        print("  Results")
        print(f"{'=' * 70}")

        processed = len(gpu_times)
        if processed == 0:
            print("  No files were processed successfully.")
            return

        avg_io = sum(io_times) / len(io_times)
        avg_gpu = sum(gpu_times) / len(gpu_times)
        avg_total = avg_io + avg_gpu
        avg_speakers = sum(speaker_counts) / len(speaker_counts)

        print(f"  Files processed: {processed}")
        print(f"  Files skipped (no speakers): {skipped}")
        print(f"  Avg speakers/file: {avg_speakers:.1f}")
        print()
        print(f"  Avg I/O time (download + DB): {avg_io:.2f}s/file")
        print(f"  Avg GPU time (extraction):    {avg_gpu:.2f}s/file")
        print(f"  Avg total per file:           {avg_total:.2f}s/file")
        print()

        # Pipeline estimate: with prefetch, GPU doesn't wait for I/O
        pipeline_per_file = max(avg_io, avg_gpu)  # Bottleneck determines rate
        print("  Pipeline throughput (with prefetch):")
        print(f"    Bottleneck: {'I/O' if avg_io > avg_gpu else 'GPU'} ({pipeline_per_file:.2f}s)")
        print(f"    ~{pipeline_per_file:.2f}s/file effective")
        print()

        # Projections
        for total_files in [100, 500, 1000, 2500]:
            sequential = total_files * avg_total
            pipelined = total_files * pipeline_per_file + model_time
            print(
                f"  {total_files:>5} files: "
                f"sequential={_fmt_duration(sequential)}, "
                f"pipelined={_fmt_duration(pipelined)}"
            )

        print(f"\n  Model load (one-time): {model_time:.1f}s")
        print(f"{'=' * 70}")


def _fmt_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}min"
    else:
        return f"{seconds / 3600:.1f}hr"
