# vector-dimension-unification Specification

## Purpose
TBD - created by archiving change codebase-health-remediation. Update Purpose after archive.
## Requirements
### Requirement: Embedding dimension is single-sourced from configuration
`Settings` in `shared/config.py` SHALL expose an `embedding_dim: int` field whose default is derived from `embedding_model` (1536 for models containing `3-small` or `ada`, 384 otherwise). All collection creation calls (`SemanticCache.init()`, knowledge `ensure_collection()`, and `init.sql` DDL) SHALL use this configured dimension value instead of a hardcoded literal.

#### Scenario: Cloud provider with text-embedding-3-small
- **WHEN** `embedding_provider=cloud` and `embedding_model=text-embedding-3-small`
- **THEN** `embedding_dim` defaults to 1536 and all Qdrant collections and Postgres vector columns are created with dimension 1536

#### Scenario: Local provider with bge-small-en
- **WHEN** `embedding_provider=local` and `embedding_model=BAAI/bge-small-en-v1.5`
- **THEN** `embedding_dim` defaults to 384 and all vector stores use dimension 384

#### Scenario: Dimension mismatch detection
- **WHEN** an existing Qdrant collection has dimension 384 but `embedding_dim` is configured as 1536
- **THEN** the service logs an error at startup identifying the mismatch and the collection is NOT silently used with wrong dimensions

