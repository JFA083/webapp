# TarDrop — webapp Flask de traitement d'archives tar

Webapp minimaliste qui permet de :

1. **envoyer** une archive tar (`.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`) ;
2. **déclencher** un script bash sur cette archive (l'archive est passée en `$1`) ;
3. **télécharger** le fichier produit par le script.

Chaque envoi crée un *job* : suivi de l'état en direct, journal du script consultable,
téléchargement du résultat. Les jobs et leurs fichiers restent dans `/var/lib/tardrop/jobs/`.

## Interface du script

Votre script bash reçoit :

- `$1` : chemin absolu de l'archive envoyée ;
- `$TARDROP_RESULT_FILE` : chemin où écrire le fichier résultat (recommandé) ;
- répertoire courant = le répertoire du job.

```bash
#!/usr/bin/env bash
set -euo pipefail
archive="$1"
result="${TARDROP_RESULT_FILE:?}"

mon-traitement "$archive" --out "$result"
```

Si le script n'utilise pas `TARDROP_RESULT_FILE`, la webapp prend le fichier le plus
récent créé dans le répertoire du job (le journal `job.log` et l'archive sont exclus).

## Installation sur AlmaLinux 9 (Apache + gunicorn)

```bash
sudo ./deploy/install.sh
```

Le script installe `httpd` et `mod_ssl`, crée l'utilisateur système `tardrop`, l'environnement
virtuel, le service `tardrop.service` (gunicorn sur `127.0.0.1:8000`), la configuration Apache
en reverse proxy, active le booléen SELinux `httpd_can_network_connect` et ouvre le pare-feu.
Le vhost est généré avec votre nom d'hôte.

Puis remplacez le script d'exemple par le vôtre :

```bash
sudo install -m 0755 -o tardrop -g tardrop mon-script.sh /opt/tardrop/detect.sh
sudo systemctl restart tardrop
```

### HTTPS

```bash
sudo dnf install -y certbot python3-certbot-apache
sudo certbot --apache -d <votre-nom-d-hote>
```

### Variables d'environnement (dans `deploy/tardrop.service`)

| Variable              | Défaut                | Rôle                                        |
|-----------------------|-----------------------|---------------------------------------------|
| `TARDROP_SCRIPT`      | `/opt/tardrop/detect.sh` | Script bash à exécuter                   |
| `TARDROP_BASE`        | `/var/lib/tardrop`    | Répertoire des jobs                         |
| `TARDROP_TIMEOUT`     | `900`                 | Délai max du script (secondes)              |
| `TARDROP_MAX_MB`      | `512`                 | Taille max de l'archive envoyée (Mo)        |
| `TARDROP_MAX_RESULT_MB` | `2048`              | Taille max du fichier résultat (Mo)         |

Après modification : `sudo systemctl daemon-reload && sudo systemctl restart tardrop`.

## Sécurité

- Apache sert de garde-fou (reverse proxy) ; mettez l'application en HTTPS et,
  si elle est exposée hors d'un réseau de confiance, ajoutez une authentification
  (BasicAuth Apache ou SSO) dans `/etc/httpd/conf.d/tardrop.conf`.
- Le nom de fichier envoyé est neutralisé (basename) et le contenu est vérifié
  (archive tar réelle). Le script s'exécute sous l'utilisateur non privilégié `tardrop`
  (`NoNewPrivileges`, `PrivateTmp`).
- Ajustez `LimitRequestBody` côté Apache si `TARDROP_MAX_MB` change.
