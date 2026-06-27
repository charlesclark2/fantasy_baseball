#!/usr/bin/env bash
# =============================================================================
# INC-16-P1 — EC2 user-data bootstrap (Amazon Linux 2023, arm64 / t4g.medium).
#
# Passed as --user-data to `aws ec2 run-instances` (see provision-ec2.sh). Runs
# ONCE on first boot as root. Prepares the host so the operator only has to:
#   git clone the repo → cp .env.example .env (fill it) → docker compose up -d --build
#
# What it does:
#   * installs Docker + the compose plugin + git
#   * adds a 4 GB swapfile — the root Dockerfile builds PyMC/CatBoost/etc.; on a
#     4 GB box the build (and the occasional weekly PyMC op) can OOM without swap
#   * enables + starts Docker, adds ec2-user to the docker group
# Repo clone + .env + `compose up` stay MANUAL (git auth is operator-specific).
# =============================================================================
set -euxo pipefail

# --- packages ---------------------------------------------------------------
dnf update -y
# cronie: AL2023 minimal ships NO cron → P3 hit `crontab: command not found`. The 4
# host-cron captures (capture.crontab) need it. amazon-ssm-agent is preinstalled on
# AL2023 but we enable it explicitly (P4 retires SSH → SSM is the only shell).
dnf install -y docker git cronie
# compose v2 + buildx plugins. AL2023's `docker` package ships an OLD buildx
# (< 0.17.0), but Compose v2's `--build` requires buildx >= 0.17.0 to drive image
# builds ("compose build requires buildx 0.17.0 or later") — so install a current
# buildx alongside compose into the global cli-plugins dir.
mkdir -p /usr/local/lib/docker/cli-plugins
ARCH=$(uname -m)  # aarch64 on t4g
case "$ARCH" in aarch64) GH_ARCH=arm64 ;; x86_64) GH_ARCH=amd64 ;; *) GH_ARCH="$ARCH" ;; esac
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
curl -fsSL "https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-${GH_ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx

# --- swap (protect the heavy image build / weekly PyMC op from OOM) ----------
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- docker -----------------------------------------------------------------
systemctl enable --now docker
usermod -aG docker ec2-user

# --- cron + SSM + region (INC-16-P5 reproducible-box bootstrap) --------------
systemctl enable --now crond            # host-cron captures (P3); AL2023 minimal has none
systemctl enable --now amazon-ssm-agent # SSM shell (P4 retires SSH); preinstalled on AL2023
# region for any host-level boto3 (the SSM agent + ad-hoc); containers also get it via .env
grep -q '^AWS_DEFAULT_REGION=' /etc/environment || echo 'AWS_DEFAULT_REGION=us-east-1' >> /etc/environment

echo "[cloud-init] INC-16 host ready (docker + cron + ssm + region). Next (as ec2-user):"
echo "  git clone <repo> ~/app && cd ~/app"
echo "  cp services/dagster/aws/.env.example services/dagster/aws/.env  # fill it, chmod 600"
echo "  docker compose -f services/dagster/aws/docker-compose.yml up -d --build"
echo "  crontab services/dagster/aws/capture.crontab   # install the host-cron captures"
