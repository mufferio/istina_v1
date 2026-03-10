import pytest
from istina.model.entities.article import Article


def test_id_stable_across_title_changes():
    a1 = Article.create(
        title="Hello",
        url="https://example.com/post/",
        source="Example News",
        published_at="2026-02-17T12:00:00Z",
    )
    a2 = Article.create(
        title="Different title",
        url="https://example.com/post",
        source="Example News",
        published_at="2026-02-17T12:00:00Z",
    )
    assert a1.id == a2.id


def test_id_changes_when_url_changes():
    a1 = Article.create(title="A", url="https://a.com/x", source="S")
    a2 = Article.create(title="A", url="https://a.com/y", source="S")
    assert a1.id != a2.id


def test_create_requires_fields():
    with pytest.raises(ValueError):
        Article.create(title="x", url="", source="S")
    with pytest.raises(ValueError):
        Article.create(title="x", url="https://x.com", source="")
    with pytest.raises(ValueError):
        Article.create(title="", url="https://x.com", source="S")


def test_roundtrip_dict():
    a1 = Article.create(
        title="T",
        url="https://example.com/post",
        source="Example",
        published_at="2026-02-17T12:00:00Z",
        summary="Sum",
    )
    a2 = Article.from_dict(a1.to_dict())
    assert a1 == a2


# Only include this test if you add the strict mismatch check in from_dict()
def test_from_dict_rejects_id_mismatch():
    a = Article.create(title="T", url="https://x.com", source="S")
    d = a.to_dict()
    d["id"] = "wrong"
    with pytest.raises(ValueError):
        Article.from_dict(d)
