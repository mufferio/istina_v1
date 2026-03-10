"""
ScoringVisitor tests.

Covers:
- visit() delegates to provider.analyze_article() and returns BiasScore
- ScoringVisitor is a subclass of ArticleVisitor
- __init__ guard: None provider raises ValueError
- __init__ guard: provider missing analyze_article raises TypeError
- __init__ guard: provider with non-callable analyze_article raises TypeError
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider
from istina.model.visitors.article_visitor import ArticleVisitor
from istina.model.visitors.scoring_visitor import ScoringVisitor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def article():
    return Article.create(
        title="Test article for scoring visitor",
        url="https://example.com/scoring-visitor-test",
        source="Test Source",
        published_at="2026-01-01T00:00:00Z",
        summary="A neutral summary.",
    )


@pytest.fixture
def mock_provider():
    return MockProvider()


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------

def test_scoring_visitor_is_article_visitor(mock_provider):
    visitor = ScoringVisitor(provider=mock_provider)
    assert isinstance(visitor, ArticleVisitor)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_visit_returns_bias_score(mock_provider, article):
    visitor = ScoringVisitor(provider=mock_provider)
    result = visitor.visit(article)
    assert isinstance(result, BiasScore)


def test_visit_delegates_to_provider(article):
    """visit() must call provider.analyze_article with the exact article."""
    expected = MockProvider().analyze_article(article)
    stub = MagicMock()
    stub.analyze_article.return_value = expected

    visitor = ScoringVisitor(provider=stub)
    result = visitor.visit(article)

    stub.analyze_article.assert_called_once_with(article)
    assert result is expected


def test_visit_result_article_id_matches(mock_provider, article):
    visitor = ScoringVisitor(provider=mock_provider)
    score = visitor.visit(article)
    assert score.article_id == article.id


# ---------------------------------------------------------------------------
# __init__ guards
# ---------------------------------------------------------------------------

def test_none_provider_raises_value_error():
    with pytest.raises(ValueError, match="provider must not be None"):
        ScoringVisitor(provider=None)


def test_provider_without_analyze_article_raises_type_error():
    class BadProvider:
        pass

    with pytest.raises(TypeError, match="analyze_article"):
        ScoringVisitor(provider=BadProvider())


def test_provider_with_non_callable_analyze_article_raises_type_error():
    class BadProvider:
        analyze_article = "not_callable"

    with pytest.raises(TypeError, match="analyze_article"):
        ScoringVisitor(provider=BadProvider())
