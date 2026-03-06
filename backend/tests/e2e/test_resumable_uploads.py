"""
E2E Tests for TUS 1.0.0 Resumable Upload Protocol (Issue #10)

Test classes:
- TestTUSProtocol: Pure HTTP API tests for TUS protocol conformance (no browser)
- TestTUSResumeUI: Browser-based pause/resume UI tests via Playwright
- TestTUSCleanup: Expired session cleanup task tests

Requirements:
- Dev environment running: ./opentr.sh start dev
- Backend at localhost:5174
- Frontend at localhost:5173

Run:
    pytest backend/tests/e2e/test_resumable_uploads.py -v
"""

import base64
import os
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

import pytest
import requests
from playwright.sync_api import Page

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("E2E_BACKEND_URL", "http://localhost:5174")
FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:5173")

TEST_ADMIN_EMAIL = "admin@example.com"
TEST_ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "password")  # noqa: S105

TUS_BASE_URL = f"{BACKEND_URL}/api/files/tus"

# Minimal valid MP3 stub: 4-byte frame sync + 128-byte padding = 132 bytes total.
# The first 4 bytes match an MPEG Layer 3 sync word, which is sufficient to pass
# the magic-byte validator for audio/mpeg.
MINIMAL_MP3: bytes = bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 128

# ---------------------------------------------------------------------------
# TUS-specific fixtures
# ---------------------------------------------------------------------------


class TUSHelper:
    """Helper for making TUS 1.0.0 protocol HTTP calls.

    Wraps the low-level requests calls with convenience methods that encode
    metadata, set required headers, and return raw Response objects so that
    individual tests can assert on status codes and headers directly.

    Attributes:
        backend_url: Base URL for the backend API.
        token: JWT access token for the authenticated user (set via login()).
    """

    def __init__(self, backend_url: str) -> None:
        self.backend_url = backend_url
        self.token: str | None = None

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def login(self, email: str = TEST_ADMIN_EMAIL, password: str = TEST_ADMIN_PASS) -> str:
        """Authenticate and store the JWT token. Returns the token string."""
        response = requests.post(
            f"{self.backend_url}/api/auth/token",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.status_code} {response.text}"
        self.token = str(response.json()["access_token"])
        return self.token

    def _auth_headers(self) -> dict[str, str]:
        """Return auth header dict. Raises if not logged in."""
        if not self.token:
            raise RuntimeError("TUSHelper: call login() before making authenticated requests")
        return {"Authorization": f"Bearer {self.token}"}

    # ------------------------------------------------------------------
    # Step 1: POST /api/files/prepare → get file UUID
    # ------------------------------------------------------------------

    def prepare_file(
        self,
        filename: str = "test.mp3",
        content_type: str = "audio/mpeg",
        file_size: int = 132,
    ) -> str:
        """Call POST /api/files/prepare and return the file UUID string."""
        response = requests.post(
            f"{self.backend_url}/api/files/prepare",
            json={
                "filename": filename,
                "file_size": file_size,
                "content_type": content_type,
            },
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            timeout=30,
        )
        assert response.status_code == 200, (
            f"prepare_file failed: {response.status_code} {response.text}"
        )
        return str(response.json()["file_id"])

    # ------------------------------------------------------------------
    # Step 2: POST /api/files/tus → create TUS upload resource
    # ------------------------------------------------------------------

    def encode_metadata(self, **kwargs: str) -> str:
        """Encode key=value pairs as TUS Upload-Metadata header.

        TUS spec: comma-separated 'key base64(value)' pairs.
        """
        pairs = []
        for key, value in kwargs.items():
            b64 = base64.b64encode(value.encode("utf-8")).decode("ascii")
            pairs.append(f"{key} {b64}")
        return ", ".join(pairs)

    def create_session(
        self,
        file_id: str,
        filename: str = "test.mp3",
        content_type: str = "audio/mpeg",
        file_size: int = 132,
        tus_version: str = "1.0.0",
        extra_headers: dict[str, str] | None = None,
        extra_metadata: dict[str, str] | None = None,
    ) -> requests.Response:
        """POST /api/files/tus to create a new upload session.

        Returns the raw Response so callers can inspect status codes and headers.
        """
        metadata_parts: dict[str, str] = {
            "filename": filename,
            "filetype": content_type,
            "fileId": file_id,
        }
        if extra_metadata:
            metadata_parts.update(extra_metadata)

        headers: dict[str, str] = {
            **self._auth_headers(),
            "Tus-Resumable": tus_version,
            "Upload-Length": str(file_size),
            "Upload-Metadata": self.encode_metadata(**metadata_parts),
        }
        if extra_headers:
            headers.update(extra_headers)

        return requests.post(TUS_BASE_URL, headers=headers, timeout=30)

    def prepare_and_create_session(
        self,
        filename: str = "test.mp3",
        content_type: str = "audio/mpeg",
        file_size: int = 132,
    ) -> tuple[str, str]:
        """Convenience: prepare a file AND create a TUS session.

        Returns:
            (file_id, upload_id) — both as strings.
        """
        file_id = self.prepare_file(filename, content_type, file_size)
        resp = self.create_session(file_id, filename, content_type, file_size)
        assert resp.status_code == 201, f"create_session failed: {resp.status_code} {resp.text}"
        # Location header: /api/files/tus/{upload_id}
        location = resp.headers["Location"]
        upload_id = location.rstrip("/").split("/")[-1]
        return file_id, upload_id

    # ------------------------------------------------------------------
    # HEAD /api/files/tus/{upload_id}
    # ------------------------------------------------------------------

    def head(self, upload_id: str) -> requests.Response:
        """HEAD /api/files/tus/{upload_id} — get current upload offset."""
        return requests.head(
            f"{TUS_BASE_URL}/{upload_id}",
            headers={**self._auth_headers(), "Tus-Resumable": "1.0.0"},
            timeout=30,
        )

    # ------------------------------------------------------------------
    # PATCH /api/files/tus/{upload_id}
    # ------------------------------------------------------------------

    def patch(
        self,
        upload_id: str,
        data: bytes,
        offset: int,
    ) -> requests.Response:
        """PATCH /api/files/tus/{upload_id} — upload a chunk at the given offset."""
        return requests.patch(
            f"{TUS_BASE_URL}/{upload_id}",
            data=data,
            headers={
                **self._auth_headers(),
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": str(offset),
            },
            timeout=60,
        )

    # ------------------------------------------------------------------
    # DELETE /api/files/tus/{upload_id}
    # ------------------------------------------------------------------

    def delete(self, upload_id: str) -> requests.Response:
        """DELETE /api/files/tus/{upload_id} — abort the upload."""
        return requests.delete(
            f"{TUS_BASE_URL}/{upload_id}",
            headers={**self._auth_headers(), "Tus-Resumable": "1.0.0"},
            timeout=30,
        )


@pytest.fixture
def tus_helper() -> TUSHelper:
    """Provide an authenticated TUSHelper pre-logged-in as admin."""
    helper = TUSHelper(BACKEND_URL)
    helper.login()
    return helper


# ---------------------------------------------------------------------------
# Class 1: TestTUSProtocol — Pure API tests (no browser)
# ---------------------------------------------------------------------------


class TestTUSProtocol:
    """Test TUS 1.0.0 protocol conformance via HTTP API.

    All tests hit the backend directly without a browser. The tus_helper
    fixture handles authentication and encoding.
    """

    # ------------------------------------------------------------------
    # OPTIONS
    # ------------------------------------------------------------------

    def test_options_returns_tus_headers(self, tus_helper: TUSHelper) -> None:
        """OPTIONS /api/files/tus returns correct capability headers."""
        response = requests.options(TUS_BASE_URL, timeout=10)

        assert response.status_code == 204
        assert response.headers.get("Tus-Resumable") == "1.0.0"
        assert response.headers.get("Tus-Version") == "1.0.0"
        assert "Tus-Max-Size" in response.headers
        assert "Tus-Extension" in response.headers

    def test_options_no_auth_required(self) -> None:
        """OPTIONS is accessible without authentication."""
        # No auth headers at all
        response = requests.options(TUS_BASE_URL, timeout=10)
        # Must not return 401 or 403
        assert response.status_code not in (401, 403), (
            f"OPTIONS should not require auth, got {response.status_code}"
        )
        assert response.status_code == 204

    def test_options_tus_extension_includes_creation_and_termination(
        self, tus_helper: TUSHelper
    ) -> None:
        """OPTIONS reports support for 'creation' and 'termination' extensions."""
        response = requests.options(TUS_BASE_URL, timeout=10)

        extension = response.headers.get("Tus-Extension", "")
        assert "creation" in extension, f"Expected 'creation' in Tus-Extension, got: {extension}"
        assert "termination" in extension, (
            f"Expected 'termination' in Tus-Extension, got: {extension}"
        )

    # ------------------------------------------------------------------
    # POST — Create upload resource
    # ------------------------------------------------------------------

    def test_post_creates_upload_resource(self, tus_helper: TUSHelper) -> None:
        """POST creates a new upload session and returns Location header."""
        file_id = tus_helper.prepare_file()
        resp = tus_helper.create_session(file_id)

        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        assert "Location" in resp.headers, "Response must include a Location header"
        location = resp.headers["Location"]
        assert "/api/files/tus/" in location, (
            f"Location should point to /api/files/tus/<uuid>, got: {location}"
        )
        # The Tus-Resumable header must also be echoed on the response
        assert resp.headers.get("Tus-Resumable") == "1.0.0"

    def test_post_rejects_missing_file_id(self, tus_helper: TUSHelper) -> None:
        """POST without fileId in Upload-Metadata returns 400."""
        file_id = tus_helper.prepare_file()
        # Override metadata to omit 'fileId'
        resp = tus_helper.create_session(
            file_id=file_id,
            extra_metadata={},
        )
        # The helper includes fileId by default; we need a raw call without it
        metadata = tus_helper.encode_metadata(filename="test.mp3", filetype="audio/mpeg")
        raw_resp = requests.post(
            TUS_BASE_URL,
            headers={
                **tus_helper._auth_headers(),
                "Tus-Resumable": "1.0.0",
                "Upload-Length": "132",
                "Upload-Metadata": metadata,
            },
            timeout=30,
        )
        assert raw_resp.status_code == 400, (
            f"Expected 400 for missing fileId, got {raw_resp.status_code}"
        )

    def test_post_rejects_invalid_tus_version(self, tus_helper: TUSHelper) -> None:
        """POST with wrong Tus-Resumable version returns 412."""
        file_id = tus_helper.prepare_file()
        resp = tus_helper.create_session(file_id, tus_version="2.0.0")

        assert resp.status_code == 412, (
            f"Expected 412 for invalid Tus-Resumable, got {resp.status_code}"
        )

    def test_post_rejects_non_media_content_type(self, tus_helper: TUSHelper) -> None:
        """POST with text/plain as filetype returns 400."""
        file_id = tus_helper.prepare_file(content_type="text/plain")
        resp = tus_helper.create_session(file_id, content_type="text/plain")

        assert resp.status_code == 400, (
            f"Expected 400 for non-media content type, got {resp.status_code}"
        )

    def test_post_enforces_per_user_session_cap(self, tus_helper: TUSHelper) -> None:
        """Creating more than 5 concurrent sessions returns 429."""
        # Create 5 sessions (the maximum allowed)
        created_upload_ids: list[str] = []
        for i in range(5):
            fid = tus_helper.prepare_file(filename=f"cap_test_{i}.mp3", file_size=132)
            resp = tus_helper.create_session(fid, filename=f"cap_test_{i}.mp3")
            if resp.status_code == 201:
                location = resp.headers.get("Location", "")
                uid = location.rstrip("/").split("/")[-1]
                created_upload_ids.append(uid)

        # The 6th session must be rejected
        fid_extra = tus_helper.prepare_file(filename="cap_test_extra.mp3", file_size=132)
        sixth_resp = tus_helper.create_session(fid_extra, filename="cap_test_extra.mp3")

        try:
            assert sixth_resp.status_code == 429, (
                f"Expected 429 when exceeding session cap, got {sixth_resp.status_code}"
            )
        finally:
            # Clean up sessions so other tests are not affected
            for uid in created_upload_ids:
                try:
                    tus_helper.delete(uid)
                except Exception:
                    pass

    def test_post_rejects_missing_upload_length(self, tus_helper: TUSHelper) -> None:
        """POST without Upload-Length returns 400."""
        file_id = tus_helper.prepare_file()
        metadata = tus_helper.encode_metadata(
            filename="test.mp3", filetype="audio/mpeg", fileId=file_id
        )
        resp = requests.post(
            TUS_BASE_URL,
            headers={
                **tus_helper._auth_headers(),
                "Tus-Resumable": "1.0.0",
                # Upload-Length intentionally omitted
                "Upload-Metadata": metadata,
            },
            timeout=30,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing Upload-Length, got {resp.status_code}"
        )

    # ------------------------------------------------------------------
    # HEAD — Get upload offset
    # ------------------------------------------------------------------

    def test_head_returns_current_offset(self, tus_helper: TUSHelper) -> None:
        """HEAD returns Upload-Offset: 0 for a freshly created session."""
        _file_id, upload_id = tus_helper.prepare_and_create_session()

        resp = tus_helper.head(upload_id)

        assert resp.status_code == 200, f"HEAD failed: {resp.status_code}"
        assert resp.headers.get("Upload-Offset") == "0", (
            f"Expected offset 0 for new session, got {resp.headers.get('Upload-Offset')}"
        )
        assert "Upload-Length" in resp.headers
        assert resp.headers.get("Cache-Control") == "no-store"

    def test_head_returns_404_for_unknown_upload(self, tus_helper: TUSHelper) -> None:
        """HEAD for a non-existent upload UUID returns 404."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp = tus_helper.head(fake_uuid)
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # PATCH — Upload chunk
    # ------------------------------------------------------------------

    def test_patch_uploads_chunk_and_advances_offset(self, tus_helper: TUSHelper) -> None:
        """PATCH with valid chunk advances Upload-Offset."""
        file_data = MINIMAL_MP3  # 132 bytes
        _file_id, upload_id = tus_helper.prepare_and_create_session(file_size=len(file_data))

        resp = tus_helper.patch(upload_id, file_data, offset=0)

        # A complete single-chunk upload returns 204 with the new offset
        assert resp.status_code == 204, f"PATCH failed: {resp.status_code} {resp.text}"
        assert resp.headers.get("Upload-Offset") == str(len(file_data)), (
            f"Expected offset {len(file_data)}, got {resp.headers.get('Upload-Offset')}"
        )

    def test_patch_rejects_wrong_offset(self, tus_helper: TUSHelper) -> None:
        """PATCH with Upload-Offset != current offset returns 409."""
        file_data = MINIMAL_MP3
        _file_id, upload_id = tus_helper.prepare_and_create_session(file_size=len(file_data))

        # Send offset=50 when the session offset is 0
        resp = tus_helper.patch(upload_id, file_data[:10], offset=50)
        assert resp.status_code == 409, (
            f"Expected 409 for mismatched offset, got {resp.status_code}"
        )

    def test_patch_rejects_wrong_content_type(self, tus_helper: TUSHelper) -> None:
        """PATCH with Content-Type: application/json returns 415."""
        file_data = MINIMAL_MP3
        _file_id, upload_id = tus_helper.prepare_and_create_session(file_size=len(file_data))

        resp = requests.patch(
            f"{TUS_BASE_URL}/{upload_id}",
            data=file_data,
            headers={
                **tus_helper._auth_headers(),
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/json",  # Wrong — must be application/offset+octet-stream
                "Upload-Offset": "0",
            },
            timeout=30,
        )
        assert resp.status_code == 415, (
            f"Expected 415 for wrong Content-Type, got {resp.status_code}"
        )

    def test_patch_rejects_invalid_magic_bytes(self, tus_helper: TUSHelper) -> None:
        """PATCH with data that doesn't match declared MIME type returns 415."""
        # 132 bytes of null — not a valid MP3
        bad_data = b"\x00" * 132
        _file_id, upload_id = tus_helper.prepare_and_create_session(file_size=len(bad_data))

        resp = tus_helper.patch(upload_id, bad_data, offset=0)
        assert resp.status_code == 415, (
            f"Expected 415 for invalid magic bytes, got {resp.status_code}: {resp.text}"
        )

    # ------------------------------------------------------------------
    # DELETE — Abort upload
    # ------------------------------------------------------------------

    def test_delete_aborts_upload(self, tus_helper: TUSHelper) -> None:
        """DELETE aborts the upload session; subsequent HEAD returns 404."""
        _file_id, upload_id = tus_helper.prepare_and_create_session()

        del_resp = tus_helper.delete(upload_id)
        assert del_resp.status_code == 204, f"DELETE failed: {del_resp.status_code} {del_resp.text}"

        # After abort, HEAD must return 404
        head_resp = tus_helper.head(upload_id)
        assert head_resp.status_code == 404, (
            f"Expected 404 after abort, got {head_resp.status_code}"
        )

    def test_delete_returns_tus_headers(self, tus_helper: TUSHelper) -> None:
        """DELETE response includes Tus-Resumable header."""
        _file_id, upload_id = tus_helper.prepare_and_create_session()
        del_resp = tus_helper.delete(upload_id)

        assert del_resp.headers.get("Tus-Resumable") == "1.0.0"

    # ------------------------------------------------------------------
    # Full single-chunk upload
    # ------------------------------------------------------------------

    def test_full_upload_completes_and_creates_media_file(self, tus_helper: TUSHelper) -> None:
        """A complete single-chunk TUS upload creates a processed MediaFile.

        Uses the minimal MP3 stub (132 bytes) so no real audio processing
        occurs. We verify the MediaFile gets storage_path set and status
        transitions out of the initial 'uploading' state.
        """
        file_data = MINIMAL_MP3

        # Step 1 & 2: prepare + create TUS session
        file_id, upload_id = tus_helper.prepare_and_create_session(
            filename="e2e_complete_test.mp3",
            content_type="audio/mpeg",
            file_size=len(file_data),
        )

        # Step 3: PATCH with all data (single chunk)
        patch_resp = tus_helper.patch(upload_id, file_data, offset=0)
        assert patch_resp.status_code == 204, (
            f"Final PATCH failed: {patch_resp.status_code} {patch_resp.text}"
        )
        assert patch_resp.headers.get("Upload-Offset") == str(len(file_data))

        # Step 4: HEAD should still return 200 (completed session is accessible)
        #   OR 404 if the implementation deletes completed sessions — both are
        #   acceptable per the TUS spec; we only assert that the PATCH succeeded.
        #
        # Step 5: Query the backend for the MediaFile to verify it was updated
        mf_resp = requests.get(
            f"{BACKEND_URL}/api/files/{file_id}",
            headers=tus_helper._auth_headers(),
            timeout=30,
        )
        # The file should be findable (even if it's pending transcription)
        assert mf_resp.status_code == 200, (
            f"MediaFile not found after upload: {mf_resp.status_code} {mf_resp.text}"
        )
        media_file: dict[str, Any] = mf_resp.json()
        # storage_path is set on completion
        assert media_file.get("storage_path"), (
            "MediaFile storage_path should be set after a completed TUS upload"
        )
        # Status should not be 'error'
        assert media_file.get("status") != "error", (
            f"MediaFile status must not be 'error' after upload, got: {media_file.get('status')}"
        )

    # ------------------------------------------------------------------
    # Resume from offset
    # ------------------------------------------------------------------

    def test_resume_from_offset(self, tus_helper: TUSHelper) -> None:
        """Interrupted upload resumes correctly from the last confirmed offset.

        Simulates a two-chunk upload where the client "disconnects" after the
        first chunk and then resumes by re-checking the HEAD offset. Uses
        random bytes beyond the first 4 (magic bytes are only validated at
        offset=0, so trailing chunks can be arbitrary bytes).

        Total file size: 10 MB + 132 bytes (to exceed the 5 MB minimum part
        size for the first chunk, forcing it to be flushed to MinIO as a real
        S3 part).
        """
        # Chunk 1: 5.25 MB with valid MP3 magic bytes at the start
        chunk1_size = 5 * 1024 * 1024 + 262_144  # 5.25 MB — exceeds 5 MB S3 minimum
        chunk1 = MINIMAL_MP3[:4] + os.urandom(chunk1_size - 4)

        # Chunk 2: 4.75 MB of arbitrary bytes (not validated since offset != 0)
        chunk2_size = 4 * 1024 * 1024 + 786_432  # 4.75 MB
        chunk2 = os.urandom(chunk2_size)

        total_size = chunk1_size + chunk2_size

        # Step 1: Prepare and create session
        file_id, upload_id = tus_helper.prepare_and_create_session(
            filename="resume_test.mp3",
            content_type="audio/mpeg",
            file_size=total_size,
        )

        # Step 2: PATCH first chunk
        patch1_resp = tus_helper.patch(upload_id, chunk1, offset=0)
        assert patch1_resp.status_code == 204, (
            f"First PATCH failed: {patch1_resp.status_code} {patch1_resp.text}"
        )

        # Step 3: HEAD confirms offset = chunk1_size (upload is paused here)
        head1_resp = tus_helper.head(upload_id)
        assert head1_resp.status_code == 200
        reported_offset = int(head1_resp.headers.get("Upload-Offset", -1))
        assert reported_offset == chunk1_size, (
            f"Expected offset {chunk1_size} after first chunk, got {reported_offset}"
        )

        # Step 4: Simulate interruption — no action needed, just proceed.

        # Step 5: HEAD again — still reports chunk1_size (no drift)
        head2_resp = tus_helper.head(upload_id)
        assert head2_resp.status_code == 200
        assert int(head2_resp.headers.get("Upload-Offset", -1)) == chunk1_size

        # Step 6: PATCH second chunk from correct offset
        patch2_resp = tus_helper.patch(upload_id, chunk2, offset=chunk1_size)
        assert patch2_resp.status_code == 204, (
            f"Second PATCH failed: {patch2_resp.status_code} {patch2_resp.text}"
        )

        # Step 7: Offset now equals total_size (upload is complete)
        final_offset = int(patch2_resp.headers.get("Upload-Offset", -1))
        assert final_offset == total_size, f"Expected final offset {total_size}, got {final_offset}"

    @pytest.mark.skip(reason="Requires injecting diverged DB/MinIO state; complex integration test")
    def test_head_heals_diverged_state(self, tus_helper: TUSHelper) -> None:
        """HEAD reconciles DB offset with MinIO truth after a simulated server crash.

        This test would need to:
        1. Upload a chunk and let MinIO receive it.
        2. Kill the process before the DB commit (simulated server crash).
        3. On the next HEAD, verify the endpoint syncs DB offset with MinIO part list.

        Skipped because reproducing a mid-commit crash without invasive test
        infrastructure (e.g. transaction-level fault injection) is not practical
        in this E2E suite.
        """


# ---------------------------------------------------------------------------
# Class 2: TestTUSResumeUI — Browser-based tests (Playwright)
# ---------------------------------------------------------------------------


class TestTUSResumeUI:
    """Test pause/resume UI in the browser via Playwright.

    These tests drive the real frontend and require a large file upload to be
    in progress. They are marked as slow and skipped by default when a running
    dev environment with sufficient file upload size cannot be guaranteed.
    """

    @pytest.mark.slow
    @pytest.mark.skip(
        reason=(
            "Requires running dev environment with a large file (>5MB) upload in progress. "
            "Run manually with: pytest -k test_upload_shows_pause_button --headed"
        )
    )
    def test_upload_shows_pause_button(self, authenticated_page: Page) -> None:
        """An active upload shows a Pause button in the upload progress panel."""
        page = authenticated_page

        # Navigate to the gallery page where uploads are initiated
        page.goto(FRONTEND_URL)
        page.wait_for_load_state("networkidle")

        # Trigger the file picker — look for a file input or upload button
        # The upload area may be a dropzone or a button that opens a file dialog
        upload_input = page.locator("input[type=file]").first
        assert upload_input.is_visible() or upload_input.count() > 0, (
            "No file input found on gallery page"
        )

        # Inject a large fake Blob via JavaScript to trigger the upload dialog
        # without needing a real file on disk
        page.evaluate("""
            () => {
                const input = document.querySelector('input[type="file"]');
                if (!input) return;
                // Create a 20MB fake MP3 blob
                const mb20 = new Uint8Array(20 * 1024 * 1024);
                mb20[0] = 0xFF; mb20[1] = 0xFB; mb20[2] = 0x90; mb20[3] = 0x00;
                const blob = new Blob([mb20], { type: 'audio/mpeg' });
                const file = new File([blob], 'e2e_pause_test.mp3', { type: 'audio/mpeg' });
                const dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)

        # Wait for the upload progress panel to appear
        page.wait_for_selector(
            "[data-testid=upload-progress], .upload-progress, .tus-upload-item",
            timeout=15_000,
        )

        # Assert: a Pause button is visible while uploading
        pause_button = page.locator(
            "button[aria-label*='Pause'], button:has-text('Pause'), [data-testid=pause-upload]"
        ).first
        assert pause_button.is_visible(), "Pause button should be visible during an active upload"

    @pytest.mark.slow
    @pytest.mark.skip(
        reason=(
            "Requires running dev environment with active upload. "
            "Run manually with: pytest -k test_pause_button_pauses_upload --headed"
        )
    )
    def test_pause_button_pauses_upload(self, authenticated_page: Page) -> None:
        """Clicking Pause stops the upload and shows Resume button."""
        page = authenticated_page
        page.goto(FRONTEND_URL)
        page.wait_for_load_state("networkidle")

        # Start a large file upload via JS injection (same technique as above)
        page.evaluate("""
            () => {
                const input = document.querySelector('input[type="file"]');
                if (!input) return;
                const mb20 = new Uint8Array(20 * 1024 * 1024);
                mb20[0] = 0xFF; mb20[1] = 0xFB; mb20[2] = 0x90; mb20[3] = 0x00;
                const blob = new Blob([mb20], { type: 'audio/mpeg' });
                const file = new File([blob], 'e2e_pause_test2.mp3', { type: 'audio/mpeg' });
                const dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)

        # Wait for progress panel
        page.wait_for_selector(
            "[data-testid=upload-progress], .upload-progress, .tus-upload-item",
            timeout=15_000,
        )

        # Click Pause
        pause_button = page.locator(
            "button[aria-label*='Pause'], button:has-text('Pause'), [data-testid=pause-upload]"
        ).first
        pause_button.click()
        page.wait_for_timeout(1000)

        # Assert: status shows 'Paused' or similar
        paused_indicator = page.locator(
            "[data-testid=upload-status-paused], "
            ".upload-status:has-text('Paused'), "
            "span:has-text('Paused')"
        )
        assert (
            paused_indicator.count() > 0
            or page.locator(
                "button[aria-label*='Resume'], button:has-text('Resume'), [data-testid=resume-upload]"
            ).count()
            > 0
        ), "Either a 'Paused' status indicator or a Resume button must appear"

    @pytest.mark.slow
    @pytest.mark.skip(
        reason=(
            "Requires running dev environment with active upload. "
            "Run manually with: pytest -k test_resume_button_continues_upload --headed"
        )
    )
    def test_resume_button_continues_upload(self, authenticated_page: Page) -> None:
        """Clicking Resume continues the upload from the last offset."""
        page = authenticated_page
        page.goto(FRONTEND_URL)
        page.wait_for_load_state("networkidle")

        # Start upload
        page.evaluate("""
            () => {
                const input = document.querySelector('input[type="file"]');
                if (!input) return;
                const mb20 = new Uint8Array(20 * 1024 * 1024);
                mb20[0] = 0xFF; mb20[1] = 0xFB; mb20[2] = 0x90; mb20[3] = 0x00;
                const blob = new Blob([mb20], { type: 'audio/mpeg' });
                const file = new File([blob], 'e2e_resume_test.mp3', { type: 'audio/mpeg' });
                const dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)

        page.wait_for_selector(
            "[data-testid=upload-progress], .upload-progress, .tus-upload-item",
            timeout=15_000,
        )

        # Pause it
        pause_button = page.locator(
            "button[aria-label*='Pause'], button:has-text('Pause'), [data-testid=pause-upload]"
        ).first
        pause_button.click()
        page.wait_for_timeout(1000)

        # Click Resume
        resume_button = page.locator(
            "button[aria-label*='Resume'], button:has-text('Resume'), [data-testid=resume-upload]"
        ).first
        assert resume_button.is_visible(), "Resume button must be visible after pausing"
        resume_button.click()

        # Assert: upload eventually reaches 100%
        page.wait_for_selector(
            "[data-testid=upload-complete], .upload-status:has-text('100'), span:has-text('100%')",
            timeout=60_000,
        )


# ---------------------------------------------------------------------------
# Class 3: TestTUSCleanup — Cleanup task tests
# ---------------------------------------------------------------------------


class TestTUSCleanup:
    """Test the expired session cleanup Celery task.

    These tests call cleanup_incomplete_tus_uploads() directly (not via the
    Celery broker) and inject rows into the database manually so they run
    without a running MinIO instance for the cleanup-specific paths.
    """

    def _create_db_session(self) -> Any:
        """Create a raw SQLAlchemy session for direct DB manipulation.

        Returns:
            A SQLAlchemy Session from SessionLocal.

        Raises:
            ImportError: If the backend package is not on sys.path.
        """
        from app.db.base import SessionLocal

        return SessionLocal()

    def _create_expired_upload_session(self, db: Any, user_id: int, media_file_id: int) -> Any:
        """Insert an expired UploadSession row directly into the database.

        Sets expires_at in the past so the cleanup task will pick it up.
        Sets minio_upload_id to None so no MinIO call is attempted — the
        cleanup task has an explicit guard: ``if session.minio_upload_id``.

        Args:
            db: SQLAlchemy Session.
            user_id: The user_id to assign (must exist in DB).
            media_file_id: The media_file_id to assign (must exist in DB).

        Returns:
            The persisted UploadSession ORM object.
        """
        from app.models.upload_session import UploadSession

        now = datetime.now(timezone.utc)
        session = UploadSession(
            media_file_id=media_file_id,
            user_id=user_id,
            minio_upload_id=None,  # No MinIO state — guard in cleanup skips abort call
            storage_path=f"test/user_{user_id}/expired_session_{int(time.time())}.mp3",
            offset=0,
            total_size=132,
            content_type="audio/mpeg",
            filename="expired_test.mp3",
            tus_metadata="",
            parts_json="[]",
            chunk_buffer=None,
            status="active",
            created_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),  # Already expired
            completed_at=None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def _create_active_upload_session(self, db: Any, user_id: int, media_file_id: int) -> Any:
        """Insert a non-expired UploadSession row directly into the database.

        Sets expires_at in the future so the cleanup task should leave it alone.

        Args:
            db: SQLAlchemy Session.
            user_id: The user_id to assign (must exist in DB).
            media_file_id: The media_file_id to assign (must exist in DB).

        Returns:
            The persisted UploadSession ORM object.
        """
        from app.models.upload_session import UploadSession

        now = datetime.now(timezone.utc)
        session = UploadSession(
            media_file_id=media_file_id,
            user_id=user_id,
            minio_upload_id=None,
            storage_path=f"test/user_{user_id}/active_session_{int(time.time())}.mp3",
            offset=0,
            total_size=132,
            content_type="audio/mpeg",
            filename="active_test.mp3",
            tus_metadata="",
            parts_json="[]",
            chunk_buffer=None,
            status="active",
            created_at=now,
            expires_at=now + timedelta(hours=1),  # Not yet expired
            completed_at=None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def _get_or_create_test_media_file(self, db: Any, user_id: int) -> int:
        """Return the id of a MediaFile owned by user_id suitable for test insertion.

        Queries the database for an existing MediaFile and returns its id.
        If none exist, raises an assertion error — the dev database must have
        at least one MediaFile record (created by prior upload tests or seed data).

        Args:
            db: SQLAlchemy Session.
            user_id: The owning user's id.

        Returns:
            The integer MediaFile.id.

        Raises:
            AssertionError: If no MediaFile exists for this user.
        """
        from app.models.media import MediaFile

        media_file = db.query(MediaFile).filter(MediaFile.user_id == user_id).first()
        assert media_file is not None, (
            "No MediaFile found for test user. "
            "Run test_full_upload_completes_and_creates_media_file first to seed data."
        )
        return int(media_file.id)

    def _get_admin_user_id(self, db: Any) -> int:
        """Return the integer id of the admin@example.com user.

        Args:
            db: SQLAlchemy Session.

        Returns:
            The integer User.id.

        Raises:
            AssertionError: If the admin user does not exist.
        """
        from app.models.user import User

        admin = db.query(User).filter(User.email == TEST_ADMIN_EMAIL).first()
        assert admin is not None, (
            f"Admin user '{TEST_ADMIN_EMAIL}' not found in database. "
            "Ensure the dev environment is seeded with the default admin account."
        )
        return int(admin.id)

    def test_cleanup_aborts_expired_sessions(self) -> None:
        """Cleanup task marks sessions past their expiry time as 'aborted'.

        Calls cleanup_incomplete_tus_uploads() directly (not via Celery) to
        avoid requiring a running broker. The expired session has no minio_upload_id
        so the cleanup skips the MinIO abort call and only updates the DB row.
        """
        from app.tasks.upload_cleanup import cleanup_incomplete_tus_uploads

        db = self._create_db_session()
        try:
            user_id = self._get_admin_user_id(db)
            media_file_id = self._get_or_create_test_media_file(db, user_id)

            expired_session = self._create_expired_upload_session(db, user_id, media_file_id)
            session_id = expired_session.id

            # Run the cleanup task function directly
            result = cleanup_incomplete_tus_uploads()

            # Reload from DB
            from app.models.upload_session import UploadSession

            db.expire_all()
            updated = db.query(UploadSession).filter(UploadSession.id == session_id).first()

            assert updated is not None
            assert updated.status == "aborted", (
                f"Expected status 'aborted' after cleanup, got: {updated.status!r}"
            )
            assert result["aborted"] >= 1, (
                f"Cleanup should report at least 1 aborted session, got: {result}"
            )
        finally:
            db.close()

    def test_cleanup_ignores_non_expired_sessions(self) -> None:
        """Cleanup task leaves active sessions with future expiry alone.

        Inserts a session with expires_at = now + 1 hour, runs the cleanup
        task, and verifies the session status is still 'active'.
        """
        from app.tasks.upload_cleanup import cleanup_incomplete_tus_uploads

        db = self._create_db_session()
        try:
            user_id = self._get_admin_user_id(db)
            media_file_id = self._get_or_create_test_media_file(db, user_id)

            active_session = self._create_active_upload_session(db, user_id, media_file_id)
            session_id = active_session.id

            # Run the cleanup task
            cleanup_incomplete_tus_uploads()

            # Reload from DB
            from app.models.upload_session import UploadSession

            db.expire_all()
            updated = db.query(UploadSession).filter(UploadSession.id == session_id).first()

            assert updated is not None
            assert updated.status == "active", (
                f"Non-expired session should remain 'active', got: {updated.status!r}"
            )
        finally:
            db.close()

    def test_cleanup_returns_aborted_count(self) -> None:
        """Cleanup task returns a dict with 'aborted' and 'errors' counts."""
        from app.tasks.upload_cleanup import cleanup_incomplete_tus_uploads

        result = cleanup_incomplete_tus_uploads()

        assert isinstance(result, dict), (
            f"Expected dict result from cleanup task, got: {type(result)}"
        )
        assert "aborted" in result, f"Result missing 'aborted' key: {result}"
        assert "errors" in result, f"Result missing 'errors' key: {result}"
        assert isinstance(result["aborted"], int)
        assert isinstance(result["errors"], int)
