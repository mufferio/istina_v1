# Istina v1

> Conflict-tracking and bias-aware news platform — web application built on the Istina v0 CLI engine.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · Pydantic v2 |
| Database | Supabase (Postgres + Auth + Storage) |
| Frontend | React · TypeScript · Vite · TailwindCSS · Framer Motion |
| Deployment | Docker · Fly.io (backend) · Vercel (frontend) |

## Repository structure

```
istina_v1/
├── v0/          ← Istina v0 CLI source (reference for migration)
├── backend/     ← FastAPI service (Phase 2+)
├── frontend/    ← React application (Phase 5+)
├── supabase/    ← Database migrations and seed data (Phase 4+)
├── docs/        ← Architecture and environment documentation
└── .github/
    └── workflows/  ← CI/CD pipelines (Phase 13)
```

## Quick start (coming soon)

Full setup instructions will be added as each phase is completed.  
Track progress on the [GitHub Project board](https://github.com/users/mufferio/projects/3).

## Issue roadmap

52 issues across 13 phases fully document the development roadmap.  
See [Issues](https://github.com/mufferio/istina_v1/issues) for the complete list.
