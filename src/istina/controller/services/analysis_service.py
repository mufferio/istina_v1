"""
AnalysisService (use case).

Workflow:
1) Select which Articles to analyze (unscored or filtered by params).
2) For each Article:
   - Run visitor.visit(article) to produce BiasScore
   - Persist BiasScore via repository
3) Return summary stats + failures.

Reliability:
- Uses retry + rate limiting around provider calls.
- Handles provider failures gracefully (log and continue or stop based on config).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Protocol, Union

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.base_repository import BaseRepository
from istina.model.visitors.article_visitor import ArticleVisitor
from istina.model.visitors.scoring_visitor import ScoringVisitor


@dataclass(frozen=True)
class SelectionParams:
    limit: Optional[int] = None  # Max number of articles to analyze
    source: Optional[str] = None  # Filter by article source
    since: Optional[datetime] = None  # Filter articles published since this date


class BiasProvider(Protocol):
    """
    Provider interface (mockable) for analyzing an article.
    Pass directly to analyze() and it will be wrapped in a ScoringVisitor automatically.
    """
    def analyze_article(self, article: Article) -> BiasScore:
        """Given an Article, return a BiasScore."""
        ...


@dataclass
class AnalyzeResult:
    analyzed_count: int
    skipped_count: int
    failed_count: int
    errors: List[str] = field(default_factory=list)


class AnalysisService:
    """
    Use-case service: decide which Articles should be analyzed next.

    Selection rules (Issue 5.3):
    - Only return articles that do NOT have a BiasScore yet.
    - Support optional limit.
    - Support optional source and since filters (delegated to repo.list_articles).
    """

    def __init__(self, repo: BaseRepository):
        self.repo = repo

    def select_unscored(self, params: Optional[SelectionParams] = None) -> List[Article]:
        """
        Select Articles that have no BiasScore yet.

        Implementation strategy:
        - Ask repo for articles (optionally filtered by source/since).
        - Filter out any article that already has a BiasScore in repo.
        - Apply limit after filtering so the count reflects truly unscored articles.

        Returns:
            list[Article]
        """
        if params is None:
            params = SelectionParams()

        # Pull a candidate set without a limit — we apply limit ourselves
        # after filtering so that "limit=N" means "N unscored articles", not
        # "check the first N articles for a score".
        candidates = self.repo.list_articles(
            source=params.source,
            since=params.since,
            limit=None,
        )

        unscored: List[Article] = []
        for a in candidates:
            if params.limit is not None and len(unscored) >= params.limit:
                break

            if self.repo.get_bias_score(a.id) is None:
                unscored.append(a)

        return unscored
    

    def analyze(
        self,
        visitor_or_provider: Union[ArticleVisitor, BiasProvider],
        params: Optional[SelectionParams] = None,
    ) -> AnalyzeResult:
        """
        Analyze selected (unscored) articles and persist BiasScores.

        Accepts either:
        - An ArticleVisitor (e.g. ScoringVisitor) — used directly.
        - A BiasProvider — automatically wrapped in ScoringVisitor.

        Requirements (Issue 5.4):
        - loops selected articles
        - calls visitor.visit(article)
        - repo.upsert_bias_score(score)
        - collects stats (analyzed/skipped/failed)
        - handles visitor/provider errors gracefully (record failure, continue)

        Notes:
        - "skipped" here means: article was selected but ended up not analyzable
          (e.g., missing id) or visitor returned invalid score.
        """
        # Build visitor: accept a raw provider for backward compat
        if isinstance(visitor_or_provider, ArticleVisitor):
            visitor = visitor_or_provider
        else:
            visitor = ScoringVisitor(provider=visitor_or_provider)
        selected = self.select_unscored(params)

        analyzed = 0
        skipped = 0
        failed = 0
        errors: List[str] = []

        for article in selected:
            article_id = article.id
            if not article_id:
                skipped += 1
                errors.append("Skipped article with missing id")
                continue

            try:
                score = visitor.visit(article)

                if getattr(score, "article_id", None) != article_id:
                    skipped += 1
                    errors.append(f"Provider returned score with mismatched article_id for article {article_id}")
                    continue

                self.repo.upsert_bias_score(score)
                analyzed += 1

            except Exception as e:
                failed += 1
                errors.append(f"Failed to analyze article {article_id}: {str(e)}")

        return AnalyzeResult(
            analyzed_count=analyzed,
            skipped_count=skipped,
            failed_count=failed,
            errors=errors,
        )   
