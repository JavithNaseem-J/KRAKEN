## Context

KRAKEN is currently running as 7 local FastAPI microservices and a Vite/React frontend on developer workstations, accessing cloud databases (Supabase, Qdrant, Upstash, Groq, Langfuse). Deploying to 100% Cloud requires hosting the React UI on a global CDN and hosting the 7 microservices on an always-on 24/7 cloud server without incurring monthly charges.

## Goals / Non-Goals

**Goals:**
- Deploy React 18 SPA to Netlify Free Tier (`https://kraken-agent.netlify.app`).
- Deploy all 7 microservices using `docker-compose.prod.yml` to Oracle Cloud Always-Free ARM VPS (4 vCPUs, 24 GB RAM, 200 GB disk).
- Configure Netlify API proxy redirects (`/api/*` -> Oracle VPS IP `:8000`) to eliminate CORS issues and secure all API calls under Netlify's HTTPS SSL certificate.
- Automate continuous deployment via GitHub Actions SSH pipeline on `git push main`.

**Non-Goals:**
- Paying any cloud provider fees (100% Free Forever stack).
- Rewriting microservices into AWS Lambda serverless functions (Docker Compose on Oracle Cloud retains exact architecture).

## Decisions

### Decision 1: Netlify CDN for Frontend + Oracle VPS for Backend
- **Choice**: Host React UI on Netlify and Backend on Oracle Cloud Always-Free ARM Instance (`VM.Standard.A1.Flex`).
- **Rationale**: Oracle Cloud provides 24 GB RAM for 0 cost (unlike Render 512MB free tier), ensuring zero container sleeping and instant 24/7 responsiveness.

### Decision 2: Netlify Proxy Rewrites for Zero-CORS API Access
- **Choice**: Use `public/_redirects`: `/api/* http://<ORACLE_IP>:8000/:splat 200!`
- **Rationale**: Browser traffic only talks to HTTPS Netlify. Netlify proxies requests to Oracle Cloud on port 8000 behind the scenes, completely avoiding browser CORS blockages and SSL setup on raw IP addresses.

### Decision 3: Automated SSH CI/CD via GitHub Actions
- **Choice**: `.github/workflows/deploy.yml` uses `appleboy/ssh-action` to connect to Oracle Cloud and execute `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
- **Rationale**: Eliminates manual server logins; pushing code to GitHub automatically deploys changes to live cloud infrastructure.

## Risks / Trade-offs

- **[Risk] Oracle Cloud free instance availability during region registration** → **Mitigation**: Use automated availability script or select alternate region if ARM capacity is temporarily full.
- **[Risk] Network latency between Netlify CDN and Oracle Cloud** → **Mitigation**: Select Oracle Cloud data center in the same geographic region as primary users (e.g. AWS/OCI Singapore or US-East).
