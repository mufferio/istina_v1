"""
Provider interface (AI analysis contract).

Defines:
- A standard method signature like:
  - analyze_article(article: Article) -> BiasScore

Design goals:
- Services depend on this interface, not on Gemini/OpenAI/etc.
- Normalize provider outputs into BiasScore (provider-agnostic).

Notes:
- Handle provider errors with domain-level exceptions
  (or raise custom exceptions used by services).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore



class BaseProvider(ABC):
    """
    Standard analysis provider interface.

    Goal:
        Make providers swappable (mock now, GPT later) without changing services.

    Contract:
        analyze_article(article) MUST return a fully-normalized, provider-agnostic BiasScore.

    Normalization requirements (v0):
        - score.article_id must equal article.article_id (or article.id if that's your field)
        - provider must be a stable identifier string (e.g., "mock", "gpt-4")
        - overall_bias_label must be one of your allowed labels (e.g., left/center/right/unknown)
        - rhetorical_bias is a list[str] (can be empty)
        - claim_checks is a list[dict] (can be empty)
        - confidence is float in [0.0, 1.0]
        - timestamp is a datetime
        - raw_response is optional dict containing provider-specific payload (if any)
    """
    @abstractmethod
    def analyze_article(self, article: Article) -> BiasScore:
        """
        Analyze the given article and return a BiasScore.

        Args:
            article (Article): The article to analyze.
        """
        raise NotImplementedError("Subclasses must implement analyze_article method")