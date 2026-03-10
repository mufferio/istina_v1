"""
Visitor pattern operations over domain entities.

Purpose:
- Encapsulate operations you want to run across entities without
  stuffing behavior into entities themselves.
- Useful for:
  - scoring pipelines
  - report generation transforms
  - exporting to formats

Visitors:
- ArticleVisitor: base visitor interface for Article traversal
- ScoringVisitor: produces BiasScore (or triggers provider calls)
"""

from istina.model.visitors.article_visitor import ArticleVisitor
from istina.model.visitors.scoring_visitor import ScoringVisitor

__all__ = ["ArticleVisitor", "ScoringVisitor"]
