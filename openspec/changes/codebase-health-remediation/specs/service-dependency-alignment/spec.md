## ADDED Requirements

### Requirement: Per-service requirements declare all transitive imports
Every service's `requirements.txt` SHALL declare all Python packages that the service transitively imports at module load time. Specifically:
- `services/gateway/requirements.txt`, `services/approval/requirements.txt`, and `services/action/requirements.txt` SHALL include `tenacity`.
- `services/orchestrator/requirements.txt` SHALL include `qdrant-client`.
- `services/knowledge/requirements.txt` and `services/memory/requirements.txt` SHALL include `langchain-openai`.

#### Scenario: Gateway Docker image boots successfully
- **WHEN** the gateway service Docker image is built and started independently (not via `Dockerfile.standalone`)
- **THEN** the service starts without `ModuleNotFoundError` for `tenacity` or any other transitive dependency

#### Scenario: Orchestrator Docker image boots with Qdrant
- **WHEN** the orchestrator service Docker image is built and started independently
- **THEN** `shared.cache` imports `qdrant_client` without `ModuleNotFoundError`

#### Scenario: Knowledge Docker image boots with cloud embeddings
- **WHEN** the knowledge service Docker image is built with `embedding_provider=cloud`
- **THEN** `langchain_openai` is available and `OpenAIEmbeddings` instantiates without `ModuleNotFoundError`
