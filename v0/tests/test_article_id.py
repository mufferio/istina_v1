from istina.model.entities.article import Article

def test_article_id_exists_and_is_string():
    article = Article.create(
        title="Test Title",
        url="https://example.com/news/1",
        source="ExampleSource",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    assert article.id is not None
    assert isinstance(article.id, str)


def test_article_id_is_stable():
    article1 = Article.create(
        title="Test Title",
        url="https://example.com/news/1",
        source="ExampleSource",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    article2 = Article.create(
        title="Test Title",
        url="https://example.com/news/1",
        source="ExampleSource",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    assert article1.id == article2.id


def test_article_id_unique_for_different_articles():
    article1 = Article.create(
        title="Test Title 1",
        url="https://example.com/news/1",
        source="ExampleSource",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    article2 = Article.create(
        title="Test Title 2",
        url="https://example.com/news/2",
        source="ExampleSource",
        published_at="2026-02-17T12:30:00Z",
        summary="A summary of the article."
    )
    assert article1.id != article2.id