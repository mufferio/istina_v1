"""
ScoringVisitor.

Purpose:
- A concrete visitor that produces BiasScore for an Article.
- Often wraps a Provider and returns normalized results.

Used by:
- analysis_service.py to apply analysis consistently across many Articles
- helps keep analysis logic modular and testable
"""

from __future__ import annotations

from typing import Protocol

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.visitors.article_visitor import ArticleVisitor


class _BiasProvider(Protocol):
    """Minimal provider interface expected by ScoringVisitor."""

    def analyze_article(self, article: Article) -> BiasScore:
        ...


class ScoringVisitor(ArticleVisitor):
    """
    Concrete visitor that delegates to a BiasProvider and returns a BiasScore.

    Example::

        visitor = ScoringVisitor(provider=my_provider)
        score: BiasScore = visitor.visit(article)
    """

    def __init__(self, provider: _BiasProvider) -> None:
        if provider is None:
            raise ValueError("provider must not be None")
        if not callable(getattr(provider, "analyze_article", None)):
            raise TypeError("provider must expose a callable .analyze_article(article) method")
        self._provider = provider

    def visit(self, article: Article) -> BiasScore:
        """
        Analyze the Article via the injected provider.

        Args:
            article: The Article to score.

        Returns:
            BiasScore produced by the provider.
        """
        return self._provider.analyze_article(article)
