#!/usr/bin/env bash
# Instalarea inițială a unui VPS curat (Ubuntu 22.04+/Debian 12+). Se rulează O SINGURĂ DATĂ, ca root:
#   AMA_ADMIN_SSH_PUBKEY="ssh-ed25519 AAAA… tu@laptop" bash bootstrap.sh
# Idempotent: se poate relua fără efecte. După el, totul rulează fără sudo, sub utilizatorul `ama`, în Docker fără root.
#
# Ce face: Docker din depozitul oficial (cu amprenta cheii verificată), utilizator `ama` fără drepturi de
# administrator cu Docker fără root, firewall (doar 22, 80, 443), SSH doar cu cheie, actualizări de securitate
# automate, structura de directoare din /srv/ama cu drepturi restrânse.
# NEVERIFICAT: scriptul nu a putut fi rulat pe un VPS real (D-001); este verificat doar cu shellcheck.
set -euo pipefail

AMA_USER="${AMA_USER:-ama}"
AMA_HOME_DIR="${AMA_HOME_DIR:-/srv/ama}"
AMA_REPO_URL="${AMA_REPO_URL:-}"            # opțional: depozitul de clonat în $AMA_HOME_DIR/repo
AMA_ADMIN_SSH_PUBKEY="${AMA_ADMIN_SSH_PUBKEY:-}"
# Amprenta cheii GPG a depozitului Docker (https://docs.docker.com/engine/install/ubuntu/)
DOCKER_GPG_FPR="9DC858229FC7DD38854AE2D88D81803C0EBFCD88"  # pragma: allowlist secret

log() { printf '\n== %s\n' "$*"; }
die() { printf 'EROARE: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "rulează ca root"
[ -r /etc/os-release ] || die "sistem necunoscut"
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in ubuntu | debian) ;; *) die "doar Ubuntu sau Debian (găsit: ${ID:-?})" ;; esac

# --- 0. Verificare anti-blocare: fără cheie SSH nu se închide autentificarea cu parolă ---------------------
has_root_key() { [ -s /root/.ssh/authorized_keys ]; }
if [ -z "$AMA_ADMIN_SSH_PUBKEY" ] && ! has_root_key; then
  die "nicio cheie SSH disponibilă: setează AMA_ADMIN_SSH_PUBKEY sau pune o cheie în /root/.ssh/authorized_keys"
fi

# --- 1. Pachete ----------------------------------------------------------------------------------------------
log "Pachete de bază"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg git ufw unattended-upgrades apt-listchanges \
  uidmap dbus-user-session slirp4netns openssh-server

log "Docker (depozit oficial)"
install -m 0755 -d /etc/apt/keyrings
if [ ! -s /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
fi
actual_fpr="$(gpg --show-keys --with-colons /etc/apt/keyrings/docker.asc | awk -F: '/^fpr/ {print $10; exit}')"
[ "$actual_fpr" = "$DOCKER_GPG_FPR" ] || { rm -f /etc/apt/keyrings/docker.asc; die "amprenta cheii Docker nu se potrivește ($actual_fpr)"; }
chmod a+r /etc/apt/keyrings/docker.asc
arch="$(dpkg --print-architecture)"
echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
  >/etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y --no-install-recommends \
  docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin docker-ce-rootless-extras
# Demonul cu drepturi de root nu e folosit: platforma rulează doar în Docker fără root.
systemctl disable --now docker.service docker.socket 2>/dev/null || true

# --- 2. Utilizatorul fără drepturi de administrator ---------------------------------------------------------
log "Utilizator ${AMA_USER}"
if ! id "$AMA_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$AMA_USER"
fi
# Fără sudo și fără grupul docker (acesta ar fi echivalent cu root)
for g in sudo docker adm; do
  if id -nG "$AMA_USER" | tr ' ' '\n' | grep -qx "$g"; then gpasswd -d "$AMA_USER" "$g"; fi
done
passwd -l "$AMA_USER" >/dev/null
grep -q "^${AMA_USER}:" /etc/subuid || usermod --add-subuids 100000-165535 "$AMA_USER"
grep -q "^${AMA_USER}:" /etc/subgid || usermod --add-subgids 100000-165535 "$AMA_USER"
loginctl enable-linger "$AMA_USER"   # serviciile utilizatorului pornesc la boot, fără sesiune

# Porturile 80/443 pentru Docker fără root (altfel utilizatorul fără drepturi nu poate publica pe ele)
cat >/etc/sysctl.d/99-ama.conf <<'SYSCTL'
net.ipv4.ip_unprivileged_port_start=80
SYSCTL
sysctl --system >/dev/null

AMA_UID="$(id -u "$AMA_USER")"
systemctl start "user@${AMA_UID}.service"
as_ama() {
  runuser -u "$AMA_USER" -- env "XDG_RUNTIME_DIR=/run/user/${AMA_UID}" \
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${AMA_UID}/bus" "$@"
}
if [ ! -S "/run/user/${AMA_UID}/docker.sock" ]; then
  log "Docker fără root pentru ${AMA_USER}"
  as_ama dockerd-rootless-setuptool.sh install
  as_ama systemctl --user enable --now docker.service
fi

# --- 3. Directoare și drepturi -------------------------------------------------------------------------------
log "Directoare în ${AMA_HOME_DIR}"
install -d -m 0755 -o "$AMA_USER" -g "$AMA_USER" "$AMA_HOME_DIR"
install -d -m 0755 -o "$AMA_USER" -g "$AMA_USER" "$AMA_HOME_DIR/repo"
# Secretele: doar utilizatorul ama le citește; în afara repo-ului
install -d -m 0700 -o "$AMA_USER" -g "$AMA_USER" "$AMA_HOME_DIR/env" "$AMA_HOME_DIR/env/backup" "$AMA_HOME_DIR/env/docker"
if [ -n "$AMA_REPO_URL" ] && [ ! -d "$AMA_HOME_DIR/repo/.git" ]; then
  as_ama git clone "$AMA_REPO_URL" "$AMA_HOME_DIR/repo"
fi

# --- 4. Chei SSH ---------------------------------------------------------------------------------------------
if [ -n "$AMA_ADMIN_SSH_PUBKEY" ]; then
  log "Chei SSH"
  for u in root "$AMA_USER"; do
    home="$(getent passwd "$u" | cut -d: -f6)"
    install -d -m 0700 -o "$u" -g "$(id -gn "$u")" "$home/.ssh"
    touch "$home/.ssh/authorized_keys"
    grep -qxF "$AMA_ADMIN_SSH_PUBKEY" "$home/.ssh/authorized_keys" || echo "$AMA_ADMIN_SSH_PUBKEY" >>"$home/.ssh/authorized_keys"
    chmod 600 "$home/.ssh/authorized_keys"
    chown "$u:$(id -gn "$u")" "$home/.ssh/authorized_keys"
  done
fi

# --- 5. SSH doar cu cheie ------------------------------------------------------------------------------------
log "SSH doar cu cheie"
install -d -m 0755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/10-ama.conf <<'SSHD'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 3
SSHD
sshd -t || die "configurația sshd nu e validă"
systemctl reload ssh 2>/dev/null || systemctl reload sshd

# --- 6. Firewall: doar 22, 80, 443 ---------------------------------------------------------------------------
log "Firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp   # HTTP/3 (același port 443)
ufw --force enable

# --- 7. Actualizări de securitate automate -------------------------------------------------------------------
log "Actualizări automate"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT
cat >/etc/apt/apt.conf.d/52ama-unattended <<'APT'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "05:30";
APT

log "Gata"
cat <<MSG
Pasul următor (ca ${AMA_USER}): vezi docs/runbooks/instalare-vps.md, de la secțiunea Fișierele de mediu.
  ssh ${AMA_USER}@<ip-server>
  export DOCKER_HOST=unix:///run/user/${AMA_UID}/docker.sock
MSG
