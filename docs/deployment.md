# Cloud-Native Deployment Guide

This guide details how to deploy the KRAKEN system across Netlify (React Frontend) and Cloud VPS (Single Consolidated Backend App) or Render.com.

---

## 1. Cloud VPS Setup (Consolidated Application)

1. Provision an **Ubuntu Compute Instance** (Ubuntu 22.04 or 24.04 LTS).
2. SSH into the instance and setup the environment:
   ```bash
   chmod +x scripts/setup_oracle_vps.sh
   ./scripts/setup_oracle_vps.sh
   ```
3. Create the `.env` file containing required production environment variables:
   - `POSTGRES_URL` / `POSTGRES_SYNC_URL` (cloud-managed PostgreSQL with pgvector)
   - `REDIS_URL` (cloud Redis instance)
   - `QDRANT_URL` & `QDRANT_API_KEY` (Qdrant Cloud vector database)
   - `LLM_API_KEY` (Groq or OpenAI-compatible API key)
   - `HITL_SERVICE_TOKEN` (>= 32 character secret token)
   - `GATEWAY_API_KEYS` (API keys for client access)

---

## 2. GitHub Actions Deployment

Add the following repository secrets under **Settings → Secrets and variables → Actions**:

| Secret Name | Description | Example |
|---|---|---|
| `ORACLE_SERVER_IP` | Public IP address of the Cloud VPS | `129.146.xxx.xxx` |
| `ORACLE_SSH_PRIVATE_KEY` | OpenSSH Private Key corresponding to the VPS user | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

Upon every `git push` to `main`, `.github/workflows/deploy.yml` SSHs into the VPS, pulls the latest code, and builds/restarts the consolidated single-container application via `docker-compose.prod.yml`.

---

## 3. Frontend Deployment (Netlify or Static Web Host)

1. Connect your GitHub repository to **Netlify**.
2. Netlify detects [`netlify.toml`](../netlify.toml) automatically:
   - **Base directory:** `frontend-react`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend-react/dist`
3. Configure Environment Variables in Netlify Dashboard:
   - `VITE_API_URL`: `http://<YOUR_SERVER_IP>:8000` (or your custom API domain)
   - `VITE_APPROVAL_URL`: `http://<YOUR_SERVER_IP>:8000` (approval routes are exposed via the Gateway)
