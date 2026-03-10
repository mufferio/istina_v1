"""
ScoringVisitor — visit() return type and determinism tests.

Covers:
- visit() returns a BiasScore instance
- returned BiasScore has correct article_id
- returned BiasScore fields satisfy BiasScore invariants (provider, label, confidence)
- determinism: same article visited twice → identical BiasScore
- determinism: same article visited by two independent ScoringVisitor instances → identical BiasScore
- determinism: different articles produce different scores
- determinism holds across repeated calls on the same visitor instance
"""

from __future__ import annotations

import pytest

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider
from istina.model.visitors.scoring_visitor import ScoringVisitor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provider():
    return MockProvider()


@pytest.fixture
def visitor(provider):
    return ScoringVisitor(provider=provider)


@pytest.fixture
def article_a():
    return Article.create(
        title="Scientists discover new renewable energy source",
        url="https://example.com/energy-article",
        source="Science Daily",
        published_at="2026-01-10T09:00:00Z",
        summary="Researchers report a promising breakthrough in solar efficiency.",
    )


@pytest.fixture
def article_b():
    return Article.create(
        title="Shocking elite mainstream media disaster revealed",
        url="https://example.com/clickbait-article",
        source="Opinion Wire",
        published_at="2026-01-11T14:00:00Z",
        summary="Everyone knows this is clearly an outrage.",
    )


# ---------------------------------------------------------------------------
# visit() return type
# ---------------------------------------------------------------------------

def test_visit_returns_bias_score(visitor, article_a):
    result = visitor.visit(article_a)
    assert isinstance(result, BiasScore)


def test_visit_score_article_id_matches_article(visitor, article_a):
    result = visitor.visit(article_a)
    assert result.article_id == article_a.id


def test_visit_score_has_valid_bias_label(visitor, article_a):
    result = visitor.visit(article_a)
    assert result.overall_bias_label in ("left", "center", "right", "unknown")


def test_visit_score_confidence_in_range(visitor, article_a):
    result = visitor.visit(article_a)
    assert 0.0 <= result.confidence <= 1.0


def test_visit_score_rhetorical_bias_is_list_of_strings(visitor, article_a):
    result = visitor.visit(article_a)
    assert isinstance(result.rhetorical_bias, list)
    assert all(isinstance(flag, str) for flag in result.rhetorical_bias)


def test_visit_score_claim_checks_is_list_of_dicts(visitor, article_a):
    result = visitor.visit(article_a)
    assert isinstance(result.claim_checks, list)
    assert all(isinstance(c, dict) for c in result.claim_checks)


# ---------------------------------------------------------------------------
# Determinism — same article, same visitor
# ---------------------------------------------------------------------------

def test_same_article_visited_twice_returns_equal_scores(visitor, article_a):
    score1 = visitor.visit(article_a)
    score2 = visitor.visit(article_a)
    assert score1.article_id == score2.article_id
    assert score1.overall_bias_label == score2.overall_bias_label
    assert score1.rhetorical_bias == score2.rhetorical_bias
    assert score1.claim_checks == score2.claim_checks
    assert score1.confidence == score2.confidence
    assert score1.timestamp == score2.timestamp


def test_same_article_visited_many_times_always_equal(visitor, article_a):
    scores = [visitor.visit(article_a) for _ in range(5)]
    first = scores[0]
    for s in scores[1:]:
        assert s.overall_bias_label == first.overall_bias_label
        assert s.confidence == first.confidence
        assert s.rhetorical_bias == first.rhetorical_bias
        assert s.timestamp == first.timestamp


# ---------------------------------------------------------------------------
# Determinism — independent visitor instances, same provider type
# ---------------------------------------------------------------------------

def test_two_independent_visitors_produce_same_score_for_same_article(article_a):
    visitor1 = ScoringVisitor(provider=MockProvider())
    visitor2 = ScoringVisitor(provider=MockProvider())
    s1 = visitor1.visit(article_a)
    s2 = visitor2.visit(article_a)
    assert s1.article_id == s2.article_id
    assert s1.overall_bias_label == s2.overall_bias_label
    assert s1.confidence == s2.confidence
    assert s1.rhetorical_bias == s2.rhetorical_bias
    assert s1.timestamp == s2.timestamp


# ---------------------------------------------------------------------------
# Determinism — different articles produce different scores
# ---------------------------------------------------------------------------

def test_different_articles_produce_different_scores(visitor, article_a, article_b):
    score_a = visitor.visit(article_a)
    score_b = visitor.visit(article_b)
    # article_ids must differ (different articles)
    assert score_a.article_id != score_b.article_id
    # At least one scored field should differ (MockProvider is content-aware)
    assert (
        score_a.overall_bias_label != score_b.overall_bias_label
        or score_a.confidence != score_b.confidence
        or score_a.rhetorical_bias != score_b.rhetorical_bias
    )


def test_loaded_language_article_flags_rhetorical_bias(visitor, article_b):
    """article_b contains loaded language keywords; MockProvider should flag them."""
    score = visitor.visit(article_b)
    assert len(score.rhetorical_bias) > 0
