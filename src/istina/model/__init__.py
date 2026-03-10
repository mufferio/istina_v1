"""
Model package (domain + core business rules).

Purpose:
- Contains domain entities, domain operations, and abstractions.
- Must NOT depend on CLI/UI (view/controller).
- Should be stable even if you replace the CLI with a web API.

Subpackages:
- entities: pure domain data structures (Article, Conflict, BiasScore)
- repositories: persistence interfaces + implementations
- providers: AI provider interfaces + implementations (Factory lives here)
- visitors: visitor pattern operations over entities
- adapters: external input sources (e.g., RSS ingestion)
"""
