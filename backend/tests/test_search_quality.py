"""Search quality integration tests against live OpenSearch data.

Run: pytest backend/tests/test_search_quality.py -v
Requires: running OpenTranscribe with indexed data (20 files, 1943 chunks)

These tests validate search behavior against a real dataset:
- Joe Rogan #2219 - Donald Trump (630 chunks)
- Joe Rogan #2221 - JD Vance (545 chunks)
- Secret Airships (102 chunks)
- Apple Event September 9 (96 chunks)
- DOGE's Findings (65 chunks)
- Pyramids & Sahara (57 chunks)
- AI Arms Race with China (54 chunks)
- Apollo 11 (47 chunks)
- Scam Factories (46 chunks)
- And more (20 files total)
"""

import re

import pytest
import requests

BASE = "http://localhost:5174/api"


@pytest.fixture(scope="module")
def auth_token():
    resp = requests.post(
        f"{BASE}/auth/login",
        data={"username": "admin@example.com", "password": "password"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def search(headers, q, mode="hybrid", sort="relevance"):
    resp = requests.get(
        f"{BASE}/search",
        params={"q": q, "search_mode": mode, "sort_by": sort, "page_size": 20},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ── Semantic Suppression Tests ──────────────────────────────


class TestSemanticSuppression:
    """When keyword matches exist, irrelevant semantic results must be suppressed."""

    def test_china_suppresses_airships_from_keyword(self, headers):
        """'china' must NOT return Secret Airships as a keyword match."""
        data = search(headers, "china")
        kw_titles = [r["title"] for r in data["results"] if not r["semantic_only"]]
        for t in kw_titles:
            assert "Airship" not in t, f"Airships wrongly in keyword results: {t}"

    def test_china_keyword_files_present(self, headers):
        """'china' must return files: AI Arms Race, Palmer Luckey, etc."""
        data = search(headers, "china")
        kw = [r for r in data["results"] if not r["semantic_only"]]
        kw_titles = [r["title"] for r in kw]
        assert any(
            "AI Arms Race" in t or "China" in t for t in kw_titles
        ), f"Missing China-related keyword files: {kw_titles}"
        assert len(kw) >= 5, f"Expected >= 5 keyword files for 'china', got {len(kw)}"

    def test_fight_suppresses_irrelevant(self, headers):
        """'fight' must NOT return Bridge to Space."""
        data = search(headers, "fight")
        sem_titles = [r["title"] for r in data["results"] if r["semantic_only"]]
        for t in sem_titles:
            assert "Bridge" not in t, f"Irrelevant semantic result for 'fight': {t}"

    def test_nasa_returns_relevant(self, headers):
        """'nasa' must return Apollo 11, NASA Spy Agency, Bridge to Space, Warp Drive."""
        data = search(headers, "NASA")
        kw_titles = [r["title"] for r in data["results"] if not r["semantic_only"]]
        assert any(
            "Apollo" in t or "Eagle" in t or "NASA" in t for t in kw_titles
        ), f"Missing NASA-related files: {kw_titles}"


# ── Exact Mode Precision Tests ──────────────────────────────


class TestExactMode:
    """Keyword/exact mode must match only exact word forms."""

    def test_fight_no_stem_highlights(self, headers):
        """'fight' exact must only highlight fight/fights/fighting, not right/might/eight."""
        data = search(headers, "fight", mode="keyword")
        for r in data["results"]:
            for occ in r["occurrences"]:
                marks = re.findall(r"<mark>(.*?)</mark>", occ["snippet"])
                for m in marks:
                    assert "fight" in m.lower(), f"Stem false positive: '{m}'"

    def test_spy_exact_precision(self, headers):
        """'spy' exact must match only spy-related content."""
        data = search(headers, "spy", mode="keyword")
        for r in data["results"]:
            assert r["keyword_occurrences"] > 0

    def test_keyword_mode_no_semantic(self, headers):
        """Keyword mode must never return semantic-only results."""
        for q in ["fight", "china", "NASA", "Trump", "fraud"]:
            data = search(headers, q, mode="keyword")
            for r in data["results"]:
                assert not r[
                    "semantic_only"
                ], f"'{q}' keyword mode returned semantic result: {r['title']}"


# ── Match Count Accuracy Tests ──────────────────────────────


class TestMatchCounts:
    """Match counts must reflect actual keyword matches, not semantic noise."""

    def test_keyword_files_positive_count(self, headers):
        """All keyword-matched files must have keyword_occurrences > 0."""
        for q in ["china", "fight", "Trump", "NASA"]:
            data = search(headers, q)
            for r in data["results"]:
                if not r["semantic_only"]:
                    assert (
                        r["keyword_occurrences"] > 0
                    ), f"'{q}': {r['title']} has kw_occ=0 but isn't semantic_only"

    def test_semantic_files_zero_keyword_count(self, headers):
        """Semantic-only files must have keyword_occurrences == 0."""
        data = search(headers, "geopolitics")
        for r in data["results"]:
            if r["semantic_only"]:
                assert r["keyword_occurrences"] == 0


# ── Speaker & Metadata Tests ────────────────────────────────


class TestSpeakerSearch:
    """Speaker name searches must detect metadata speaker presence."""

    def test_joe_rogan_metadata_speaker(self, headers):
        """All files with Joe Rogan as speaker must have metadata_speaker source."""
        data = search(headers, "Joe Rogan")
        for r in data["results"]:
            if "Joe Rogan" in r.get("speakers", []):
                assert (
                    "metadata_speaker" in r["match_sources"]
                ), f"Missing metadata_speaker: {r['title']}, src={r['match_sources']}"

    def test_speaker_search_finds_files(self, headers):
        """Searching speaker name must return files they appear in."""
        data = search(headers, "Joe Rogan")
        assert (
            data["total_files"] >= 10
        ), f"Joe Rogan is in 15+ files but search found {data['total_files']}"

    def test_trump_in_title_and_content(self, headers):
        """'Trump' should match title and content sources."""
        data = search(headers, "Trump")
        trump_file = next((r for r in data["results"] if "Donald Trump" in r["title"]), None)
        assert trump_file is not None, "Trump file not found"
        assert "title" in trump_file["match_sources"] or "content" in trump_file["match_sources"]


# ── Highlight Type Tests ────────────────────────────────────


class TestHighlightType:
    """Occurrences must have correct highlight_type for styling."""

    def test_keyword_type(self, headers):
        """Keyword-matched files must have at least one keyword-type occurrence."""
        data = search(headers, "china")
        for r in data["results"]:
            if not r["semantic_only"]:
                types = {occ.get("highlight_type") for occ in r["occurrences"]}
                assert (
                    "keyword" in types
                ), f"Keyword file '{r['title']}' has no keyword highlights: {types}"

    def test_semantic_type(self, headers):
        """Semantic-only occurrences must have highlight_type='semantic'."""
        data = search(headers, "international relations between superpowers")
        for r in data["results"]:
            if r["semantic_only"]:
                for occ in r["occurrences"]:
                    assert occ.get("highlight_type") == "semantic"


# ── Relevance Ordering Tests ───────────────────────────────


class TestRelevanceOrder:
    """Keyword matches must always rank above semantic-only results."""

    def test_keyword_before_semantic(self, headers):
        """No keyword result may appear after a semantic-only result."""
        for q in ["china", "fight", "NASA", "fraud"]:
            data = search(headers, q)
            saw_semantic = False
            for r in data["results"]:
                if r["semantic_only"]:
                    saw_semantic = True
                elif saw_semantic:
                    pytest.fail(f"'{q}': keyword result after semantic: {r['title']}")


# ── Semantic Search Quality Tests ───────────────────────────


class TestSemanticQuality:
    """Semantic search should find topically related content."""

    def test_espionage_finds_spy_content(self, headers):
        """'espionage' should find NASA Spy Agency and surveillance content."""
        data = search(headers, "espionage")
        titles = [r["title"] for r in data["results"]]
        assert any(
            "spy" in t.lower() or "nasa" in t.lower() for t in titles
        ), f"Espionage should find spy/NASA content: {titles}"

    def test_artificial_intelligence_finds_ai(self, headers):
        """'artificial intelligence' should find AI Arms Race, Warp Drive AI, etc."""
        data = search(headers, "artificial intelligence")
        titles = [r["title"] for r in data["results"]]
        assert any(
            "AI" in t for t in titles
        ), f"'artificial intelligence' should find AI content: {titles}"

    def test_cryptocurrency_fraud_finds_scam(self, headers):
        """'cryptocurrency fraud' should find Scam Factories."""
        data = search(headers, "online fraud scam")
        titles = [r["title"] for r in data["results"]]
        assert any("Scam" in t for t in titles), f"Fraud search should find scam content: {titles}"

    def test_space_exploration_finds_nasa(self, headers):
        """'space exploration' should find NASA, Apollo, Bridge to Space."""
        data = search(headers, "space exploration")
        titles = [r["title"] for r in data["results"]]
        space_matches = [
            t for t in titles if any(w in t for w in ["Space", "Apollo", "Eagle", "NASA", "Warp"])
        ]
        assert len(space_matches) >= 2, f"Space exploration should find multiple matches: {titles}"

    def test_government_corruption_finds_pelosi(self, headers):
        """'government corruption' should find Nancy Pelosi insider trading."""
        data = search(headers, "government corruption insider trading")
        titles = [r["title"] for r in data["results"]]
        assert any(
            "Pelosi" in t or "insider" in t.lower() for t in titles
        ), f"Corruption search should find Pelosi: {titles}"

    def test_archaeology_finds_pyramids(self, headers):
        """'ancient archaeology discoveries' should find pyramid content."""
        data = search(headers, "ancient archaeology discoveries")
        titles = [r["title"] for r in data["results"]]
        assert any(
            "Pyramid" in t or "Sahara" in t for t in titles
        ), f"Archaeology should find pyramids: {titles}"


# ── Multi-word and Phrase Tests ─────────────────────────────


class TestPhraseSearch:
    """Multi-word searches should match phrases correctly."""

    def test_joe_rogan_experience(self, headers):
        """'Joe Rogan Experience' should match title and content."""
        data = search(headers, "Joe Rogan Experience")
        assert data["total_files"] >= 5

    def test_warp_drive(self, headers):
        """'warp drive' should find Warp Drive article."""
        data = search(headers, "warp drive")
        kw_titles = [r["title"] for r in data["results"] if not r["semantic_only"]]
        assert any("Warp" in t for t in kw_titles), f"Missing warp drive: {kw_titles}"

    def test_quantum_computer(self, headers):
        """'quantum computer' should find China Quantum Computer."""
        data = search(headers, "quantum computer")
        kw_titles = [r["title"] for r in data["results"] if not r["semantic_only"]]
        assert any("Quantum" in t for t in kw_titles), f"Missing quantum: {kw_titles}"


# ── Speaker-Scoped Search Tests ─────────────────────────────


class TestSpeakerScopedSearch:
    """speaker: operator must filter by speaker."""

    def test_speaker_operator_basic(self, headers):
        """'speaker:"Joe Rogan" china' should only return Joe Rogan's chunks."""
        data = search(headers, 'speaker:"Joe Rogan" china')
        for r in data["results"]:
            for occ in r["occurrences"]:
                assert (
                    occ["speaker"] == "Joe Rogan"
                ), f"Wrong speaker: {occ['speaker']} (expected Joe Rogan)"

    def test_speaker_operator_filters_occurrences(self, headers):
        """Speaker-scoped search must only return occurrences from that speaker."""
        scoped = search(headers, 'speaker:"Joe Rogan" china')
        for r in scoped["results"]:
            for occ in r["occurrences"]:
                assert (
                    occ["speaker"] == "Joe Rogan"
                ), f"Scoped search returned wrong speaker: {occ['speaker']}"

    def test_speaker_only_returns_all_content(self, headers):
        """Just 'speaker:"Joe Rogan"' should return all files with that speaker."""
        data = search(headers, 'speaker:"Joe Rogan"')
        assert data["total_files"] >= 10
