#!/usr/bin/env bash
# ==============================================================================
# One-Command Oracle Cloud VPS Automated Setup Script for AKEA
# ==============================================================================
# Installs Docker, Docker Compose v2, Git, configures iptables firewall rules,
# and prepares the deployment environment on Ubuntu 22.04 / 24.04 LTS.
#
# Usage:
#   chmod +x scripts/setup_oracle_vps.sh
#   ./scripts/setup_oracle_vps.sh
# ==============================================================================

set -euo pipefail

echo "🚀 Starting Oracle Cloud VPS Environment Setup for AKEA..."

# 1. System Updates & Prerequisites
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git iptables-persistent

# 2. Install Docker Official GPG Key & Repository
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --replace-file
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 3. Install Docker Engine & Compose Plugin
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. User Permissions
sudo usermod -aG docker "$USER" || true

# 5. Open Firewall Ports (Oracle Cloud IPTables rules)
echo "🔥 Opening Firewall Ports (8000 for Gateway, 8004 for Approval)..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8004 -j ACCEPT || true
sudo netfilter-persistent save || true

echo "✅ Setup Complete! Log out and back in for Docker group permissions to take effect."
