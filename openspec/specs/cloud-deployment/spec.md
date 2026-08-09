# cloud-deployment Specification

## Requirements

### Requirement: Netlify Edge API Proxy Rewrites
The frontend deployment SHALL include Netlify proxy redirect rules in `public/_redirects` forwarding all `/api/*` requests to the Oracle Cloud Gateway endpoint with HTTP 200 pass-through.

#### Scenario: Production API Request Proxying
- **WHEN** the browser frontend sends a request to `https://kraken-agent.netlify.app/api/run`
- **THEN** Netlify edge proxies the request directly to the backend Gateway microservice on port 8000 without CORS headers mismatch

### Requirement: Automated SSH Deployment Pipeline
The repository SHALL contain a GitHub Actions workflow `.github/workflows/deploy.yml` that automatically connects to the target cloud server via SSH on `git push main` to pull latest code and rebuild production Docker containers.

#### Scenario: Continuous Integration and Deployment
- **WHEN** a developer pushes code commits to the `main` branch on GitHub
- **THEN** GitHub Actions runs unit tests and executes `docker compose -f docker-compose.prod.yml up -d --build` on Oracle Cloud
