## Why

Transition KRAKEN from local workstation execution to a 100% Cloud-Native Production Architecture using 100% Free-Forever Cloud Services (Netlify, Oracle Cloud Infrastructure Always-Free VPS, Supabase PostgreSQL, Qdrant Cloud, Upstash Redis, Groq LPU Cloud API, and GitHub Actions CI/CD). This deployment strategy achieves $0.00/month operational costs while providing 24/7/365 zero-downtime uptime, global SSL encryption, and automated continuous deployment on `git push main`.

## What Changes

- **Frontend Deployment Config**: Add Netlify configuration (`netlify.toml` and `public/_redirects`) to host the React SPA on Netlify Free Tier (`https://kraken-agent.netlify.app`) with automatic API proxy rewrites (`/api/*` -> Oracle Cloud VPS).
- **Docker Production Compose**: Create `docker-compose.prod.yml` optimized for Oracle Cloud Always-Free ARM VPS (`VM.Standard.A1.Flex`, 24GB RAM, 4 vCPUs) with production healthchecks and automatic container restarts.
- **Automated CI/CD Workflow**: Add `.github/workflows/deploy.yml` for automated SSH deployment to Oracle Cloud upon pushing code to `main`.
- **Environment & CORS Hardening**: Configure production CORS origins and service tokens for public Cloud DNS resolution.

## Capabilities

### New Capabilities
- `cloud-deployment`: Enables zero-cost 100% Cloud-Native infrastructure deployment via Netlify, Oracle Cloud VPS, and GitHub Actions CI/CD.

### Modified Capabilities
- None.

## Impact

- **Affected Code**: `frontend-react/public/_redirects`, `netlify.toml`, `docker-compose.prod.yml`, `.github/workflows/deploy.yml`, `shared/config.py`.
- **APIs**: Unchanged endpoints; all public API routes accessible via `https://kraken-agent.netlify.app/api/*`.
- **Dependencies**: Adds GitHub Actions SSH action (`appleboy/ssh-action`) and Netlify CLI config.
