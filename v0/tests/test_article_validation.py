import pytest
from istina.model.entities.article import Article

@pytest.mark.parametrize("missing", ["title", "url", "source"])
def test_article_from_dict_missing_required(missing):
    data = {
        "title": "Test Article",
        "url": "https://example.com/article",
        "source": "Example Source",
        "published_at": "2026-02-17T12:30:00Z",
        "summary": "A summary of the article."
    }
    data.pop(missing)

    with pytest.raises(ValueError) as exc:
        Article.from_dict(data)


def test_url_must_be_string():
    with pytest.raises(ValueError):
        Article.create(title="T", url=123, source="S")


def test_empty_url_rejected():
    with pytest.raises(ValueError):
        Article.create(title="T", url="   ", source="S")


def test_empty_required_fields_rejected():
    with pytest.raises(ValueError):
        Article.create(title="   ", url="http://x", source="S")

    with pytest.raises(ValueError):
        Article.create(title="T", url="http://x", source="   ")


def test_optional_fields_can_be_none_or_empty():
    article = Article.create(title="T", url="http://x", source="S", published_at=None, summary="")
    assert article.published_at is None
    assert article.summary == ""


