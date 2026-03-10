"""
Gemini provider tests.

Goal:
- Test parsing/normalization logic without calling real Gemini.
- Use mocked HTTP responses or monkeypatch the SDK call.
- Verify:
  - malformed outputs handled safely
  - normalized BiasScore fields are populated correctly
"""
