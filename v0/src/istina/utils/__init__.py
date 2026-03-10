"""
Utilities / infrastructure helpers.

Purpose:
- Cross-cutting concerns:
  - logging
  - retries
  - rate limiting
  - error normalization

Rule:
- Utilities must not import controller/view; keep dependencies one-way.
"""
