# E2E Test Expansion Plan for OpenTranscribe

## Executive Summary

This document provides a comprehensive implementation plan for expanding the E2E testing capabilities of the OpenTranscribe application. The plan covers:
- Additional E2E test coverage for Gallery, File Upload, Settings, Transcription, Speaker Management, and Search
- Test runner scripts for convenience
- Mobile/responsive testing support
- GitHub Actions CI workflow
- Visual regression testing
- Combined API + E2E test patterns

---

## 1. Current State Analysis

### Existing Test Infrastructure
**Location:** `backend/tests/e2e/`

**Files:**
- `conftest.py` - Fixtures including `login_page`, `authenticated_page`, `auth_helper`, `api_helper`, `console_errors`
- `test_login.py` - ~50 tests covering form validation, success/failure scenarios, security, session, UI, accessibility
- `test_registration.py` - ~35 tests covering form validation, password requirements, duplicate prevention
- `test_auth_flow.py` - Combined authentication flow tests
- `pytest.ini` - E2E test configuration with markers
- `README.md` - Documentation for running tests

**Key Fixtures Available:**
```python
@pytest.fixture
def login_page(page: Page, base_url: str)  # Navigates to login page

@pytest.fixture
def authenticated_page(page: Page, base_url: str)  # Logged in as admin

@pytest.fixture
def auth_helper(page: Page, base_url: str)  # AuthHelper class instance

@pytest.fixture
def api_helper(backend_url: str)  # APIHelper for backend calls
```

---

## 2. Test Files and URLs for Upload/Processing Tests

### Test Media Files

Create minimal test files in `backend/tests/e2e/fixtures/`:

| File | Type | Duration | Size | Purpose |
|------|------|----------|------|---------|
| `test_audio_short.mp3` | Audio | 5 seconds | ~100KB | Quick upload test |
| `test_audio_speech.mp3` | Audio | 30 seconds | ~500KB | Transcription test with speech |
| `test_video_short.mp4` | Video | 5 seconds | ~500KB | Video upload test |
| `test_audio_multi_speaker.mp3` | Audio | 60 seconds | ~1MB | Diarization test |

**Source for Test Files:**
- Use royalty-free audio from [freesound.org](https://freesound.org) or similar
- Or generate with text-to-speech for predictable transcription content
- Keep files small to speed up tests

### Test URLs for URL Upload

**Recommended Test URLs (Public, Short, Reliable):**

```python
# backend/tests/e2e/conftest.py

TEST_URLS = {
    # YouTube - Short, public domain content
    "youtube_short": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley (known content)

    # Archive.org - Public domain, reliable
    "archive_speech": "https://archive.org/details/MLKDream",  # MLK speech (public domain)

    # Direct MP3 URLs (more reliable for testing)
    "direct_mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",

    # Short test videos
    "sample_video": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4",
}

# URLs that should FAIL (for error handling tests)
TEST_INVALID_URLS = {
    "not_a_url": "not-a-valid-url",
    "invalid_domain": "https://this-domain-does-not-exist-12345.com/video.mp4",
    "private_video": "https://www.youtube.com/watch?v=private123",  # Private/unavailable
    "requires_auth": "https://vimeo.com/private-video",  # Requires login
}
```

### Upload Test Fixtures

```python
# backend/tests/e2e/conftest.py additions

import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def test_audio_file():
    """Path to short test audio file."""
    path = FIXTURES_DIR / "test_audio_short.mp3"
    if not path.exists():
        pytest.skip("Test audio file not found. Run: scripts/e2e/setup-test-files.sh")
    return str(path)

@pytest.fixture
def test_video_file():
    """Path to short test video file."""
    path = FIXTURES_DIR / "test_video_short.mp4"
    if not path.exists():
        pytest.skip("Test video file not found. Run: scripts/e2e/setup-test-files.sh")
    return str(path)

@pytest.fixture
def test_speech_file():
    """Path to audio file with known speech content for transcription verification."""
    path = FIXTURES_DIR / "test_audio_speech.mp3"
    if not path.exists():
        pytest.skip("Test speech file not found")
    return str(path)

@pytest.fixture
def test_youtube_url():
    """A short, public YouTube video URL for testing."""
    return "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # First YouTube video (18 sec)

@pytest.fixture
def test_invalid_url():
    """An invalid URL for error handling tests."""
    return "https://invalid-domain-12345.com/video.mp4"
```

### Test File Setup Script

Create `scripts/e2e/setup-test-files.sh`:

```bash
#!/bin/bash
# Setup test files for E2E tests

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIXTURES_DIR="$PROJECT_ROOT/backend/tests/e2e/fixtures"

mkdir -p "$FIXTURES_DIR"

echo "Downloading test files..."

# Short audio file (SoundHelix - royalty free)
curl -L "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3" \
    -o "$FIXTURES_DIR/test_audio_short.mp3" \
    --max-time 30

# Sample video (Big Buck Bunny snippet)
curl -L "https://sample-videos.com/video321/mp4/240/big_buck_bunny_240p_1mb.mp4" \
    -o "$FIXTURES_DIR/test_video_short.mp4" \
    --max-time 30

echo "Test files downloaded to: $FIXTURES_DIR"
ls -la "$FIXTURES_DIR"
```

---

## 3. Implementation Phases

### Phase 1: Gallery Page Tests (Priority: High)

**File:** `backend/tests/e2e/test_gallery.py`

**Test Classes:**
- `TestGalleryPageLoad` - Initial load, file cards, empty state
- `TestGalleryFilters` - Filter sidebar, tag/speaker/date filters
- `TestGallerySorting` - Sort by date, name, duration
- `TestGalleryPagination` - Infinite scroll, load more
- `TestGalleryViewModes` - Grid/list view toggle
- `TestGallerySelection` - Select files, bulk actions
- `TestGalleryFileCards` - Card content, click navigation

---

### Phase 2: File Upload Tests (Priority: High)

**File:** `backend/tests/e2e/test_upload.py`

**Test Classes:**

```python
class TestUploadModal:
    """Tests for upload modal."""
    - test_add_button_visible
    - test_click_add_opens_modal
    - test_modal_has_tabs

class TestFileUpload:
    """Tests for direct file upload."""
    - test_file_tab_visible
    - test_drag_drop_zone
    - test_upload_audio_file(test_audio_file)
    - test_upload_video_file(test_video_file)
    - test_upload_progress_indicator
    - test_upload_success_notification
    - test_file_appears_in_gallery
    - test_cancel_upload

class TestURLUpload:
    """Tests for URL-based upload."""
    - test_url_tab_clickable
    - test_url_input_field
    - test_submit_youtube_url(test_youtube_url)
    - test_url_validation_shown
    - test_invalid_url_error(test_invalid_url)
    - test_url_download_progress

class TestUploadProcessing:
    """Tests for transcription processing after upload."""
    - test_file_shows_processing_status
    - test_processing_progress_updates
    - test_completed_file_has_transcript
    - test_processing_can_be_cancelled

class TestSpeakerSettings:
    """Tests for speaker diarization settings during upload."""
    - test_advanced_settings_expandable
    - test_min_max_speakers_inputs
    - test_speaker_count_validation
```

---

### Phase 3: Settings/Profile Tests (Priority: Medium)

**File:** `backend/tests/e2e/test_settings.py`

**Test Classes:**
- `TestSettingsModalOpen` - Open/close modal
- `TestProfileSection` - Name, email updates
- `TestPasswordSection` - Password change
- `TestLanguageSettings` - Locale change
- `TestTranscriptionSettings` - Speaker defaults
- `TestAdminSettings` - Admin-only sections

---

### Phase 4: Transcription Viewing/Editing Tests (Priority: Medium)

**File:** `backend/tests/e2e/test_transcription.py`

**Test Classes:**
- `TestFileDetailPageLoad` - Page loads, player visible
- `TestTranscriptDisplay` - Segments, speakers, timestamps
- `TestTranscriptEditing` - Edit text, save changes
- `TestSpeakerEditing` - Rename, merge speakers
- `TestSummaryGeneration` - AI summary (if LLM available)

---

### Phase 5: Search Functionality Tests (Priority: Medium)

**File:** `backend/tests/e2e/test_search.py`

**Test Classes:**
- `TestSearchPageAccess` - Navigate to search
- `TestSearchInput` - Type query, submit
- `TestSearchResults` - Results display, click to open
- `TestSearchFilters` - Filter results
- `TestSearchSorting` - Sort results
- `TestSearchPagination` - Page through results

---

### Phase 6: Test Runner Scripts (Priority: Medium)

**Directory:** `scripts/e2e/`

| Script | Purpose |
|--------|---------|
| `run-e2e-tests.sh` | Run all E2E tests headless |
| `run-e2e-headed.sh` | Run with visible browser (XRDP) |
| `run-e2e-smoke.sh` | Quick smoke tests only |
| `run-e2e-upload.sh` | Run only upload tests |
| `setup-test-files.sh` | Download test media files |

---

### Phase 7: Mobile/Responsive Tests (Priority: Low)

**File:** `backend/tests/e2e/test_responsive.py`

**Viewport Configurations:**
```python
VIEWPORTS = {
    "mobile": {"width": 375, "height": 667},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1920, "height": 1080},
}
```

---

### Phase 8: GitHub Actions CI Workflow (Priority: High)

**File:** `.github/workflows/e2e-tests.yml`

- Runs on PR to main/develop
- Sets up services (postgres)
- Installs dependencies
- Runs smoke tests by default
- Uploads screenshots on failure

---

### Phase 9: Visual Regression Testing (Priority: Low)

**File:** `backend/tests/e2e/test_visual.py`

- Screenshot comparison for key pages
- Baseline management

---

### Phase 10: Combined API + E2E Tests (Priority: Medium)

**File:** `backend/tests/e2e/test_api_e2e_combined.py`

- Create data via API, verify in browser
- Create user via API, login via UI
- Upload via API, verify in gallery

---

## 4. Implementation Order

| Week | Phase | Description |
|------|-------|-------------|
| 1 | Phase 1, 8 | Gallery tests + CI workflow |
| 2 | Phase 2 | Upload tests (with test files) |
| 3 | Phase 3, 4 | Settings + Transcription tests |
| 4 | Phase 5, 6 | Search tests + Runner scripts |
| Future | Phase 7, 9, 10 | Responsive, Visual, API+E2E |

---

## 5. Directory Structure After Implementation

```
backend/tests/e2e/
├── conftest.py              # Enhanced with new fixtures
├── pytest.ini               # Updated with new markers
├── README.md                # Updated documentation
├── fixtures/                # Test data files
│   ├── test_audio_short.mp3
│   ├── test_audio_speech.mp3
│   ├── test_video_short.mp4
│   └── README.md            # Source attribution
├── screenshots/             # Screenshot output
├── test_auth_flow.py        # Existing
├── test_login.py            # Existing
├── test_registration.py     # Existing
├── test_gallery.py          # NEW
├── test_upload.py           # NEW
├── test_settings.py         # NEW
├── test_transcription.py    # NEW
├── test_search.py           # NEW
├── test_responsive.py       # NEW
├── test_visual.py           # NEW
└── test_api_e2e_combined.py # NEW

scripts/e2e/
├── run-e2e-tests.sh         # NEW
├── run-e2e-headed.sh        # NEW
├── run-e2e-smoke.sh         # NEW
├── run-e2e-upload.sh        # NEW
└── setup-test-files.sh      # NEW

.github/workflows/
└── e2e-tests.yml            # NEW
```

---

## 6. Test Markers

Update `backend/tests/e2e/pytest.ini`:

```ini
[pytest]
base_url = http://localhost:5173
addopts = --browser chromium

markers =
    slow: marks tests as slow
    smoke: marks tests for smoke testing
    auth: authentication tests
    gallery: gallery page tests
    upload: upload functionality tests
    settings: settings tests
    transcription: transcription tests
    search: search tests
    responsive: responsive/mobile tests
    visual: visual regression tests
    api_e2e: combined API and E2E tests
```

---

## 7. Running Specific Test Categories

```bash
# Smoke tests only (fast)
pytest backend/tests/e2e/ -m smoke -v

# Upload tests
pytest backend/tests/e2e/ -m upload -v

# All except slow
pytest backend/tests/e2e/ -m "not slow" -v

# Gallery and search
pytest backend/tests/e2e/ -m "gallery or search" -v
```

---

## 8. Test Credentials

| User | Email | Password | Role |
|------|-------|----------|------|
| Admin | admin@example.com | password | admin |
| Test users | UUID-generated | TestPassword123! | user |

---

## Notes

- All tests should work both headless and with visible browser (XRDP display :13)
- Test files should be small to keep tests fast
- Use `page.wait_for_load_state("networkidle")` after navigation
- Capture console errors with `console_errors` fixture
- Take screenshots on failure for debugging
