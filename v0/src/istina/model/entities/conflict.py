"""
Conflict entity.

Represents:
- A conflict “topic” or tracked event (e.g., a war, dispute, crisis).
- Articles may be associated to a Conflict (manually or by clustering later).

Typical fields:
- id
- name/title (e.g., "Israel–Gaza War")
- description (optional)
- tags/keywords (optional; used for matching)
- created_at / updated_at

Used by:
- Later versions: clustering, tagging, timeline views
- Repositories: store conflicts and query related articles
"""
