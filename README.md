# TarDrop — webapp Flask de traitement d'archives tar

Webapp minimaliste qui permet de :

1. **envoyer** une archive tar (`.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`) ;
2. **déclencher** un script bash sur cette archive (l'archive est passée en `$1`) ;
3. **télécharger** le fichier produit par le script.

Chaque envoi crée un *job* : suivi de l'état en direct, journal du script consultable,
téléchargement du résultat. Les jobs et leurs fichiers restent dans `/var/lib/tardrop/jobs/`.
Si Apache transmet l'en-tête `X-Remote-User` (authentification PAM/LDAP), l'utilisateur
qui lance chaque job est tracé et affiché.

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

### Cas A — intégration à votre vhost HTTPS + PAM existant (recommandé)

```bash
git clone https://github.com/JFA083/webapp.git
cd webapp
TARDROP_SKIP_APACHE=1 sudo -E ./deploy/install.sh
```

L'installation ne touche alors pas à `/etc/httpd/conf.d/` : elle installe le service
`systemd` (`127.0.0.1:8000`, préfixe `/tardrop`), le venv Python et les répertoires.
Puis, **dans votre vhost `*:443` existant** (celui qui a déjà `AuthBasicProvider PAM`
et `AuthPAMService httpd`), ajoutez le bloc « MODE 1 » de `deploy/tardrop.conf` :

```apache
<Location "">
    AuthType Basic
    AuthName "TarDrop"
    AuthBasicProvider PAM
    AuthPAMService httpd
    Require valid-user
</Location>
RequestHeader set X-Remote-User "%{REMOTE_USER}s" env=REMOTE_USER
LimitRequestBody 536870912
ProxyPass        /tardrop http://127.0.0.1:8000/tardrop
ProxyPassReverse /tardrop http://127.0.0.1:8000/tardrop
```

```bash
apachectl configtest && systemctl reload httpd
```

Interface : `https://<votre-serveur>/tardrop/`

### Cas B — vhost autonome génér automatiquement

```bash
sudo ./deploy/install.sh
```

Sans `TARDROP_SKIP_APACHE`, le script déploie aussi `conf.d/tardrop.conf` (vhost HTTPS
en exemple à adapter, même mécanisme PAM, `LimitRequestBody` aligné) et ajuste SELinux
(`httpd_can_network_connect`) et firewalld.

### Votre script personnalisé

```bash
sudo install -m 0755 -o tardrop -g tardrop mon-script.sh /opt/tardrop/detect.sh
sudo systemctl restart tardrop
```

### HTTPS avec Let's Encrypt (cas B)

```bash
sudo dnf install -y certbot python3-certbot-apache
sudo certbot --apache -d <votre-nom-d-hote>
```

### Variables d'environnement (dans `deploy/tardrop.service`)

| Variable                | Défaut                  | Rôle                                            |
|-------------------------|-------------------------|-------------------------------------------------|
| `TARDROP_SCRIPT`        | `/opt/tardrop/detect.sh`| Script bash à exécuter                          |
| `TARDROP_BASE`          | `/var/lib/tardrop`      | Répertoire des jobs                             |
| `TARDROP_TIMEOUT`       | `900`                   | Délai max du script (secondes)                  |
| `TARDROP_MAX_MB`        | `512`                   | Taille max de l'archive envoyée (Mo)            |
| `TARDROP_MAX_RESULT_MB` | `2048`                  | Taille max du fichier résultat (Mo)             |
| `TARDROP_PREFIX`        | `/tardrop`              | Préfixe d'URL derrière un vhost existant (`/` pour un vhost dédié) |

Après modification : `sudo systemctl daemon-reload && sudo systemctl restart tardrop`.

## Sécurité

- Apache est le point d'entrée et applique l'authentification (PAM) et le TLS ;
  gunicorn n'écoute que sur `127.0.0.1:8000`, donc `X-Remote-User` ne peut être
  falsifié que depuis la machine elle-même.
- Le nom de fichier envoyé est neutralisé (basename) et le contenu est vérifié
  (archive tar réelle). Le script s'exécute sous l'utilisateur non privilégié `tardrop`
  (`NoNewPrivileges`, `PrivateTmp`).
- Ajustez `LimitRequestBody` côté Apache si `TARDROP_MAX_MB` change.
- `restart tardrop` reprend la liste des jobs existants (métadonnées sur disque).
