import pytest

from istina.model.repositories.memory_repository import MemoryRepository
from istina.model.entities.article import Article


def _make_article(title: str, url: str, source: str, published_at: str):
    """
    Helper to create an Article with the fields your project has been using.
    Adjust ONLY if your Article constructor differs.
    """
    return Article.create(
        title=title,
        url=url,
        source=source,
        published_at=published_at,
        summary="test summary",
    )


def test_add_same_article_twice_counts_and_storage_size():
    repo = MemoryRepository()

    a = _make_article(
        title="Same",
        url="https://example.com/1",
        source="ExampleSource",
        published_at="2026-02-01T10:00:00Z",
    )

    # First insert: 1 new, 0 existing
    new1, existing1 = repo.add_articles([a])
    assert (new1, existing1) == (1, 0)

    # Second insert with the exact same object: 0 new, 1 existing
    new2, existing2 = repo.add_articles([a])
    assert (new2, existing2) == (0, 1)

    # Storage count remains 1
    assert len(repo.articles) == 1  # okay for unit tests; alternatively expose a count method

    # The stored article is still retrievable and unchanged
    article_id = getattr(a, "article_id", None) or getattr(a, "id", None)
    assert article_id is not None

    stored = repo.get_article(article_id)
    assert stored is not None
    assert stored.title == "Same"
    assert stored.url == "https://example.com/1"


def test_add_two_articles_then_add_duplicate_one():
    repo = MemoryRepository()

    a1 = _make_article("A1", "https://example.com/a1", "S", "2026-02-01T10:00:00Z")
    a2 = _make_article("A2", "https://example.com/a2", "S", "2026-02-02T10:00:00Z")

    new, existing = repo.add_articles([a1, a2])
    assert (new, existing) == (2, 0)
    assert len(repo.articles) == 2

    # Add duplicate of a1 again
    new2, existing2 = repo.add_articles([a1])
    assert (new2, existing2) == (0, 1)
    assert len(repo.articles) == 2  # still 2


def test_dedupe_policy_does_not_overwrite_existing_article():
    repo = MemoryRepository()

    a_original = _make_article("Original", "https://example.com/x", "S", "2026-02-01T10:00:00Z")

    # Insert original
    new1, existing1 = repo.add_articles([a_original])
    print(f"a_original.id: {a_original.id}")
    assert (new1, existing1) == (1, 0)

    # Create another Article object with SAME id.
    a_dupe = _make_article("DupeTitle", "https://example.com/x", "S", "2026-02-01T10:00:00Z")
    print(f"a_dupe.id: {a_dupe.id}")

    # Insert dupe -> should count as existing and NOT overwrite
    new2, existing2 = repo.add_articles([a_dupe])
    print(f"new2, existing2: {new2}, {existing2}")

    assert (new2, existing2) == (0, 1)

    article_id = getattr(a_original, "article_id", None) or getattr(a_original, "id", None)
    stored = repo.get_article(article_id)
    print(f"stored.title: {stored.title}, stored.published_at: {stored.published_at}")

    # Confirm overwrite did NOT happen
    assert stored.title == "Original"
    assert stored.published_at == "2026-02-01T10:00:00Z"
