import json
import pytest
from istina.model.entities.article import Article


def test_article_roundtrip_to_dict_from_dict():
    article = Article.create(
        title="Test Title",
        url="https://example.com/news/1",
        source="ExampleSource",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )

    d = article.to_dict()
    article2 = Article.from_dict(d)
    assert article == article2

    # JSON serialization
    j = json.dumps(d)
    d2 = json.loads(j)
    article3 = Article.from_dict(d2)
    assert article == article3


@pytest.mark.parametrize("missing_field", ["title", "url", "source"])
def test_article_roundtrip_missing_required(missing_field):
    base = {
        "title": "Test Title",
        "url": "https://example.com/news/1",
        "source": "ExampleSource",
        "published_at": "2026-02-17T12:30:00Z",
        "summary": "A summary of the article."
    }

    base.pop(missing_field)

    with pytest.raises(ValueError):
        Article.from_dict(base)


def test_article_from_dict_rejects_id_mismatch():
    article = Article.create(
        title="Test Title",
        url="https://example.com/news/1",
        source="ExampleSource"
    )

    d = article.to_dict()
    d["id"] = "WRONG"

    with pytest.raises(ValueError):
        Article.from_dict(d)
