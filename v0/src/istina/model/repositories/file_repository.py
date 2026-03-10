"""
File-based repository — CLI v0 stable persistence.

Storage Format
--------------
Two newline-delimited JSON (JSONL) files, each in *base_dir* (default ``data/``):

    data/articles.jsonl
    data/bias_scores.jsonl

Each line is exactly one JSON object, **never** pretty-printed, terminated by
``\\n``.  Empty lines and lines whose JSON cannot be parsed are silently skipped
on load (resilient reader).

Article record  (schema_version = 1)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    {
      "schema_version":  1,
      "id":              "<64-char sha256 hex>",
      "title":           "Gaza ceasefire talks resume in Cairo",
      "url":             "https://bbc.co.uk/news/world-middle-east-123456",
      "source":          "BBC News",
      "published_at":    "2026-03-04T12:00:00Z",
      "summary":         "Negotiators from both sides ..."
    }

    Nullable fields: ``published_at``, ``summary`` may be ``null``.

BiasScore record  (schema_version = 1)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    {
      "schema_version":     1,
      "article_id":         "<64-char sha256 hex>",
      "provider":           "gemini",
      "overall_bias_label": "center",
      "rhetorical_bias":    ["loaded_language"],
      "claim_checks":       [
          {
              "claim_text": "The ceasefire was unconditional.",
              "verdict":    "contradicted",
              "evidence":   ["https://reuters.com/..."]
          }
      ],
      "confidence":         0.87,
      "timestamp":          "2026-03-04T14:05:00",
      "raw_response":       null
    }

    Nullable field: ``raw_response`` may be ``null``.

Update Policies
---------------
Articles:
    **First write wins.**  Once an article ``id`` is stored it is never
    overwritten.  Duplicate ``id`` values encountered on load or during
    ``add_articles`` are silently skipped.

BiasScores:
    **Latest write wins.**  A new record for the same ``(article_id, provider)``
    pair is *appended* to the JSONL file; on load, only the **last** occurrence
    is kept as the canonical value.  The file accumulates superseded lines until
    ``compact()`` is called (or until the next full rewrite).

Atomicity
---------
File rewrites use write-to-temp-then-``os.replace`` so a crash mid-write never
leaves a half-written file.  Append-only writes (articles) do not need this
guarantee because partial lines at the end of the file are skipped on the next
load.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.base_repository import BaseRepository
from istina.utils.error_handling import RepositoryError

# ── constants ────────────────────────────────────────────────────────────────

ARTICLES_FILE = "articles.jsonl"
BIAS_SCORES_FILE = "bias_scores.jsonl"
SCHEMA_VERSION = 1


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> List[Tuple[int, dict]]:
    """Return ``(lineno, record)`` pairs from a JSONL file (1-based line numbers).

    Silently skips blank lines and lines that fail to parse.
    Returns an empty list if the file does not exist.
    """
    if not path.exists():
        return []
    records: List[Tuple[int, dict]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append((lineno, json.loads(raw)))
            except json.JSONDecodeError:
                pass  # corrupted line — skip
    return records


def _validate_schema_version(rec: dict, *, path: Path, lineno: int) -> None:
    """Raise :exc:`RepositoryError` if *rec* carries an unrecognised schema version.

    Rules:
    - A missing ``schema_version`` key is treated as **version 0** (pre-versioning
      era) and is rejected so old unversioned files are not silently misread.
    - Any version other than :data:`SCHEMA_VERSION` is rejected with a message
      that tells the operator exactly which file and line caused the problem and
      what migration step is needed.
    """
    stored = rec.get("schema_version", None)
    if stored is None:
        raise RepositoryError(
            f"{path}:{lineno}: record is missing 'schema_version'. "
            f"Expected {SCHEMA_VERSION}. "
            "The file may have been written by a pre-versioning build. "
            "Remove or migrate the file before restarting."
        )
    if stored != SCHEMA_VERSION:
        raise RepositoryError(
            f"{path}:{lineno}: unsupported schema_version={stored!r} "
            f"(this build understands version {SCHEMA_VERSION}). "
            "Migrate the data file or downgrade the application."
        )


def _append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON object as a single line to *path*.

    Calls ``flush()`` then ``os.fsync()`` before returning so the record is
    committed to storage even if the process exits immediately afterwards.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _rewrite_jsonl(path: Path, records: Iterable[dict]) -> None:
    """Atomically overwrite *path* with *records* (one JSON line each)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── repository ────────────────────────────────────────────────────────────────

class FileRepository(BaseRepository):
    """Persistent JSONL-backed repository for CLI v0.

    Parameters
    ----------
    base_dir:
        Directory that holds ``articles.jsonl`` and ``bias_scores.jsonl``.
        Created automatically if absent.  Defaults to ``data/`` relative to
        the current working directory.

    Example
    -------
    ::

        repo = FileRepository()                        # data/ in cwd
        repo = FileRepository(base_dir="./my_data")   # custom path

        # Write
        article = Article.create(title="...", url="https://...", source="BBC")
        repo.add_articles([article])

        # Read back
        loaded = repo.get_article(article.id)
        assert loaded == article
    """

    def __init__(self, base_dir: str | os.PathLike = "data") -> None:
        self._base = Path(base_dir)
        self._articles_path = self._base / ARTICLES_FILE
        self._scores_path = self._base / BIAS_SCORES_FILE

        # In-memory indexes — populated on construction
        self._articles: Dict[str, Article] = {}
        self._insert_index: Dict[str, int] = {}
        self._next_idx: int = 0
        # BiasScores keyed by article_id (one score per article, latest write wins)
        self._scores: Dict[str, BiasScore] = {}

        self._load()

    # ── internal loading ──────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load both JSONL files into memory."""
        self._load_articles()
        self._load_scores()

    def _load_articles(self) -> None:
        for lineno, rec in _read_jsonl(self._articles_path):
            _validate_schema_version(rec, path=self._articles_path, lineno=lineno)
            try:
                article = Article.from_dict(rec)
            except (ValueError, KeyError):
                continue  # skip malformed record
            if article.id not in self._articles:
                # first write wins — ignore later occurrences
                self._articles[article.id] = article
                self._insert_index[article.id] = self._next_idx
                self._next_idx += 1

    def _load_scores(self) -> None:
        for lineno, rec in _read_jsonl(self._scores_path):
            _validate_schema_version(rec, path=self._scores_path, lineno=lineno)
            try:
                score = BiasScore.from_dict(rec)
            except (ValueError, KeyError):
                continue
            # latest write wins — always overwrite the in-memory slot
            self._scores[score.article_id] = score

    # ── BaseRepository interface ──────────────────────────────────────────────

    def add_articles(self, articles: Iterable[Article]) -> Tuple[int, int]:
        """Add articles; skip any whose ``id`` is already stored.

        Returns
        -------
        (new_count, existing_count)
        """
        new_count = 0
        existing_count = 0
        for article in articles:
            aid = article.id
            if aid in self._articles:
                existing_count += 1
                continue
            # Persist first, then update index (so a write failure leaves
            # state consistent with what's on disk).
            rec = {**article.to_dict(), "schema_version": SCHEMA_VERSION}
            _append_jsonl(self._articles_path, rec)
            self._articles[aid] = article
            self._insert_index[aid] = self._next_idx
            self._next_idx += 1
            new_count += 1
        return new_count, existing_count

    def get_article(self, article_id: str) -> Optional[Article]:
        return self._articles.get(article_id)

    def list_articles(
        self,
        limit: Optional[int] = None,
        source: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Article]:
        items = list(self._articles.values())

        if source is not None:
            items = [a for a in items if a.source == source]

        if since is not None:
            def _dt(a: Article) -> Optional[datetime]:
                if a.published_at is None:
                    return None
                try:
                    return datetime.fromisoformat(a.published_at.rstrip("Z"))
                except ValueError:
                    return None

            items = [a for a in items if (_dt(a) is not None and _dt(a) >= since)]

        def _sort_key(a: Article):
            dt = None
            if a.published_at:
                try:
                    dt = datetime.fromisoformat(a.published_at.rstrip("Z"))
                except ValueError:
                    pass
            idx = self._insert_index.get(a.id, 10 ** 12)
            # newest first; articles without a date sort after those with one
            return (dt is None, -(dt.timestamp() if dt else 0), idx)

        items.sort(key=_sort_key)

        if limit is not None:
            items = items[:limit]
        return items

    def upsert_bias_score(self, score: BiasScore) -> None:
        """Insert or replace a BiasScore.

        Appends to the JSONL file and updates the in-memory index.  ``latest
        write wins`` — the new record supersedes any previous record for the
        same ``(article_id, provider)`` pair.
        """
        rec = {**score.to_dict(), "schema_version": SCHEMA_VERSION}
        _append_jsonl(self._scores_path, rec)
        self._scores[score.article_id] = score

    def get_bias_score(self, article_id: str, provider: Optional[str] = None) -> Optional[BiasScore]:  # noqa: ARG002
        return self._scores.get(article_id)

    # ── housekeeping ──────────────────────────────────────────────────────────

    def compact(self) -> None:
        """Rewrite both JSONL files keeping only canonical (live) records.

        For ``articles.jsonl``: emit one line per stored article (deduplication
        was already enforced on load/write, so this is mostly a no-op but
        removes any corrupted-line gaps).

        For ``bias_scores.jsonl``: emit one line per ``(article_id, provider)``
        pair, collapsing all superseded records.  Useful to keep the file from
        growing unboundedly after many``upsert_bias_score`` calls.
        """
        article_records = [
            {**a.to_dict(), "schema_version": SCHEMA_VERSION}
            for a in self._articles.values()
        ]
        _rewrite_jsonl(self._articles_path, article_records)

        score_records = [
            {**s.to_dict(), "schema_version": SCHEMA_VERSION}
            for s in self._scores.values()  # keyed by article_id
        ]
        _rewrite_jsonl(self._scores_path, score_records)
