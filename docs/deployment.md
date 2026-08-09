# Cloud-Native Deployment Guide

This guide details how to deploy the AKEA system across Netlify (React Frontend) and Oracle Cloud VPS (Backend Microservices).

---

## 1. Oracle Cloud VPS Setup (Backend Microservices)

1. Provision an **Oracle Cloud Infrastructure (OCI) Compute Instance** (Ubuntu 22.04 or 24.04 LTS).
2. SSH into the instance and run the one-command setup script:
   ```bash
   chmod +x scripts/setup_oracle_vps.sh
   ./scripts/setup_oracle_vps.sh
   ```
3. Create the `/home/ubuntu/Autonomous-Knowledge-Execution-Agent/.env` file containing required production environment variables (`POSTGRES_URL`, `REDIS_URL`, `QDRANT_URL`, `LLM_API_KEY`, `HITL_SERVICE_TOKEN`, `GATEWAY_API_KEYS`).

---

## 2. GitHub Actions Deployment Secrets

Add the following repository secrets under **Settings → Secrets and variables → Actions**:

| Secret Name | Description | Example |
|---|---|---|
| `ORACLE_SERVER_IP` | Public IP address of the Oracle Cloud VPS | `129.146.xxx.xxx` |
| `ORACLE_SSH_PRIVATE_KEY` | OpenSSH Private Key corresponding to the VPS `ubuntu` user | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

Upon every `git push` to `main`, `.github/workflows/deploy.yml` SSHs into the Oracle VPS, pulls the latest code, and builds/restarts the multi-container stack via `docker-compose.prod.yml`.

---

## 3. Netlify Setup (React Frontend)

1. Connect your GitHub repository to **Netlify**.
2. Netlify detects [`netlify.toml`](../netlify.toml) automatically:
   - **Base directory:** `frontend-react`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend-react/dist`
3. Configure Environment Variables in Netlify Dashboard:
   - `VITE_API_URL`: `http://<YOUR_ORACLE_SERVER_IP>:8000` (or custom domain if configured).
