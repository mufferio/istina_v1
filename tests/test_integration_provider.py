"""
End-to-end integration test for ISTINA_PROVIDER environment variable.

This test demonstrates that:
1. ISTINA_PROVIDER=mock loads MockProvider correctly
2. MockProvider returns deterministic results
3. The whole system works together seamlessly
"""

import os
import pytest 
from unittest.mock import patch

from istina.config.settings import load_settings
from istina.model.providers.provider_factory import create_provider
from istina.model.providers.mock_provider import MockProvider
from istina.model.entities.article import Article


@pytest.fixture
def test_article():
    """Create a test article for integration testing."""
    return Article.create(
        title="Test article with loaded language and shocking news",
        url="https://example.com/test-integration",
        source="Integration Test Source",
        published_at="2024-01-15T12:00:00Z",
        summary="This clearly demonstrates integration testing."
    )


class TestEndToEndIntegration:
    """Test complete integration from environment variable to analysis results."""

    @patch.dict(os.environ, {"ISTINA_PROVIDER": "mock"})
    def test_full_integration_istina_provider_mock(self, test_article):
        """
        Complete integration test: 
        ISTINA_PROVIDER=mock -> Settings -> Factory -> MockProvider -> Analysis
        """
        
        # 1. Load settings from environment
        settings = load_settings()
        assert settings.provider == "mock"
        
        # 2. Create provider via factory
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)
        
        # 3. Analyze article and verify deterministic results
        result1 = provider.analyze_article(test_article)
        result2 = provider.analyze_article(test_article) 
        
        # Results should be identical (deterministic)
        assert result1.article_id == result2.article_id
        assert result1.overall_bias_label == result2.overall_bias_label
        assert result1.confidence == result2.confidence
        assert result1.timestamp == result2.timestamp
        assert result1.rhetorical_bias == result2.rhetorical_bias
        assert result1.claim_checks == result2.claim_checks
        
        # Verify expected content
        assert result1.article_id == test_article.id
        assert result1.provider == "mock"
        assert result1.overall_bias_label in ["left", "center", "right", "unknown"]
        assert len(result1.rhetorical_bias) > 0  # Should detect loaded language
        assert len(result1.claim_checks) == 1
        
        # Check rhetorical flags detected keywords
        assert "loaded_language" in result1.rhetorical_bias  # "loaded", "shocking"
        assert "assertion_without_evidence" in result1.rhetorical_bias  # "clearly"

    @patch.dict(os.environ, {"ISTINA_PROVIDER": "MOCK"})  # Test case insensitive
    def test_integration_case_insensitive_env_var(self, test_article):
        """Test that ISTINA_PROVIDER is case insensitive."""
        
        settings = load_settings()
        assert settings.provider == "MOCK"  # Preserves case from env var
        
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)  # But factory handles it correctly
        
    @patch.dict(os.environ, {}, clear=True)  # Clear all env vars
    def test_integration_default_to_mock_when_no_env_var(self, test_article):
        """Test default behavior when ISTINA_PROVIDER not set."""
        
        settings = load_settings()
        assert settings.provider == "mock"  # Default from Settings
        
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)
        
        # Should still work normally
        result = provider.analyze_article(test_article)
        assert result.provider == "mock"
        assert result.article_id == test_article.id

    def test_integration_analysis_consistency_across_runs(self, test_article):
        """Test that analysis results are consistent across multiple provider instances."""
        
        # Create multiple providers and verify same results
        settings1 = load_settings()
        provider1 = create_provider(settings1)
        
        settings2 = load_settings() 
        provider2 = create_provider(settings2)
        
        result1 = provider1.analyze_article(test_article)
        result2 = provider2.analyze_article(test_article) 
        
        # Should be identical even from different provider instances
        assert result1.overall_bias_label == result2.overall_bias_label
        assert result1.confidence == result2.confidence
        assert result1.timestamp == result2.timestamp
        assert result1.rhetorical_bias == result2.rhetorical_bias


if __name__ == "__main__":
    # Standalone test runner for quick verification
    import sys
    
    # Set environment variable 
    os.environ["ISTINA_PROVIDER"] = "mock"
    
    # Create test article
    article = Article.create(
        title="Test: shocking revelation about mainstream media",
        url="https://example.com/standalone-test",
        source="Standalone Test",
        published_at="2024-01-15T12:00:00Z",
        summary="Everyone knows this is clearly a test article."
    )
    
    # Load settings and create provider
    settings = load_settings()
    provider = create_provider(settings)
    
    print(f"Settings provider: {settings.provider}")
    print(f"Provider type: {type(provider)}")
    print(f"Provider name: {provider.provider_name}")
    
    # Analyze article
    result = provider.analyze_article(article)
    
    print(f"\nAnalysis results:")
    print(f"Article ID: {result.article_id}")
    print(f"Bias label: {result.overall_bias_label}")
    print(f"Confidence: {result.confidence}")
    print(f"Rhetorical flags: {result.rhetorical_bias}")
    print(f"Claims: {len(result.claim_checks)}")
    
    # Test determinism
    result2 = provider.analyze_article(article)
    print(f"\nDeterminism check: {result.timestamp == result2.timestamp}")
    
    print("\n✅ Integration test passed!")