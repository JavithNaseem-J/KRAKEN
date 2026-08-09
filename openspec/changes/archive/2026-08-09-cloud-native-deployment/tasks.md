## 1. Netlify Frontend Configuration

- [x] 1.1 Create `frontend-react/public/_redirects` with Netlify proxy rules (`/api/* http://<ORACLE_IP>:8000/:splat 200!`).
- [x] 1.2 Create `netlify.toml` in project root configuring build command (`npm run build`) and publish directory (`frontend-react/dist`).
- [x] 1.3 Update API base URL handling in `frontend-react/src/services/api.ts` to support relative `/api` paths in production.

## 2. Production Docker & Server Config

- [x] 2.1 Create `docker-compose.prod.yml` mapping ports, environment variables, restart policies (`restart: unless-stopped`), and healthchecks.
- [x] 2.2 Create `scripts/setup_oracle_vps.sh` for one-command automated installation of Docker, Docker Compose, Git, and firewall port forwarding on Oracle Cloud Ubuntu VPS.

## 3. GitHub Actions Continuous Deployment Pipeline

- [x] 3.1 Create `.github/workflows/deploy.yml` with SSH deployment action (`appleboy/ssh-action`) triggered on push to `main`.
- [x] 3.2 Document required GitHub Repository Secrets (`ORACLE_SERVER_IP`, `ORACLE_SSH_PRIVATE_KEY`).

## 4. End-to-End Cloud Deployment Verification

- [x] 4.1 Verify Netlify build success and production API proxy routing.
- [x] 4.2 Verify 24/7 multi-service health status on Oracle Cloud VPS.
