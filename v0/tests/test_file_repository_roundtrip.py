"""
Round-trip smoke test for FileRepository.

Verifies:
- An Article can be written to data/articles.jsonl and read back intact.
- A BiasScore can be written to data/bias_scores.jsonl and read back intact.
- "Latest write wins" policy for BiasScores (upsert replaces previous record).
- "First write wins" policy for Articles (duplicate id is ignored).
- A second FileRepository instance pointing at the same directory loads the
  persisted data correctly (persistence round-trip).
- compact() rewrites both files to a single canonical line per record.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.file_repository import (
    ARTICLES_FILE,
    BIAS_SCORES_FILE,
    SCHEMA_VERSION,
    FileRepository,
)
from istina.utils.error_handling import RepositoryError


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_repo(tmp_path: Path) -> FileRepository:
    """Fresh FileRepository backed by a temporary directory."""
    return FileRepository(base_dir=tmp_path)


@pytest.fixture()
def sample_article() -> Article:
    return Article.create(
        title="Gaza ceasefire talks resume in Cairo",
        url="https://bbc.co.uk/news/world-middle-east-123456",
        source="BBC News",
        published_at="2026-03-04T12:00:00Z",
        summary="Negotiators from both sides met on Tuesday.",
    )


@pytest.fixture()
def sample_score(sample_article: Article) -> BiasScore:
    return BiasScore(
        article_id=sample_article.id,
        provider="mock",
        overall_bias_label="center",
        rhetorical_bias=["loaded_language"],
        claim_checks=[
            {
                "claim_text": "The ceasefire was unconditional.",
                "verdict": "contradicted",
                "evidence": ["https://reuters.com/example"],
            }
        ],
        confidence=0.87,
        timestamp=datetime(2026, 3, 4, 14, 5, 0),
        raw_response=None,
    )


# ── article tests ─────────────────────────────────────────────────────────────

class TestArticleRoundtrip:
    def test_write_then_read_in_memory(self, tmp_repo: FileRepository, sample_article: Article) -> None:
        new, existing = tmp_repo.add_articles([sample_article])
        assert new == 1
        assert existing == 0

        loaded = tmp_repo.get_article(sample_article.id)
        assert loaded == sample_article

    def test_file_contains_schema_version(self, tmp_repo: FileRepository, sample_article: Article) -> None:
        tmp_repo.add_articles([sample_article])
        lines = (tmp_repo._articles_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["schema_version"] == SCHEMA_VERSION
        assert rec["id"] == sample_article.id

    def test_persistence_across_instances(
        self, tmp_path: Path, sample_article: Article
    ) -> None:
        """Data written by one FileRepository survives a fresh load."""
        repo1 = FileRepository(base_dir=tmp_path)
        repo1.add_articles([sample_article])

        repo2 = FileRepository(base_dir=tmp_path)
        loaded = repo2.get_article(sample_article.id)
        assert loaded == sample_article

    def test_first_write_wins(self, tmp_repo: FileRepository, sample_article: Article) -> None:
        """Adding the same article twice keeps the first copy."""
        new1, _ = tmp_repo.add_articles([sample_article])
        new2, existing2 = tmp_repo.add_articles([sample_article])
        assert new1 == 1
        assert new2 == 0
        assert existing2 == 1
        # Only one line in the file
        lines = tmp_repo._articles_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

    def test_list_articles_returns_written_article(
        self, tmp_repo: FileRepository, sample_article: Article
    ) -> None:
        tmp_repo.add_articles([sample_article])
        articles = tmp_repo.list_articles()
        assert len(articles) == 1
        assert articles[0] == sample_article


# ── bias score tests ──────────────────────────────────────────────────────────

class TestBiasScoreRoundtrip:
    def test_write_then_read_in_memory(
        self, tmp_repo: FileRepository, sample_article: Article, sample_score: BiasScore
    ) -> None:
        tmp_repo.add_articles([sample_article])
        tmp_repo.upsert_bias_score(sample_score)

        loaded = tmp_repo.get_bias_score(sample_score.article_id)
        assert loaded is not None
        assert loaded.article_id == sample_score.article_id
        assert loaded.provider == sample_score.provider
        assert loaded.overall_bias_label == sample_score.overall_bias_label
        assert abs(loaded.confidence - sample_score.confidence) < 1e-9
        assert loaded.rhetorical_bias == sample_score.rhetorical_bias
        assert loaded.claim_checks == sample_score.claim_checks
        assert loaded.timestamp == sample_score.timestamp

    def test_file_contains_schema_version(
        self, tmp_repo: FileRepository, sample_score: BiasScore
    ) -> None:
        tmp_repo.upsert_bias_score(sample_score)
        lines = tmp_repo._scores_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["schema_version"] == SCHEMA_VERSION
        assert rec["article_id"] == sample_score.article_id

    def test_persistence_across_instances(
        self, tmp_path: Path, sample_score: BiasScore
    ) -> None:
        """BiasScore written by one instance is loaded by the next."""
        repo1 = FileRepository(base_dir=tmp_path)
        repo1.upsert_bias_score(sample_score)

        repo2 = FileRepository(base_dir=tmp_path)
        loaded = repo2.get_bias_score(sample_score.article_id)
        assert loaded is not None
        assert loaded.article_id == sample_score.article_id

    def test_latest_write_wins(
        self, tmp_repo: FileRepository, sample_score: BiasScore
    ) -> None:
        """Second upsert for same (article_id, provider) replaces the first."""
        tmp_repo.upsert_bias_score(sample_score)

        updated = BiasScore(
            article_id=sample_score.article_id,
            provider=sample_score.provider,
            overall_bias_label="left",
            rhetorical_bias=[],
            claim_checks=[],
            confidence=0.55,
            timestamp=datetime(2026, 3, 4, 15, 0, 0),
            raw_response=None,
        )
        tmp_repo.upsert_bias_score(updated)

        # Two lines in file (append-only) ...
        lines = tmp_repo._scores_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

        # ... but in-memory index holds only the latest
        loaded = tmp_repo.get_bias_score(sample_score.article_id)
        assert loaded is not None
        assert loaded.overall_bias_label == "left"
        assert abs(loaded.confidence - 0.55) < 1e-9

    def test_latest_write_wins_after_reload(
        self, tmp_path: Path, sample_score: BiasScore
    ) -> None:
        """After a reload, latest-write-wins is honoured by the new instance."""
        repo1 = FileRepository(base_dir=tmp_path)
        repo1.upsert_bias_score(sample_score)
        updated = BiasScore(
            article_id=sample_score.article_id,
            provider=sample_score.provider,
            overall_bias_label="right",
            rhetorical_bias=[],
            claim_checks=[],
            confidence=0.3,
            timestamp=datetime(2026, 3, 4, 16, 0, 0),
            raw_response=None,
        )
        repo1.upsert_bias_score(updated)

        repo2 = FileRepository(base_dir=tmp_path)
        loaded = repo2.get_bias_score(sample_score.article_id)
        assert loaded is not None
        assert loaded.overall_bias_label == "right"


# ── compact() tests ───────────────────────────────────────────────────────────

class TestCompact:
    def test_compact_collapses_duplicate_scores(
        self, tmp_repo: FileRepository, sample_score: BiasScore
    ) -> None:
        tmp_repo.upsert_bias_score(sample_score)
        updated = BiasScore(
            article_id=sample_score.article_id,
            provider=sample_score.provider,
            overall_bias_label="left",
            rhetorical_bias=[],
            claim_checks=[],
            confidence=0.4,
            timestamp=datetime(2026, 3, 4, 17, 0, 0),
        )
        tmp_repo.upsert_bias_score(updated)

        assert (
            len(tmp_repo._scores_path.read_text(encoding="utf-8").splitlines()) == 2
        ), "Pre-compact: two lines expected"

        tmp_repo.compact()

        lines = tmp_repo._scores_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, "Post-compact: only latest record should remain"
        rec = json.loads(lines[0])
        assert rec["overall_bias_label"] == "left"

    def test_compact_articles_is_idempotent(
        self, tmp_repo: FileRepository, sample_article: Article
    ) -> None:
        tmp_repo.add_articles([sample_article])
        tmp_repo.compact()
        lines = tmp_repo._articles_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1


# ── schema version validation tests ─────────────────────────────────────────────────────

class TestSchemaVersionValidation:
    """Loading a file whose schema_version != SCHEMA_VERSION must raise RepositoryError."""

    def _write_raw(self, path: Path, record: dict) -> None:
        """Write *record* as a single JSONL line, bypassing FileRepository."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    # —— articles.jsonl ——

    def test_articles_wrong_version_raises(self, tmp_path: Path, sample_article: Article) -> None:
        """A record with schema_version=99 must raise RepositoryError on load."""
        bad_rec = {**sample_article.to_dict(), "schema_version": 99}
        self._write_raw(tmp_path / ARTICLES_FILE, bad_rec)

        with pytest.raises(RepositoryError, match="schema_version=99"):
            FileRepository(base_dir=tmp_path)

    def test_articles_missing_version_raises(self, tmp_path: Path, sample_article: Article) -> None:
        """A record without schema_version must raise RepositoryError on load."""
        bad_rec = sample_article.to_dict()  # no schema_version key
        self._write_raw(tmp_path / ARTICLES_FILE, bad_rec)

        with pytest.raises(RepositoryError, match="missing 'schema_version'"):
            FileRepository(base_dir=tmp_path)

    def test_articles_error_names_file_and_line(self, tmp_path: Path, sample_article: Article) -> None:
        """The error message must include the file path and line number."""
        bad_rec = {**sample_article.to_dict(), "schema_version": 2}
        self._write_raw(tmp_path / ARTICLES_FILE, bad_rec)

        with pytest.raises(RepositoryError) as exc_info:
            FileRepository(base_dir=tmp_path)
        msg = str(exc_info.value)
        assert ARTICLES_FILE in msg
        assert ":1" in msg  # line 1

    # —— bias_scores.jsonl ——

    def test_scores_wrong_version_raises(
        self, tmp_path: Path, sample_score: BiasScore
    ) -> None:
        """A bias_score record with schema_version=99 must raise RepositoryError."""
        bad_rec = {**sample_score.to_dict(), "schema_version": 99}
        self._write_raw(tmp_path / BIAS_SCORES_FILE, bad_rec)

        with pytest.raises(RepositoryError, match="schema_version=99"):
            FileRepository(base_dir=tmp_path)

    def test_scores_missing_version_raises(
        self, tmp_path: Path, sample_score: BiasScore
    ) -> None:
        bad_rec = sample_score.to_dict()  # no schema_version key
        self._write_raw(tmp_path / BIAS_SCORES_FILE, bad_rec)

        with pytest.raises(RepositoryError, match="missing 'schema_version'"):
            FileRepository(base_dir=tmp_path)

    # —— valid version still loads cleanly ——

    def test_correct_version_loads_cleanly(
        self, tmp_path: Path, sample_article: Article
    ) -> None:
        """A record with the current SCHEMA_VERSION must load without error."""
        good_rec = {**sample_article.to_dict(), "schema_version": SCHEMA_VERSION}
        self._write_raw(tmp_path / ARTICLES_FILE, good_rec)

        repo = FileRepository(base_dir=tmp_path)  # must not raise
        assert repo.get_article(sample_article.id) == sample_article

    # —— second-line error names the correct line number ——

    def test_error_reports_correct_line_number(
        self, tmp_path: Path, sample_article: Article
    ) -> None:
        """If the bad record is on line 2, the error message must say :2."""
        good_rec = {**sample_article.to_dict(), "schema_version": SCHEMA_VERSION}
        a2 = Article.create(
            title="Second article",
            url="https://example.com/2",
            source="Example",
        )
        bad_rec = {**a2.to_dict(), "schema_version": 0}
        path = tmp_path / ARTICLES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(good_rec) + "\n")
            fh.write(json.dumps(bad_rec) + "\n")

        with pytest.raises(RepositoryError) as exc_info:
            FileRepository(base_dir=tmp_path)
        assert ":2" in str(exc_info.value)
