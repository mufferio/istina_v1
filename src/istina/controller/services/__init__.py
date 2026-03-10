"""
Application services (use cases).

Purpose:
- Implements the “business workflows” of the app:
  - ingest articles
  - analyze articles
  - generate reports
- Services coordinate repositories + providers + adapters + visitors.

Key rule:
- Services should be UI-agnostic (usable by CLI now, web later).
"""
