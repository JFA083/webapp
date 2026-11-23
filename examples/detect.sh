#!/usr/bin/env bash
# Exemple de script compatible TarDrop.
#   $1 = chemin de l'archive tar envoyée
# Le répertoire courant est celui du job.
# Le fichier résultat doit être écrit à $TARDROP_RESULT_FILE.
set -euo pipefail

archive="$1"
report="${TARDROP_RESULT_FILE:?La variable TARDROP_RESULT_FILE doit définir le fichier de sortie}"

{
    echo "Rapport TarDrop — $(date -Is)"
    echo "Archive : $archive"
    echo
    echo "## Contenu de l'archive"
    tar -tf "$archive"
} > "$report"
