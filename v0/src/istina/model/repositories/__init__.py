"""
Repositories (persistence layer).

Purpose:
- Provide a stable interface to store and retrieve domain entities.
- The domain/services depend on repository interfaces, not concrete storage.

Implementations:
- memory_repository.py: in-memory for fast dev/tests
- file_repository.py: JSONL/JSON persistence for CLI v0

Design goal:
- Swap persistence later (SQLite/Postgres) without changing services.
"""
