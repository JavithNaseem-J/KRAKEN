# configurable-cors Specification

## Purpose
Environment-configurable CORS allowed origins for gateway and approval services.

## Requirements

### Requirement: CORS origins configurable via environment
The system SHALL read CORS allowed origins from `Settings.cors_allowed_origins` (comma-separated string, default `"http://localhost:5173,http://localhost:3000"`). Both the gateway and approval service SHALL use this setting for their `CORSMiddleware` `allow_origins` parameter instead of hardcoded lists.

#### Scenario: Default localhost origins
- **WHEN** no `CORS_ALLOWED_ORIGINS` env var is set
- **THEN** gateway and approval accept requests from `http://localhost:5173` and `http://localhost:3000`

#### Scenario: Production origins configured
- **WHEN** `CORS_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com` is set
- **THEN** gateway and approval accept requests only from those two origins

#### Scenario: Preflight request from allowed origin
- **WHEN** a browser sends an OPTIONS preflight from a configured origin
- **THEN** the CORS middleware responds with appropriate `Access-Control-Allow-Origin` headers
