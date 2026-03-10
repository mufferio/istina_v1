"""
AI providers (analysis integrations).

Purpose:
- Provide a uniform interface for “analyze article -> BiasScore”.
- Hide vendor SDK differences behind base_provider.py.

Implementations:
- mock_provider.py: deterministic fake outputs for tests/dev
- gemini_provider.py: real integration with Google Gemini

Factory:
- provider_factory.py chooses provider based on settings/env.
"""
