#!/usr/bin/env bash
# Installation de TarDrop sur AlmaLinux 9.
#   ./deploy/install.sh                      # installe tout, y compris la conf Apache en conf.d/
#   TARDROP_SKIP_APACHE=1 ./deploy/install.sh
#                                            # n'installe PAS tardrop.conf dans conf.d/
#                                            # (vous intégrez le bloc de deploy/tardrop.conf
#                                            #  dans votre vhost HTTPS + PAM existant)
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Exécuter en root." >&2
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="${TARDROP_SCRIPT_PATH:-/opt/tardrop/detect.sh}"

echo "## Paquets"
dnf install -y httpd python3 python3-pip mod_ssl

echo "## Service et répertoires"
useradd --system --home /opt/tardrop --shell /sbin/nologin tardrop 2>/dev/null || true
mkdir -p /opt/tardrop /var/lib/tardrop/jobs
rsync -a --delete "$PROJECT_DIR"/ /opt/tardrop/app/ --exclude deploy --exclude examples
rm -rf /opt/tardrop/app/.git
chown -R tardrop:tardrop /opt/tardrop /var/lib/tardrop

echo "## Environnement virtuel Python"
python3 -m venv /opt/tardrop/venv
/opt/tardrop/venv/bin/pip install --upgrade pip
/opt/tardrop/venv/bin/pip install -r /opt/tardrop/app/requirements.txt

if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "## Installation du script d'exemple (à remplacer par le vôtre) : $SCRIPT_PATH"
    install -m 0755 -o tardrop -g tardrop "$PROJECT_DIR/examples/detect.sh" "$SCRIPT_PATH"
fi
chown tardrop:tardrop "$(dirname "$SCRIPT_PATH")" 2>/dev/null || true

echo "## Service systemd"
install -m 0644 "$PROJECT_DIR/deploy/tardrop.service" /etc/systemd/system/tardrop.service
systemctl daemon-reload
systemctl enable --now tardrop

# Autorise Apache à joindre gunicorn sur 127.0.0.1:8000 (SELinux)
setsebool -P httpd_can_network_connect 1 2>/dev/null || true

if [[ "${TARDROP_SKIP_APACHE:-0}" == "1" ]]; then
    echo "## Apache : conf.d/ volontairement non modifié (TARDROP_SKIP_APACHE=1)"
    echo "   Intégrez le bloc MODE 1 de deploy/tardrop.conf dans votre vhost HTTPS"
    echo "   (auth PAM déjà en place), puis : apachectl configtest && systemctl reload httpd"
else
    echo "## Apache (vhost autonome conf.d/tardrop.conf)"
    install -m 0644 "$PROJECT_DIR/deploy/tardrop.conf" /etc/httpd/conf.d/tardrop.conf
    sed -i "s/tardrop.example.com/$(hostname -f)/g" /etc/httpd/conf.d/tardrop.conf
fi

httpd -t
systemctl enable --now httpd
systemctl reload httpd

if [[ "${TARDROP_SKIP_APACHE:-0}" == "1" ]]; then
    echo "Terminé. Le service TarDrop écoute sur 127.0.0.1:8000 (préfixe /tardrop)."
    echo "Vérifiez ensuite : https://<votre-serveur>/tardrop/ (authentification PAM demandée)."
else
    echo "Terminé. Interface : https://$(hostname -f)/tardrop/"
fi
