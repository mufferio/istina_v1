import pytest
from istina.model.repositories.memory_repository import MemoryRepository
from istina.model.entities.article import Article

@pytest.fixture
def repo():
    return MemoryRepository()

def test_add_and_get_articles(repo):
    a1 = Article.create(
        title="Older",
        url="https://ex.com/1",
        source="BBC",
        published_at="2026-02-01T10:00:00Z",
        summary="An article about something."
    )
    a2 = Article.create(
        title="Newer",
        url="https://ex.com/2",
        source="BBC",
        published_at="2026-02-02T10:00:00Z",
        summary="Another article about something."
    )
    repo.add_articles([a1, a2])
    print("Added articles: 2 0")  # Manual print for debugging
    assert repo.get_article(a1.id).title == "Older"
    print(repo.get_article(a1.id).title)  # Should print: Older
    assert repo.get_article(a1.id).title == "Older"

def test_list_articles_order(repo):
    a1 = Article.create(
        title="Older",
        url="https://ex.com/1",
        source="BBC",
        published_at="2026-02-01T10:00:00Z",
        summary="An article about something."
    )
    a2 = Article.create(
        title="Newer",
        url="https://ex.com/2",
        source="BBC",
        published_at="2026-02-02T10:00:00Z",
        summary="Another article about something."
    )
    repo.add_articles([a1, a2])
    listed = repo.list_articles()
    print([a.title for a in listed])  # Should print: ['Newer', 'Older'] (newer first)
    titles = [a.title for a in listed]
    assert titles == ["Newer", "Older"]