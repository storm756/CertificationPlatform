#!/usr/bin/env bash
# One-time server hardening for Ubuntu 24.04. Run as root, once:
#
#   sudo DEPLOY_SSH_PUBKEY="ssh-ed25519 AAAA... you@laptop" bash bootstrap.sh
#
# Does: non-root `deploy` user (key only) · SSH keys only, root login off, passwords off ·
#       ufw 22/80/443 · fail2ban · unattended-upgrades · Docker Engine + compose plugin.
# Safe to re-run. IMPORTANT: keep your current SSH session open and test a NEW login as
# `deploy` before closing it.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
: "${DEPLOY_SSH_PUBKEY:?set DEPLOY_SSH_PUBKEY to the public key that may log in as deploy}"
case "$DEPLOY_SSH_PUBKEY" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*) ;;
  *) echo "DEPLOY_SSH_PUBKEY does not look like an SSH public key" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg ufw fail2ban unattended-upgrades git

echo "==> deploy user"
if ! id deploy >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" deploy
fi
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
grep -qxF "$DEPLOY_SSH_PUBKEY" /home/deploy/.ssh/authorized_keys \
  || echo "$DEPLOY_SSH_PUBKEY" >> /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys

echo "==> Docker Engine"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker deploy # note: docker group is root-equivalent; deploy is the only member
install -d -o deploy -g deploy /srv/csfr /srv/csfr/staging /srv/csfr/prod

echo "==> SSH hardening"
# 00- sorts first, and sshd uses the first value it sees, so this beats cloud-init's 50-cloud-init.conf.
cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'SSHD'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
AllowUsers deploy
SSHD
sshd -t
systemctl reload ssh

echo "==> firewall (ufw)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp # HTTP/3
ufw --force enable

echo "==> fail2ban"
cat > /etc/fail2ban/jail.d/sshd.local <<'F2B'
[sshd]
enabled = true
maxretry = 4
findtime = 10m
bantime = 1h
F2B
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> unattended-upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT
systemctl enable --now unattended-upgrades

echo
echo "Done. Now, from your laptop and BEFORE closing this session:"
echo "  ssh deploy@$(hostname -I | awk '{print $1}')    # must work"
echo "  ssh root@$(hostname -I | awk '{print $1}')      # must be refused"
