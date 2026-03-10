"""
tests/test_repositories/test_file_repository.py
================================================
Deterministic integration tests for FileRepository.

Focus areas
-----------
1.  Persistence round-trip  — write articles/scores, reload a *new* instance,
    verify exact counts and field values survive intact.
2.  Latest-write-wins (BiasScore upsert)  — verified in-memory AND after reload.
3.  First-write-wins (Article dedup)  — same id never duplicated on disk.
4.  list_articles ordering  — newest published_at first; ties broken by
    insertion order.
5.  list_articles filtering  — by source, by since, by limit, combined.
6.  Graceful None returns  — unknown ids do not raise.
7.  Auto-create data directory  — repo works even if base_dir does not yet
    exist.
8.  Batch add_articles return value  — (new, existing) counts are exact.
9.  Score slot semantics  — one slot per article_id; any provider's record
    occupies that slot (latest wins regardless of provider name change).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.file_repository import FileRepository


# ── shared helpers ────────────────────────────────────────────────────────────

def _article(
    title: str,
    url: str,
    source: str = "TestSource",
    published_at: str | None = None,
    summary: str | None = None,
) -> Article:
    return Article.create(
        title=title,
        url=url,
        source=source,
        published_at=published_at,
        summary=summary,
    )


def _score(
    article: Article,
    *,
    label: str = "center",
    confidence: float = 0.5,
    provider: str = "mock",
    timestamp: datetime | None = None,
) -> BiasScore:
    return BiasScore(
        article_id=article.id,
        provider=provider,
        overall_bias_label=label,
        rhetorical_bias=[],
        claim_checks=[],
        confidence=confidence,
        timestamp=timestamp or datetime(2026, 3, 4, 12, 0, 0),
        raw_response=None,
    )


def _reload(tmp_path: Path) -> FileRepository:
    """Return a brand-new FileRepository instance pointing at *tmp_path*."""
    return FileRepository(base_dir=tmp_path)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def repo(tmp_path: Path) -> FileRepository:
    return FileRepository(base_dir=tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Persistence round-trip
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistenceRoundTrip:
    """Write to disk via one instance; verify a second instance loads the data."""

    def test_articles_survive_reload(self, tmp_path: Path) -> None:
        a1 = _article("Article One", "https://example.com/1", published_at="2026-03-04T10:00:00Z")
        a2 = _article("Article Two", "https://example.com/2", published_at="2026-03-04T11:00:00Z")

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([a1, a2])

        repo2 = _reload(tmp_path)
        assert repo2.get_article(a1.id) == a1
        assert repo2.get_article(a2.id) == a2
        assert len(repo2.list_articles()) == 2

    def test_article_fields_are_exact_after_reload(self, tmp_path: Path) -> None:
        a = _article(
            "Field Fidelity Test",
            "https://bbc.co.uk/news/field-test",
            source="BBC News",
            published_at="2026-03-04T09:30:00Z",
            summary="Every field should survive the round-trip.",
        )
        FileRepository(base_dir=tmp_path).add_articles([a])

        loaded = _reload(tmp_path).get_article(a.id)
        assert loaded is not None
        assert loaded.id == a.id
        assert loaded.title == a.title
        assert loaded.url == a.url
        assert loaded.source == a.source
        assert loaded.published_at == a.published_at
        assert loaded.summary == a.summary

    def test_score_fields_are_exact_after_reload(self, tmp_path: Path) -> None:
        a = _article("Score Field Test", "https://example.com/sft")
        s = BiasScore(
            article_id=a.id,
            provider="mock",
            overall_bias_label="left",
            rhetorical_bias=["loaded_language", "framing"],
            claim_checks=[{"claim_text": "X", "verdict": "supported", "evidence": []}],
            confidence=0.73,
            timestamp=datetime(2026, 3, 4, 15, 22, 7),
            raw_response={"raw": "data"},
        )

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([a])
        repo1.upsert_bias_score(s)

        loaded = _reload(tmp_path).get_bias_score(a.id)
        assert loaded is not None
        assert loaded.article_id == s.article_id
        assert loaded.provider == s.provider
        assert loaded.overall_bias_label == s.overall_bias_label
        assert loaded.rhetorical_bias == s.rhetorical_bias
        assert loaded.claim_checks == s.claim_checks
        assert abs(loaded.confidence - s.confidence) < 1e-9
        assert loaded.timestamp == s.timestamp
        assert loaded.raw_response == s.raw_response

    def test_multiple_scores_survive_reload(self, tmp_path: Path) -> None:
        articles = [
            _article(f"Article {i}", f"https://example.com/{i}")
            for i in range(5)
        ]
        scores = [_score(a, label="center", confidence=0.1 * (i + 1)) for i, a in enumerate(articles)]

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles(articles)
        for s in scores:
            repo1.upsert_bias_score(s)

        repo2 = _reload(tmp_path)
        for a, s in zip(articles, scores):
            loaded = repo2.get_bias_score(a.id)
            assert loaded is not None
            assert abs(loaded.confidence - s.confidence) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# 2. Latest-write-wins (BiasScore upsert)
# ─────────────────────────────────────────────────────────────────────────────

class TestLatestWriteWins:
    """The last upsert for an article_id is canonical — both in-memory and on disk."""

    def test_second_upsert_replaces_first_in_memory(self, repo: FileRepository) -> None:
        a = _article("LWW in memory", "https://example.com/lww")
        repo.add_articles([a])

        repo.upsert_bias_score(_score(a, label="left", confidence=0.2))
        repo.upsert_bias_score(_score(a, label="right", confidence=0.9))

        s = repo.get_bias_score(a.id)
        assert s is not None
        assert s.overall_bias_label == "right"
        assert abs(s.confidence - 0.9) < 1e-9

    def test_second_upsert_replaces_first_after_reload(self, tmp_path: Path) -> None:
        a = _article("LWW reload", "https://example.com/lww-reload")

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([a])
        repo1.upsert_bias_score(_score(a, label="center", confidence=0.5))
        repo1.upsert_bias_score(_score(a, label="left", confidence=0.1))

        s = _reload(tmp_path).get_bias_score(a.id)
        assert s is not None
        assert s.overall_bias_label == "left"
        assert abs(s.confidence - 0.1) < 1e-9

    def test_three_upserts_last_one_wins(self, tmp_path: Path) -> None:
        a = _article("LWW triple", "https://example.com/triple")

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([a])
        for label, conf in [("left", 0.1), ("center", 0.5), ("right", 0.9)]:
            repo1.upsert_bias_score(_score(a, label=label, confidence=conf))

        # File should have 3 lines
        lines = repo1._scores_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3

        # Fresh load uses only the last
        s = _reload(tmp_path).get_bias_score(a.id)
        assert s is not None
        assert s.overall_bias_label == "right"

    def test_upsert_timestamp_is_preserved(self, tmp_path: Path) -> None:
        a = _article("TS test", "https://example.com/ts")
        ts = datetime(2026, 3, 4, 18, 45, 59)

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([a])
        repo1.upsert_bias_score(_score(a, timestamp=ts))

        s = _reload(tmp_path).get_bias_score(a.id)
        assert s is not None
        assert s.timestamp == ts


# ─────────────────────────────────────────────────────────────────────────────
# 3. First-write-wins (Article dedup)
# ─────────────────────────────────────────────────────────────────────────────

class TestFirstWriteWins:
    """Articles are never overwritten once stored; disk stays clean."""

    def test_duplicate_not_appended_to_file(self, repo: FileRepository) -> None:
        a = _article("Dedup test", "https://example.com/dedup")
        repo.add_articles([a])
        repo.add_articles([a])  # second time — should be ignored

        lines = repo._articles_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

    def test_batch_counts_new_vs_existing(self, repo: FileRepository) -> None:
        a1 = _article("New 1", "https://example.com/n1")
        a2 = _article("New 2", "https://example.com/n2")
        repo.add_articles([a1, a2])

        # second call: a1 already exists, a3 is new
        a3 = _article("New 3", "https://example.com/n3")
        new, existing = repo.add_articles([a1, a3])
        assert new == 1
        assert existing == 1

    def test_dedup_survives_reload(self, tmp_path: Path) -> None:
        a = _article("Reload dedup", "https://example.com/rd")

        repo1 = FileRepository(base_dir=tmp_path)
        n1, _ = repo1.add_articles([a])
        n2, e2 = repo1.add_articles([a])
        assert n1 == 1
        assert n2 == 0
        assert e2 == 1

        repo2 = _reload(tmp_path)
        assert len(repo2.list_articles()) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. list_articles — ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestListArticlesOrdering:
    """Articles are returned newest-published_at first."""

    def test_newest_first_ordering(self, repo: FileRepository) -> None:
        older = _article("Older", "https://example.com/older", published_at="2026-03-01T00:00:00Z")
        newer = _article("Newer", "https://example.com/newer", published_at="2026-03-04T00:00:00Z")
        middle = _article("Middle", "https://example.com/mid", published_at="2026-03-02T00:00:00Z")

        # Insert out of chronological order
        repo.add_articles([older, newer, middle])
        articles = repo.list_articles()

        assert articles[0] == newer
        assert articles[1] == middle
        assert articles[2] == older

    def test_ordering_survives_reload(self, tmp_path: Path) -> None:
        dates = ["2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z", "2026-02-01T00:00:00Z"]
        arts = [_article(f"A{i}", f"https://example.com/ord{i}", published_at=d) for i, d in enumerate(dates)]

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles(arts)

        ordered = _reload(tmp_path).list_articles()
        timestamps = [a.published_at for a in ordered]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_articles_without_date_sort_after_dated(self, repo: FileRepository) -> None:
        dated = _article("Dated", "https://example.com/dated", published_at="2026-03-04T00:00:00Z")
        undated = _article("Undated", "https://example.com/undated", published_at=None)

        repo.add_articles([undated, dated])
        articles = repo.list_articles()

        assert articles[0] == dated
        assert articles[1] == undated


# ─────────────────────────────────────────────────────────────────────────────
# 5. list_articles — filtering
# ─────────────────────────────────────────────────────────────────────────────

class TestListArticlesFiltering:

    @pytest.fixture()
    def populated_repo(self, repo: FileRepository) -> FileRepository:
        articles = [
            _article("BBC A", "https://bbc.com/a", source="BBC", published_at="2026-03-04T10:00:00Z"),
            _article("BBC B", "https://bbc.com/b", source="BBC", published_at="2026-03-03T10:00:00Z"),
            _article("AJ  A", "https://aj.com/a",  source="AlJazeera", published_at="2026-03-02T10:00:00Z"),
            _article("AJ  B", "https://aj.com/b",  source="AlJazeera", published_at="2026-03-01T10:00:00Z"),
        ]
        repo.add_articles(articles)
        return repo

    def test_filter_by_source(self, populated_repo: FileRepository) -> None:
        bbc = populated_repo.list_articles(source="BBC")
        assert len(bbc) == 2
        assert all(a.source == "BBC" for a in bbc)

    def test_filter_by_source_no_match(self, populated_repo: FileRepository) -> None:
        assert populated_repo.list_articles(source="Reuters") == []

    def test_filter_by_since(self, populated_repo: FileRepository) -> None:
        since = datetime(2026, 3, 3, 0, 0, 0)
        recent = populated_repo.list_articles(since=since)
        assert len(recent) == 2
        for a in recent:
            dt = datetime.fromisoformat(a.published_at.rstrip("Z"))
            assert dt >= since

    def test_limit(self, populated_repo: FileRepository) -> None:
        assert len(populated_repo.list_articles(limit=2)) == 2

    def test_limit_larger_than_total(self, populated_repo: FileRepository) -> None:
        assert len(populated_repo.list_articles(limit=100)) == 4

    def test_limit_combined_with_source(self, populated_repo: FileRepository) -> None:
        result = populated_repo.list_articles(source="BBC", limit=1)
        assert len(result) == 1
        assert result[0].source == "BBC"
        # Should be the newer BBC article
        assert result[0].published_at == "2026-03-04T10:00:00Z"

    def test_empty_repo_returns_empty_list(self, repo: FileRepository) -> None:
        assert repo.list_articles() == []
        assert repo.list_articles(source="BBC") == []
        assert repo.list_articles(limit=10) == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. Graceful None returns for unknown ids
# ─────────────────────────────────────────────────────────────────────────────

class TestNoneForUnknownIds:

    def test_get_article_unknown_returns_none(self, repo: FileRepository) -> None:
        assert repo.get_article("does-not-exist") is None

    def test_get_bias_score_unknown_returns_none(self, repo: FileRepository) -> None:
        assert repo.get_bias_score("does-not-exist") is None

    def test_get_article_after_write_unknown_still_none(self, repo: FileRepository) -> None:
        a = _article("Known", "https://example.com/known")
        repo.add_articles([a])
        assert repo.get_article("completely-different-id") is None

    def test_get_score_article_exists_no_score_returns_none(self, repo: FileRepository) -> None:
        a = _article("No score", "https://example.com/noscore")
        repo.add_articles([a])
        assert repo.get_bias_score(a.id) is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Auto-create data directory
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoCreateDirectory:

    def test_repo_creates_nonexistent_base_dir_on_first_write(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()

        repo = FileRepository(base_dir=nested)
        a = _article("Dir test", "https://example.com/dir")
        repo.add_articles([a])

        assert nested.exists()
        assert (nested / "articles.jsonl").exists()

    def test_repo_on_missing_dir_returns_empty_lists_before_write(self, tmp_path: Path) -> None:
        nested = tmp_path / "empty_dir"
        repo = FileRepository(base_dir=nested)

        assert repo.list_articles() == []
        assert repo.get_article("x") is None
        assert repo.get_bias_score("x") is None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Batch add_articles return value
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchReturnValue:

    def test_all_new_returns_correct_counts(self, repo: FileRepository) -> None:
        arts = [_article(f"B{i}", f"https://example.com/b{i}") for i in range(4)]
        new, existing = repo.add_articles(arts)
        assert new == 4
        assert existing == 0

    def test_all_existing_returns_correct_counts(self, repo: FileRepository) -> None:
        arts = [_article(f"C{i}", f"https://example.com/c{i}") for i in range(3)]
        repo.add_articles(arts)
        new, existing = repo.add_articles(arts)
        assert new == 0
        assert existing == 3

    def test_mixed_batch_returns_correct_counts(self, repo: FileRepository) -> None:
        old = _article("Old", "https://example.com/old")
        repo.add_articles([old])

        fresh = [_article(f"F{i}", f"https://example.com/f{i}") for i in range(2)]
        new, existing = repo.add_articles([old] + fresh)
        assert new == 2
        assert existing == 1

    def test_empty_batch_returns_zero_zero(self, repo: FileRepository) -> None:
        new, existing = repo.add_articles([])
        assert new == 0
        assert existing == 0


# ─────────────────────────────────────────────────────────────────────────────
# 9. Score slot semantics (one slot per article_id)
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreSlotSemantics:
    """
    The score slot is keyed by article_id alone.
    Writing a score with a different provider name still occupies the same
    slot — latest write wins regardless of provider.
    """

    def test_independent_articles_have_independent_slots(self, repo: FileRepository) -> None:
        a1 = _article("Slot A1", "https://example.com/s1")
        a2 = _article("Slot A2", "https://example.com/s2")
        repo.add_articles([a1, a2])
        repo.upsert_bias_score(_score(a1, label="left",   confidence=0.1))
        repo.upsert_bias_score(_score(a2, label="right",  confidence=0.9))

        s1 = repo.get_bias_score(a1.id)
        s2 = repo.get_bias_score(a2.id)
        assert s1 is not None and s1.overall_bias_label == "left"
        assert s2 is not None and s2.overall_bias_label == "right"

    def test_later_provider_replaces_earlier_provider_for_same_article(
        self, tmp_path: Path
    ) -> None:
        a = _article("Provider swap", "https://example.com/ps")

        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([a])
        repo1.upsert_bias_score(_score(a, label="center",  provider="mock",   confidence=0.5))
        repo1.upsert_bias_score(_score(a, label="left",    provider="gemini", confidence=0.2))

        # Latest write (gemini) wins
        s = _reload(tmp_path).get_bias_score(a.id)
        assert s is not None
        assert s.provider == "gemini"
        assert s.overall_bias_label == "left"

    def test_score_for_one_article_does_not_affect_another(
        self, repo: FileRepository
    ) -> None:
        a1 = _article("No cross 1", "https://example.com/nc1")
        a2 = _article("No cross 2", "https://example.com/nc2")
        repo.add_articles([a1, a2])
        repo.upsert_bias_score(_score(a1, label="right"))

        # Updating a1's score must not touch a2's slot
        assert repo.get_bias_score(a2.id) is None
        repo.upsert_bias_score(_score(a1, label="left"))
        assert repo.get_bias_score(a2.id) is None
