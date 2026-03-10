"""
Pytest configuration and shared fixtures.

Purpose:
- Provide reusable fixtures:
  - settings fixture (test config)
  - memory_repository fixture
  - mock_provider fixture
  - sample articles fixture

Rule:
- Tests should run without .env and without network calls.
"""
