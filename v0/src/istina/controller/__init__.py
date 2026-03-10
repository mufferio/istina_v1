"""
Controller layer (CLI orchestration).

Purpose:
- Glue between CLI commands (user intent) and application services (use cases).
- Parse arguments, call services, pass results to views.

Key rule:
- Controller should not contain domain logic; it coordinates.
"""
