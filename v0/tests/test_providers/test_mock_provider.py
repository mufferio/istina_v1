"""
Mock provider tests.

Goal:
- Test deterministic behavior without external APIs.
- Verify:
  - Same article analyzed twice returns identical BiasScore
  - Different articles return different scores
  - Rhetorical flags work with keyword heuristics
  - Claim checks structure is populated
"""

import pytest
from datetime import datetime, timezone

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture 
def sample_article():
    return Article.create(
        title="Breaking: Shocking revelation about the elite mainstream media disaster",
        url="https://example.com/test-article",
        source="Test Source",
        published_at="2024-01-15T12:00:00Z",
        summary="This story is clearly a bombshell that everyone knows represents outrage."
    )


@pytest.fixture
def simple_article():
    return Article.create(
        title="Simple news story",
        url="https://example.com/simple",
        source="Test Source", 
        published_at="2024-01-15T12:00:00Z",
        summary="A basic news summary."
    )


def test_analyze_same_article_twice_returns_identical_results(mock_provider, sample_article):
    """Core requirement: analyzing the same article twice should return identical BiasScore."""
    
    # Analyze the same article twice
    result1 = mock_provider.analyze_article(sample_article)
    result2 = mock_provider.analyze_article(sample_article)
    
    # All fields should be identical
    assert result1.article_id == result2.article_id
    assert result1.provider == result2.provider
    assert result1.overall_bias_label == result2.overall_bias_label
    assert result1.rhetorical_bias == result2.rhetorical_bias
    assert result1.claim_checks == result2.claim_checks
    assert result1.confidence == result2.confidence
    assert result1.timestamp == result2.timestamp
    assert result1.raw_response == result2.raw_response
    
    # Verify the result is a valid BiasScore
    assert isinstance(result1, BiasScore)
    assert result1.article_id == sample_article.id


def test_different_articles_return_different_scores(mock_provider, sample_article, simple_article):
    """Different articles should produce different bias scores."""
    
    result1 = mock_provider.analyze_article(sample_article)
    result2 = mock_provider.analyze_article(simple_article)
    
    # Should have different article IDs and likely different scores
    assert result1.article_id != result2.article_id
    assert result1.article_id == sample_article.id
    assert result2.article_id == simple_article.id
    
    # Scores might be different (not guaranteed, but very likely given hash distribution)
    # At minimum, timestamps should be different due to different seeds
    assert result1.raw_response["mock_seed"] != result2.raw_response["mock_seed"]


def test_rhetorical_flags_detected_by_keywords(mock_provider, sample_article):
    """Test that rhetorical flags are detected via keyword heuristics."""
    
    result = mock_provider.analyze_article(sample_article)
    
    # Sample article contains: "shocking", "elite", "mainstream media", "disaster", "bombshell", 
    # "clearly", "everyone knows", "outrage"
    expected_flags = {"loaded_language", "assertion_without_evidence", "us_vs_them"}
    actual_flags = set(result.rhetorical_bias)
    
    # Should detect multiple rhetorical flags
    assert len(result.rhetorical_bias) > 0
    assert expected_flags.issubset(actual_flags), f"Expected {expected_flags} to be subset of {actual_flags}"


def test_simple_article_has_fewer_rhetorical_flags(mock_provider, simple_article):
    """Simple article should have fewer/no rhetorical flags."""
    
    result = mock_provider.analyze_article(simple_article)
    
    # Simple article has neutral language, so should have fewer flags
    # (might still have the deterministic sensationalism flag for some IDs)
    rhetorical_count = len(result.rhetorical_bias)
    assert rhetorical_count <= 1  # At most the deterministic sensationalism flag


def test_claim_checks_structure_populated(mock_provider, sample_article):
    """Verify claim_checks has the expected stub structure."""
    
    result = mock_provider.analyze_article(sample_article)
    
    assert len(result.claim_checks) == 1
    claim = result.claim_checks[0]
    
    # Check required fields are present
    assert "claim" in claim
    assert "verdict" in claim  
    assert "confidence" in claim
    assert "evidence" in claim
    
    # Check types and values
    assert isinstance(claim["claim"], str)
    assert claim["verdict"] in ["true", "false", "mixed", "unverified"]
    assert 0.0 <= claim["confidence"] <= 1.0
    assert isinstance(claim["evidence"], list)
    
    # Should include article ID in claim text for traceability
    assert sample_article.id[:8] in claim["claim"]


def test_analysis_result_fields_valid(mock_provider, sample_article):
    """Verify that all BiasScore fields are valid."""
    
    result = mock_provider.analyze_article(sample_article)
    
    # Check basic field types and constraints
    assert isinstance(result.article_id, str)
    assert result.article_id == sample_article.id
    assert result.provider == "mock"
    assert result.overall_bias_label in ["left", "center", "right", "unknown"]
    assert isinstance(result.rhetorical_bias, list)
    assert isinstance(result.claim_checks, list)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.timestamp, datetime)
    assert result.timestamp.tzinfo is not None  # Should be timezone-aware
    assert isinstance(result.raw_response, dict)
    
    # Check raw response structure
    assert "mock_seed" in result.raw_response
    assert "inputs" in result.raw_response
    assert isinstance(result.raw_response["mock_seed"], int)


def test_deterministic_timestamp(mock_provider, sample_article):
    """Verify timestamp is deterministic, not based on current time."""
    
    result1 = mock_provider.analyze_article(sample_article)
    result2 = mock_provider.analyze_article(sample_article)
    
    # Timestamps should be identical (deterministic)
    assert result1.timestamp == result2.timestamp
    
    # Should be in UTC timezone
    assert result1.timestamp.tzinfo == timezone.utc


def test_error_handling_for_missing_article_id(mock_provider):
    """Test handling of invalid article without ID."""
    
    # This test is more theoretical since Article.create always generates an ID
    # but tests the error path in the provider
    
    # We can't easily create an Article without an ID since it's computed in create()
    # But we can test the provider's error handling by creating a mock object
    class MockArticleNoId:
        def __init__(self):
            self.title = "Test"
            self.summary = "Test summary"
    
    mock_article = MockArticleNoId()
    
    with pytest.raises(ValueError, match="Article missing id"):
        mock_provider.analyze_article(mock_article)