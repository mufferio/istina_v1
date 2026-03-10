"""
ArticleVisitor interface.

Purpose:
- Define a visitor contract for operations over Articles.

Example usage:
- visitor.visit(article) -> result
- Could be used by services to apply transformations consistently.

Note:
- Keep this lightweight; in Python you can implement as Protocol/ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from istina.model.entities.article import Article


class ArticleVisitor(ABC):
    """
    Visitor base class for operations over Articles.

    Implementors should define `visit(article)` to perform an operation on the
    Article and return a result (or None).
    """

    @abstractmethod
    def visit(self, article: Article) -> Any:
        """
        Visit an Article and perform an operation.

        Args:
            article: The Article to operate on.

        Returns:
            The result of the operation, or None.
        """
        ...