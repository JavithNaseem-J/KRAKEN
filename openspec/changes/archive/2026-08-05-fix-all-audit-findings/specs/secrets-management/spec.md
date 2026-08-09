## MODIFIED Requirements

### Requirement: No live secrets in source control
The repository SHALL NOT contain live API keys, tokens, passwords, or other credentials in any tracked file, including `.env`. Tracked environment template files (e.g., `.env.example`) SHALL contain only placeholders. `.env` files SHALL be listed in `.gitignore`. Real secrets SHALL be sourced exclusively from environment variables injected by the deployment platform or a secrets manager. Any credential that has been committed SHALL be rotated at the provider before this change is considered complete.

#### Scenario: Repository scan finds no live credentials
- **WHEN** the tracked files in the repository are scanned for known secret patterns (e.g., `gsk_` Groq keys, tokens, passwords)
- **THEN** no live credential values are present; only placeholders such as `<your-key-here>` appear

#### Scenario: Leaked key is rotated
- **WHEN** a credential has previously been committed to git history
- **THEN** that credential has been revoked/rotated at the provider and is no longer valid, regardless of its continued presence in history

#### Scenario: .env file is gitignored
- **WHEN** `.env` is created locally in the repository root
- **THEN** git status ignores the `.env` file and prevents accidental staging or committing

## ADDED Requirements

### Requirement: Per-service tokens replace flat single-token model
The inter-service authentication framework SHALL support per-service pair token configuration (e.g., `ORCHESTRATOR_TO_APPROVAL_TOKEN`) rather than relying on a single flat shared token across all services. Each service SHALL validate inbound tokens against its specific expected service caller tokens.

#### Scenario: Inbound service request validated against service-specific token
- **WHEN** a service receives an internal API request with an `X-Service-Token` matching its expected caller token
- **THEN** authentication succeeds and the request is processed
