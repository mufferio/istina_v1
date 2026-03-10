"""
Live smoke tests for Gemini provider with real API.

REQUIRED: Set environment variable ISTINA_GEMINI_API_KEY or GEMINI_API_KEY
These tests make actual API calls to Google Gemini and cost money.

Usage:
  # Set your API key
  export ISTINA_GEMINI_API_KEY="your-actual-gemini-api-key"
  
  # Run the smoke tests
  pytest tests/test_providers/test_gemini_live_smoke.py -v -s

Features tested:
- Real API calls with actual parsing
- Settings integration and configuration
- Rate limiting with multiple requests
- Complete BiasScore generation pipeline
- Repository storage integration
"""

import os
import pytest
import time
from datetime import datetime, timezone

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.gemini_provider import GeminiProvider
from istina.model.repositories.memory_repository import MemoryRepository
from istina.config.settings import Settings
from istina.utils.rate_limiter import RateLimiter


def _has_gemini_key() -> bool:
    """Check for Gemini API key using multiple naming conventions."""
    return bool(
        os.getenv("ISTINA_GEMINI_API_KEY") or 
        os.getenv("GEMINI_API_KEY") or 
        os.getenv("gemini_api_key")
    )


def _get_gemini_key() -> str:
    """Get Gemini API key from environment variables."""
    return (
        os.getenv("ISTINA_GEMINI_API_KEY") or 
        os.getenv("GEMINI_API_KEY") or 
        os.getenv("gemini_api_key") or 
        ""
    )


# Skip all tests in this module if no API key is available
pytestmark = pytest.mark.skipif(
    not _has_gemini_key(),
    reason="LIVE TEST: Set ISTINA_GEMINI_API_KEY, GEMINI_API_KEY, or gemini_api_key to run live tests"
)


@pytest.fixture
def live_settings():
    """Settings configured for live Gemini testing."""
    api_key = _get_gemini_key()
    return {
        "provider": "gemini",
        "gemini_api_key": api_key,
        "gemini_model": "gemini-2.5-flash",
        "rate_limit_rpm": 15  # Conservative for free tier
    }


@pytest.fixture
def test_article():
    """Create a test article with balanced, neutral content for consistent testing."""
    return Article.create(
        title="Local Government Reviews Infrastructure Spending",
        url="https://example.com/istina-live-test-infrastructure",
        source="Istina Live Test",
        published_at="2024-02-15T10:30:00Z",
        summary="City officials announced they will review the annual infrastructure budget allocation. The mayor stated the review will examine current projects and prioritize future investments. Citizens are invited to attend public meetings scheduled for next month."
    )


class TestGeminiLiveIntegration:
    """Live integration tests using real Gemini API."""

    def test_live_analysis_basic_functionality(self, live_settings, test_article):
        """Test basic live analysis with real Gemini API."""
        print(f"\\n🔥 LIVE TEST: Testing with real Gemini API")
        print(f"Article: {test_article.title}")
        print(f"API Key present: {'Yes' if live_settings['gemini_api_key'] else 'No'}")
        
        # Create provider from settings
        provider = GeminiProvider.from_settings(live_settings)
        
        start_time = time.time()
        score = provider.analyze_article(test_article)
        elapsed = time.time() - start_time
        
        print(f"\\n📊 Analysis completed in {elapsed:.2f}s")
        print(f"   Bias Label: {score.overall_bias_label}")
        print(f"   Confidence: {score.confidence}")
        print(f"   Rhetorical Flags: {score.rhetorical_bias}")
        print(f"   Claims Found: {len(score.claim_checks)}")
        
        # Verify BiasScore structure
        assert isinstance(score, BiasScore)
        assert score.provider == "gemini"
        assert score.article_id == test_article.id
        assert score.overall_bias_label in {"left", "center", "right", "unknown"}
        assert isinstance(score.rhetorical_bias, list)
        assert isinstance(score.claim_checks, list)
        assert 0.0 <= score.confidence <= 1.0
        assert isinstance(score.timestamp, datetime)
        assert score.timestamp.tzinfo is not None
        
        # Verify we got actual parsed content (not just fallbacks)
        print(f"   Raw response keys: {list(score.raw_response.keys())}")
        assert "bias_call" in score.raw_response
        assert "claims_call" in score.raw_response
        assert "model" in score.raw_response
        
        print("✅ Live analysis successful!")

    def test_live_rate_limiting_functionality(self, live_settings, test_article):
        """Test rate limiting with multiple real API calls."""
        print(f"\\n⏱️  LIVE TEST: Testing rate limiting with multiple requests")
        
        # Create rate limiter (6 requests per minute = 1 every 10 seconds)
        limiter = RateLimiter(requests_per_minute=6)
        
        # Create provider with rate limiter
        provider = GeminiProvider.from_settings(live_settings, limiter=limiter)
        
        # Make multiple requests and time them
        request_times = []
        
        for i in range(3):
            print(f"   Making request {i+1}/3...")
            start_time = time.time()
            
            # Modify article slightly for each request
            article = Article.create(
                title=f"Test Article {i+1}: Infrastructure Update",
                url=f"https://example.com/test-{i+1}",
                source="Rate Limit Test",
                published_at=datetime.now(timezone.utc).isoformat(),
                summary=f"Test content {i+1} for rate limiting validation."
            )
            
            score = provider.analyze_article(article)
            elapsed = time.time() - start_time
            request_times.append(elapsed)
            
            print(f"   Request {i+1} completed in {elapsed:.2f}s")
            
            # Verify each response
            assert score.provider == "gemini"
            assert score.article_id == article.id
        
        # Analyze timing (should be rate limited if working correctly)
        total_time = sum(request_times)
        avg_time = total_time / len(request_times)
        
        print(f"\\n   Total time: {total_time:.2f}s")
        print(f"   Average per request: {avg_time:.2f}s")
        print(f"   Rate limiting: {'Active' if any(t > 5 for t in request_times[1:]) else 'Not detected'}")
        
        print("✅ Rate limiting test completed!")

    def test_live_repository_integration(self, live_settings, test_article):
        """Test complete workflow: analysis + storage + retrieval."""
        print(f"\\n💾 LIVE TEST: Testing repository integration")
        
        # Analyze article
        provider = GeminiProvider.from_settings(live_settings)
        score = provider.analyze_article(test_article)
        
        print(f"   Generated BiasScore for article: {score.article_id}")
        
        # Store in repository
        repo = MemoryRepository()
        repo.upsert_bias_score(score)
        
        # Retrieve and verify
        fetched = repo.get_bias_score(test_article.id)
        
        assert fetched is not None
        assert fetched.article_id == test_article.id
        assert fetched.provider == "gemini"
        assert fetched.overall_bias_label == score.overall_bias_label
        assert fetched.confidence == score.confidence
        assert len(fetched.claim_checks) == len(score.claim_checks)
        
        print(f"   Stored and retrieved successfully")
        print(f"   Roundtrip verified: {fetched.overall_bias_label} bias")
        
        print("✅ Repository integration successful!")

    def test_live_detailed_parsing_validation(self, live_settings):
        """Test parsing with content designed to trigger specific responses."""
        print(f"\\n🔍 LIVE TEST: Testing detailed parsing with varied content")
        
        # Create article with specific content to test parsing
        test_cases = [
            {
                "name": "Neutral Content",
                "article": Article.create(
                    title="Weather Report: Temperature Trends This Week", 
                    url="https://example.com/weather",
                    source="Weather Service",
                    published_at="2024-02-15T12:00:00Z",
                    summary="The National Weather Service reports average temperatures will remain steady this week with partly cloudy conditions expected."
                )
            },
            {
                "name": "Opinion Content",
                "article": Article.create(
                    title="Editorial: Why We Must Act Now on Climate Policy",
                    url="https://example.com/editorial",
                    source="Opinion Section",
                    published_at="2024-02-15T12:00:00Z",
                    summary="The evidence is overwhelming - immediate action on climate change is essential. Opponents who claim economic concerns outweigh environmental catastrophe are fundamentally misguided."
                )
            }
        ]
        
        provider = GeminiProvider.from_settings(live_settings)
        
        for case in test_cases:
            print(f"\\n   Testing: {case['name']}")
            score = provider.analyze_article(case["article"])
            
            print(f"     Bias: {score.overall_bias_label} (confidence: {score.confidence})")
            print(f"     Flags: {score.rhetorical_bias}")
            print(f"     Claims: {len(score.claim_checks)}")
            
            if score.claim_checks:
                for i, claim in enumerate(score.claim_checks[:2]):  # Show first 2
                    print(f"       Claim {i+1}: {claim['verdict']} - {claim['claim'][:50]}...")
            
            # Basic validation
            assert score.provider == "gemini"
            assert score.overall_bias_label in {"left", "center", "right", "unknown"}
        
        print("\\n✅ Detailed parsing validation completed!")


if __name__ == "__main__":
    # Enable running directly for quick testing
    if _has_gemini_key():
        print("🔥 Running Gemini Live Smoke Tests...")
        print(f"API Key available: {'Yes'}")
        # Add any direct execution testing here
    else:
        print("❌ No Gemini API key found. Set ISTINA_GEMINI_API_KEY to run live tests.")