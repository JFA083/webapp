#!/usr/bin/env bash
# Installation de TarDrop sur AlmaLinux 9.
# À exécuter en root :  ./deploy/install.sh  depuis la racine du projet.
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
mkdir -p /opt/tardrop /var/lib/tardrop/jobs /etc/httpd/conf.d
cp -a "$PROJECT_DIR/app.py" "$PROJECT_DIR/wsgi.py" "$PROJECT_DIR/templates" /opt/tardrop/app/ 2>/dev/null || true
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

echo "## Apache"
install -m 0644 "$PROJECT_DIR/deploy/tardrop.conf" /etc/httpd/conf.d/tardrop.conf
# Autorise Apache à joindre gunicorn sur 127.0.0.1:8000 (SELinux)
setsebool -P httpd_can_network_connect 1 2>/dev/null || true
sed -i "s/tardrop.example.com/$(hostname -f)/g" /etc/httpd/conf.d/tardrop.conf
httpd -t
systemctl enable --now httpd
systemctl reload httpd

if firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --reload
fi

echo
echo "Terminé. Interface : http://$(hostname -f)/"
echo "Remplacez votre script bash dans $SCRIPT_PATH (l'archive est passée en \$1,"
echo "le fichier résultat doit être écrit dans \$TARDROP_RESULT_FILE)."
