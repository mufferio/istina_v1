from istina.model.entities.article import Article



def test_round_trip_serialization():
    original_article = Article.create(
        title="Test Article",
        url="https://example.com/article",
        source="Example Source",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )

    # Serialize to dict
    article_dict = original_article.to_dict()

    # Deserialize back to Article
    reconstructed_article = Article.from_dict(article_dict)

    assert original_article == reconstructed_article


def test_to_dict_keys():
    article = Article.create(
        title="Test Article",
        url="https://example.com/article",
        source="Example Source",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    d = article.to_dict()
    expected_keys = {"id", "title", "url", "source", "published_at", "summary"}
    assert set(d.keys()) == expected_keys



def test_to_dict_keys():
    article = Article.create(
        title="Test Article",
        url="https://example.com/article",
        source="Example Source",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    d = article.to_dict()
    expected_keys = {"id", "title", "url", "source", "published_at", "summary"}
    assert set(d.keys()) == expected_keys

def test_to_dict_values():
    article = Article.create(
        title="Test Article",
        url="https://example.com/article",
        source="Example Source",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    d = article.to_dict()
    assert d["id"] == article.id
    assert d["title"] == article.title
    assert d["url"] == article.url
    assert d["source"] == article.source
    assert d["published_at"] == article.published_at
    assert d["summary"] == article.summary

