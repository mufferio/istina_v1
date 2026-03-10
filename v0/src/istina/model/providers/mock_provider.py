"""
Mock provider for analysis.

Purpose:
- Provide predictable, fast analysis results without external APIs.
- Used for:
  - tests
  - offline development
  - demo flows

Behavior:
- Generates BiasScore using simple heuristics:
  - “loaded language” detection via keyword list
  - trivial claim extraction or stub claims
- Always returns the same result for the same Article id (deterministic).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.base_provider import BaseProvider

VALID_LABELS: Tuple[str, ...] = ("left", "center", "right", "unknown")


def _stable_int(s: str) -> int:
    """Generate a stable integer from a string using hashing."""
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)  # enough entropy for stable buckets


def _pick_label(seed: int) -> str:
    # Simple deterministic mapping
    r = seed % 100
    if r < 30:
        return "left"
    if r < 70:
        return "center"
    if r < 95:
        return "right"
    return "unknown"


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass(frozen=True)
class MockProvider(BaseProvider):
    """
    Offline deterministic provider for dev/testing.

    Determinism:
        Same article_id => identical outputs (including timestamp).
        (We set timestamp deterministically rather than "now".)
    """

    provider_name: str = "mock"

    def analyze_article(self, article: Article) -> BiasScore:
        aid = getattr(article, "id", None)
        if not aid:
            raise ValueError("Article missing id")

        seed = _stable_int(aid)

        # ----- rhetorical flags (simple keyword heuristic) -----
        text = " ".join(
            [
                str(getattr(article, "title", "") or ""),
                str(getattr(article, "summary", "") or ""),
            ]
        ).lower()

        rhetorical: List[str] = []
        # tiny heuristic set: deterministic & explainable
        if any(w in text for w in ("shocking", "outrage", "disaster", "explode", "bombshell")):
            rhetorical.append("loaded_language")
        if any(w in text for w in ("everyone knows", "obviously", "clearly", "undeniable")):
            rhetorical.append("assertion_without_evidence")
        if any(w in text for w in ("they", "them", "elite", "mainstream media")):
            rhetorical.append("us_vs_them")

        # Add a deterministic extra flag sometimes so empty titles still vary by id
        if (seed % 10) == 0:
            rhetorical.append("sensationalism")

        # ----- stub claim checks structure -----
        # v0 stub: a list of dicts with stable fields
        claim_checks: List[Dict[str, Any]] = [
            {
                "claim": f"Mock claim derived from {aid[:8]}",
                "verdict": ["true", "false", "mixed", "unverified"][seed % 4],
                "confidence": round(_clamp01(((seed % 100) / 100.0)), 2),
                "evidence": [],
            }
        ]

        # ----- overall label + confidence -----
        label = _pick_label(seed)
        confidence = round(_clamp01(0.35 + ((seed % 60) / 100.0)), 2)  # 0.35..0.95

        # ----- deterministic timestamp -----
        # Use a fixed epoch + seed-derived offset so it's identical for same aid.
        base = 1700000000  # fixed unix seconds constant
        ts_seconds = base + (seed % 1_000_000)
        timestamp = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)

        raw: Dict[str, Any] = {
            "mock_seed": seed,
            "inputs": {"title": getattr(article, "title", ""), "summary": getattr(article, "summary", "")},
        }

        return BiasScore(
            article_id=aid,
            provider=self.provider_name,
            overall_bias_label=label,
            rhetorical_bias=rhetorical,
            claim_checks=claim_checks,
            confidence=confidence,
            timestamp=timestamp,
            raw_response=raw,
        )