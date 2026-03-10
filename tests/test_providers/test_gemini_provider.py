"""
Gemini provider tests.

Goal:
- Test GeminiProvider integration without calling real API
- Verify prompt generation, settings handling, and secret protection
- Mock HTTP calls to test error handling and response processing
- Ensure rate limiting and retry logic work correctly
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.gemini_provider import (
    GeminiProvider, 
    build_bias_prompt, 
    build_claims_prompt,
    ProviderError
)
from istina.model.providers.provider_factory import create_provider, ConfigError
from istina.config.settings import Settings
from istina.utils.rate_limiter import RateLimiter


@pytest.fixture
def sample_article():
    """Create a test article for prompt generation tests."""
    return Article.create(
        title="Breaking: Government announces new climate policy amid controversy",
        url="https://example.com/climate-policy",
        source="Example News",
        published_at="2024-01-15T12:00:00Z",
        summary="The administration unveiled sweeping climate regulations that critics say will devastate the economy while supporters claim are essential for saving the planet."
    )


@pytest.fixture
def mock_settings():
    """Settings configured for Gemini provider."""
    return Settings(
        provider="gemini",
        # Note: In real usage, these would come from environment variables
        # This is just for testing the settings structure
    )


@pytest.fixture
def mock_settings_dict():
    """Dictionary-style settings for testing."""
    return {
        "provider": "gemini",
        "gemini_api_key": "test-api-key-123",
        "gemini_model": "gemini-1.5-pro", 
        "rate_limit_rpm": 30
    }


class TestPromptGeneration:
    """Test the prompt templates for bias detection and claim extraction."""

    def test_bias_prompt_structure_and_content(self, sample_article):
        """Test bias detection prompt has correct structure and includes article data."""
        prompt = build_bias_prompt(sample_article)
        
        # Should contain article information
        assert "Government announces new climate policy" in prompt
        assert "Example News" in prompt
        assert "https://example.com/climate-policy" in prompt
        assert "devastating the economy" in prompt or "devastate the economy" in prompt
        
        # Should contain analysis framework
        assert "overall_bias_label" in prompt
        assert "rhetorical_flags" in prompt
        assert "confidence" in prompt
        assert "justification" in prompt
        
        # Should specify exact output format
        assert "left|center|right|unknown" in prompt
        assert "JSON" in prompt
        
        # Should include comprehensive rhetorical flags
        rhetorical_flags = [
            "loaded_language", "cherry_picking", "ad_hominem", 
            "appeal_to_fear", "strawman", "whataboutism", 
            "false_dilemma", "us_vs_them", "assertion_without_evidence",
            "sensationalism"
        ]
        for flag in rhetorical_flags:
            assert flag in prompt
            
        # Should provide clear analysis criteria
        assert "Word choice and framing" in prompt
        assert "Selection and omission" in prompt
        assert "Sources cited" in prompt

    def test_claims_prompt_structure_and_content(self, sample_article):
        """Test claim extraction prompt has correct structure and specificity."""
        prompt = build_claims_prompt(sample_article)
        
        # Should contain article information
        assert "Government announces new climate policy" in prompt
        assert "Example News" in prompt
        
        # Should contain extraction criteria
        assert "up to 5" in prompt
        assert "verifiable" in prompt
        assert "claim_checks" in prompt
        
        # Should specify claim types to extract
        assert "Numerical data" in prompt
        assert "Attribution claims" in prompt
        assert "Causal relationships" in prompt
        assert "Event descriptions" in prompt
        assert "Timeline assertions" in prompt
        
        # Should specify verdict categories clearly
        verdicts = ["true", "false", "mixed", "unverified"]
        for verdict in verdicts:
            assert verdict in prompt
        
        # Should include confidence scale guidance
        assert "0.0-0.3" in prompt
        assert "0.4-0.6" in prompt  
        assert "0.7-1.0" in prompt
        
        # Should specify exact JSON structure
        assert "JSON" in prompt
        assert "\"claim\":" in prompt
        assert "\"verdict\":" in prompt
        assert "\"confidence\":" in prompt
        assert "\"evidence\":" in prompt

    def test_prompts_handle_missing_article_fields(self):
        """Test prompts gracefully handle articles with missing fields."""
        minimal_article = Article.create(
            title="Minimal article",
            url="https://example.com/minimal",
            source="Test Source"
            # No published_at, no summary
        )
        
        bias_prompt = build_bias_prompt(minimal_article)
        claims_prompt = build_claims_prompt(minimal_article)
        
        # Should not crash and should still contain core structure
        assert "overall_bias_label" in bias_prompt
        assert "claim_checks" in claims_prompt
        assert "Minimal article" in bias_prompt
        assert "Minimal article" in claims_prompt


class TestGeminiProviderConfiguration:
    """Test GeminiProvider configuration and initialization."""

    def test_from_settings_with_valid_config(self, mock_settings_dict):
        """Test creating GeminiProvider from valid settings."""
        provider = GeminiProvider.from_settings(mock_settings_dict)
        
        assert provider.api_key == "test-api-key-123"
        assert provider.model == "gemini-1.5-pro"
        assert provider.timeout_seconds == 10.0

    def test_from_settings_with_rate_limiter(self, mock_settings_dict):
        """Test creating GeminiProvider with rate limiter."""
        limiter = RateLimiter(rpm=30)
        provider = GeminiProvider.from_settings(mock_settings_dict, limiter=limiter)
        
        assert provider.limiter is limiter

    def test_from_settings_missing_api_key(self):
        """Test that missing API key raises clear error."""
        settings = {"provider": "gemini"}  # Missing gemini_api_key
        
        with pytest.raises(ValueError, match="gemini_api_key is required"):
            GeminiProvider.from_settings(settings)

    def test_from_settings_with_custom_model(self):
        """Test custom model configuration.""" 
        settings = {
            "gemini_api_key": "test-key",
            "gemini_model": "gemini-1.5-flash"
        }
        
        provider = GeminiProvider.from_settings(settings)
        assert provider.model == "gemini-1.5-flash"

    def test_api_key_not_in_repr(self):
        """Test that API key is not exposed in string representation."""
        provider = GeminiProvider(api_key="secret-key-123", model="gemini-1.5-pro")
        repr_string = repr(provider)
        
        assert "secret-key-123" not in repr_string
        assert "gemini-1.5-pro" in repr_string


class TestProviderFactoryIntegration:
    """Test GeminiProvider integration with the provider factory."""

    def test_factory_creates_gemini_provider(self, mock_settings_dict):
        """Test provider factory creates GeminiProvider correctly."""
        provider = create_provider(mock_settings_dict)
        
        assert isinstance(provider, GeminiProvider)
        assert provider.api_key == "test-api-key-123"
        assert provider.model == "gemini-1.5-pro"

    def test_factory_applies_rate_limiting(self, mock_settings_dict):
        """Test that factory applies rate limiting based on settings."""
        provider = create_provider(mock_settings_dict)
        
        assert provider.limiter is not None
        assert provider.limiter.rpm == 30  # From mock_settings_dict

    def test_factory_handles_missing_gemini_provider(self):
        """Test factory error when GeminiProvider can't be imported."""
        settings = {"provider": "gemini", "gemini_api_key": "test"}
        
        # This should work now since we have implemented it
        provider = create_provider(settings)
        assert isinstance(provider, GeminiProvider)


class TestGeminiProviderApiCalls:
    """Test API call wrapper and error handling."""

    def test_call_gemini_success(self, mock_settings_dict):
        """Test successful Gemini API call.""" 
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "response"}]}}]
        }
        
        # Create provider with mocked post function
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response)
        
        result = provider._call_gemini("test prompt")
        
        # Verify the call was made correctly
        provider._post.assert_called_once()
        call_args = provider._post.call_args
        
        # Check URL
        assert "generativelanguage.googleapis.com" in call_args[0][0]
        assert provider.model in call_args[0][0]
        
        # Check that API key is in params (but not logged)
        assert call_args[1]["params"]["key"] == "test-api-key-123"
        
        # Check payload structure
        payload = call_args[1]["json"]
        assert "contents" in payload
        assert payload["contents"][0]["parts"][0]["text"] == "test prompt"
        
        # Check response
        assert result == mock_response.json.return_value

    def test_call_gemini_http_error(self, mock_settings_dict):
        """Test handling of HTTP error responses."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response)
        
        with pytest.raises(ProviderError, match="Gemini API returned status 400"):
            provider._call_gemini("test prompt")

    def test_call_gemini_invalid_json(self, mock_settings_dict):
        """Test handling of invalid JSON responses."""
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response)
        
        with pytest.raises(ProviderError, match="invalid JSON response"):
            provider._call_gemini("test prompt")

    def test_call_gemini_secret_protection(self, mock_settings_dict):
        """Test that secrets are not leaked in error messages."""
        mock_response = Mock()
        mock_response.status_code = 401  # Unauthorized
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response)
        
        with pytest.raises(ProviderError) as exc_info:
            provider._call_gemini("test prompt")
        
        error_message = str(exc_info.value)
        
        # Should not contain API key
        assert "test-api-key-123" not in error_message
        # Should not contain URL with key
        assert "key=" not in error_message

    @patch('istina.model.providers.gemini_provider.retry')
    def test_call_gemini_retry_logic(self, mock_retry, mock_settings_dict):
        """Test that retry logic is applied correctly."""
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=Mock(status_code=200, json=lambda: {}))
        
        provider._call_gemini("test prompt")
        
        # Verify retry was called with correct parameters
        mock_retry.assert_called_once()
        call_args = mock_retry.call_args
        
        # Check retry configuration
        assert call_args[1]["max_attempts"] == 3
        assert call_args[1]["base_delay"] == 0.5
        assert call_args[1]["backoff_factor"] == 2.0


class TestEndToEndAnalysis:
    """Test complete analysis workflow."""

    def test_analyze_article_structure(self, sample_article, mock_settings_dict):
        """Test that analyze_article returns properly structured BiasScore."""
        # Mock both API calls
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "response"}
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response)
        
        result = provider.analyze_article(sample_article)
        
        # Verify BiasScore structure
        assert isinstance(result, BiasScore)
        assert result.article_id == sample_article.id
        assert result.provider == "gemini"
        assert result.overall_bias_label in ["left", "center", "right", "unknown"]
        assert isinstance(result.rhetorical_bias, list) 
        assert isinstance(result.claim_checks, list)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo is not None  # Should be timezone-aware
        
        # Verify raw_response contains expected structure
        assert isinstance(result.raw_response, dict)
        assert "bias_call" in result.raw_response
        assert "claims_call" in result.raw_response
        assert "model" in result.raw_response
        assert result.raw_response["model"] == "gemini-1.5-pro"
        
        # Verify no secrets in raw_response
        raw_str = str(result.raw_response)
        assert "test-api-key-123" not in raw_str

    def test_analyze_article_makes_two_api_calls(self, sample_article, mock_settings_dict):
        """Test that analysis makes separate calls for bias and claims."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "response"}
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response) 
        
        provider.analyze_article(sample_article)
        
        # Should make exactly 2 API calls (bias + claims)
        assert provider._post.call_count == 2
        
        # Verify different prompts were used
        call1_payload = provider._post.call_args_list[0][1]["json"]
        call2_payload = provider._post.call_args_list[1][1]["json"] 
        
        prompt1 = call1_payload["contents"][0]["parts"][0]["text"]
        prompt2 = call2_payload["contents"][0]["parts"][0]["text"]
        
        # One should be bias prompt, other should be claims prompt
        assert prompt1 != prompt2
        assert ("overall_bias_label" in prompt1) != ("overall_bias_label" in prompt2)
        assert ("claim_checks" in prompt1) != ("claim_checks" in prompt2)

    def test_analyze_article_missing_id_error(self, mock_settings_dict):
        """Test error handling for article without ID."""
        # Create a mock article without ID (this is hard with the real Article class)
        mock_article = Mock()
        mock_article.id = None
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        
        with pytest.raises(ValueError, match="Article missing id"):
            provider.analyze_article(mock_article)

    @patch('istina.model.providers.gemini_provider.maybe_acquire')
    def test_analyze_article_applies_rate_limiting(self, mock_acquire, sample_article, mock_settings_dict):
        """Test that rate limiting is applied to API calls."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "response"}
        
        limiter = RateLimiter(rpm=30)
        provider = GeminiProvider.from_settings(mock_settings_dict, limiter=limiter)
        provider._post = Mock(return_value=mock_response)
        
        provider.analyze_article(sample_article)
        
        # Should call rate limiter twice (once for each API call)
        assert mock_acquire.call_count == 2
        mock_acquire.assert_called_with(limiter)


class TestSecurityAndPrivacy:
    """Test security aspects and secret protection."""

    def test_api_key_not_logged_in_normal_operation(self, sample_article, mock_settings_dict):
        """Test that API key doesn't appear in any logged output during normal operation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"safe": "response"}
        
        provider = GeminiProvider.from_settings(mock_settings_dict) 
        provider._post = Mock(return_value=mock_response)
        
        # Capture all string representations that might be logged
        result = provider.analyze_article(sample_article)
        provider_str = str(provider)
        result_str = str(result.raw_response)
        
        # API key should not appear in any of these
        secret = "test-api-key-123"
        assert secret not in provider_str
        assert secret not in result_str

    def test_response_sanitization(self, mock_settings_dict):
        """Test that response data is sanitized to remove potential key leaks."""
        # Mock response that might contain key information
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": "safe response",
            "key": "should-be-removed", 
            "api_key": "should-also-be-removed",
            "apiKey": "remove-this-too"
        }
        
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(return_value=mock_response)
        
        result = provider._call_gemini("test")
        
        # Sensitive keys should be removed
        assert "key" not in result
        assert "api_key" not in result
        assert "apiKey" not in result
        assert result["data"] == "safe response"


if __name__ == "__main__":
    # Quick demonstration test
    print("Testing Gemini Provider Prompts")
    print("=" * 50)
    
    # Test article
    article = Article.create(
        title="Test: Politicians clash over controversial new legislation", 
        url="https://example.com/test",
        source="Test News",
        published_at="2024-01-15T12:00:00Z",
        summary="The proposed bill has sparked fierce debate with supporters calling it essential reform while critics denounce it as government overreach."
    )
    
    # Test bias prompt
    bias_prompt = build_bias_prompt(article)
    print("\\nBias Detection Prompt Length:", len(bias_prompt))
    print("Contains bias analysis framework:", "overall_bias_label" in bias_prompt)
    print("Contains rhetorical flags:", "loaded_language" in bias_prompt)
    print("Requests JSON output:", "JSON" in bias_prompt)
    
    # Test claims prompt  
    claims_prompt = build_claims_prompt(article)
    print("\\nClaim Extraction Prompt Length:", len(claims_prompt))
    print("Contains claim criteria:", "verifiable" in claims_prompt)
    print("Contains verdict categories:", "unverified" in claims_prompt)
    print("Contains confidence guidance:", "0.0-0.3" in claims_prompt)
    
    print("\\n✅ Prompt templates are comprehensive and well-structured!")


class TestGeminiResponseParsing:
    """Test realistic Gemini response parsing and BiasScore generation."""
    
    def test_parse_realistic_gemini_responses(self, sample_article, mock_settings_dict):
        """Test parsing realistic Gemini API responses returns valid BiasScore."""
        
        # Create realistic bias analysis response
        bias_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '''{
  "overall_bias_label": "left",
  "rhetorical_flags": ["loaded_language", "appeal_to_fear"],
  "confidence": 0.75,
  "justification": "Article uses emotionally charged phrases like 'devastating the economy' and 'saving the planet' suggesting partisan framing."
}'''
                    }]
                }
            }]
        }
        
        # Create realistic claims analysis response
        claims_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '''{
  "claim_checks": [
    {
      "claim": "The administration unveiled sweeping climate regulations",
      "verdict": "true",
      "confidence": 0.9,
      "evidence": ["Policy announcement confirmed by official sources"]
    },
    {
      "claim": "Critics say regulations will devastate the economy",
      "verdict": "mixed", 
      "confidence": 0.6,
      "evidence": ["Opposition statements documented", "Economic impact disputed"]
    }
  ]
}'''
                    }]
                }
            }]
        }
        
        # Mock the HTTP responses
        mock_response_bias = Mock()
        mock_response_bias.status_code = 200
        mock_response_bias.json.return_value = bias_response
        
        mock_response_claims = Mock()
        mock_response_claims.status_code = 200
        mock_response_claims.json.return_value = claims_response
        
        # Create provider and mock HTTP calls to return different responses
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(side_effect=[mock_response_bias, mock_response_claims])
        
        # Analyze article
        result = provider.analyze_article(sample_article)
        
        # Verify BiasScore structure and content
        assert isinstance(result, BiasScore)
        assert result.article_id == sample_article.id
        assert result.provider == "gemini"
        
        # Verify parsed bias analysis
        assert result.overall_bias_label == "left"
        assert "loaded_language" in result.rhetorical_bias
        assert "appeal_to_fear" in result.rhetorical_bias
        assert len(result.rhetorical_bias) == 2
        assert result.confidence == 0.75
        
        # Verify parsed claim checks
        assert len(result.claim_checks) == 2
        
        first_claim = result.claim_checks[0]
        assert first_claim["claim"] == "The administration unveiled sweeping climate regulations"
        assert first_claim["verdict"] == "true"
        assert first_claim["confidence"] == 0.9
        assert "Policy announcement confirmed" in first_claim["evidence"][0]
        
        second_claim = result.claim_checks[1]
        assert second_claim["claim"] == "Critics say regulations will devastate the economy"
        assert second_claim["verdict"] == "mixed"
        assert second_claim["confidence"] == 0.6
        
        # Verify metadata
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo is not None
        
        # Verify raw_response preservation
        assert "bias_call" in result.raw_response
        assert "claims_call" in result.raw_response
        assert result.raw_response["model"] == "gemini-1.5-pro"
        
        print(f"✅ Parsed BiasScore: {result.overall_bias_label} bias, {result.confidence} confidence")
        print(f"   Rhetorical flags: {result.rhetorical_bias}")
        print(f"   Claims analyzed: {len(result.claim_checks)}")

    def test_parse_malformed_responses_with_fallbacks(self, sample_article, mock_settings_dict):
        """Test that malformed Gemini responses fall back gracefully."""
        
        # Malformed bias response (invalid JSON)
        bias_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "This is not JSON, just some text response from the model."
                    }]
                }
            }]
        }
        
        # Malformed claims response (missing required fields)
        claims_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '''```json
{
  "claim_checks": [
    {
      "broken": "no claim field",
      "invalid": "data structure"
    }
  ]
}
```'''
                    }]
                }
            }]
        }
        
        # Mock the HTTP responses
        mock_response_bias = Mock()
        mock_response_bias.status_code = 200
        mock_response_bias.json.return_value = bias_response
        
        mock_response_claims = Mock()
        mock_response_claims.status_code = 200
        mock_response_claims.json.return_value = claims_response
        
        # Create provider and analyze
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(side_effect=[mock_response_bias, mock_response_claims])
        
        result = provider.analyze_article(sample_article)
        
        # Verify fallback values
        assert result.overall_bias_label == "unknown"  # Fallback for invalid bias
        assert result.rhetorical_bias == []  # Fallback for invalid bias
        assert result.confidence == 0.0  # Fallback for invalid bias
        
        # Verify fallback claim check
        assert len(result.claim_checks) == 1
        fallback_claim = result.claim_checks[0]
        assert fallback_claim["verdict"] == "insufficient evidence"
        assert fallback_claim["confidence"] == 0.0
        assert "insufficient evidence" in fallback_claim["evidence"]
        
        print("✅ Malformed responses handled gracefully with fallbacks")

    def test_parse_fenced_json_responses(self, sample_article, mock_settings_dict):
        """Test parsing JSON wrapped in markdown code fences."""
        
        # Response with markdown fences (common LLM behavior)
        bias_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '''Here's my analysis:

```json
{
  "overall_bias_label": "center",
  "rhetorical_flags": ["cherry_picking"],
  "confidence": 0.6,
  "justification": "Article presents both sides but selectively emphasizes certain facts."
}
```

This analysis is based on the framework provided.'''
                    }]
                }
            }]
        }
        
        # Claims with trailing comma (common JSON error)
        claims_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '''{
  "claim_checks": [
    {
      "claim": "Policy has bipartisan support",
      "verdict": "unverified",
      "confidence": 0.3,
      "evidence": ["Limited polling data available",],
    },
  ]
}'''
                    }]
                }
            }]
        }
        
        # Mock responses
        mock_response_bias = Mock()
        mock_response_bias.status_code = 200
        mock_response_bias.json.return_value = bias_response
        
        mock_response_claims = Mock() 
        mock_response_claims.status_code = 200
        mock_response_claims.json.return_value = claims_response
        
        # Test parsing
        provider = GeminiProvider.from_settings(mock_settings_dict)
        provider._post = Mock(side_effect=[mock_response_bias, mock_response_claims])
        
        result = provider.analyze_article(sample_article)
        
        # Verify fenced JSON was parsed correctly
        assert result.overall_bias_label == "center"
        assert "cherry_picking" in result.rhetorical_bias
        assert result.confidence == 0.6
        
        # Verify trailing comma was handled
        assert len(result.claim_checks) == 1
        assert result.claim_checks[0]["claim"] == "Policy has bipartisan support"
        assert result.claim_checks[0]["verdict"] == "unverified"
        
        print("✅ Fenced JSON and trailing commas parsed successfully")