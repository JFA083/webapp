"""TarDrop : upload d'une archive tar, exécution d'un script bash, téléchargement du résultat.

Le script reçoit le chemin de l'archive en premier argument ($1) et s'exécute
dans le répertoire de travail du job. Pour désigner explicitement le fichier
résultat à télécharger, il peut écrire ce fichier à l'emplacement indiqué par
la variable d'environnement TARDROP_RESULT_FILE. Sinon, le fichier le plus
récent créé par le script dans le répertoire du job est utilisé.
"""
import json
import os
import shutil
import subprocess
import tarfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_file, url_for)

BASE_DIR = Path(os.environ.get("TARDROP_BASE", "/var/lib/tardrop"))
JOBS_DIR = BASE_DIR / "jobs"
SCRIPT_PATH = Path(os.environ.get("TARDROP_SCRIPT", "/opt/tardrop/detect.sh"))
TIMEOUT = int(os.environ.get("TARDROP_TIMEOUT", "900"))
MAX_RESULT_MB = int(os.environ.get("TARDROP_MAX_RESULT_MB", "2048"))

ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("TARDROP_MAX_MB", "512")) * 1024 * 1024
app.config["SECRET_KEY"] = os.environ.get("TARDROP_SECRET_KEY", uuid.uuid4().hex)

_jobs = {}
_jobs_lock = threading.Lock()


def _load_jobs():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for meta_file in JOBS_DIR.glob("*/meta.json"):
        try:
            with meta_file.open() as fh:
                job = json.load(fh)
            _jobs[job["id"]] = job
        except Exception:
            continue


def _save_job(job):
    with (_jobs_dir(job["id"]) / "meta.json").open("w") as fh:
        json.dump(job, fh)


def _jobs_dir(job_id):
    return JOBS_DIR / job_id


def _new_job(archive_name):
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    job_dir = _jobs_dir(job_id)
    job_dir.mkdir(parents=True)
    job = {
        "id": job_id,
        "archive": archive_name,
        "status": "running",
        "message": "",
        "result": "",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _jobs[job_id] = job
    _save_job(job)
    return job


def _is_valid_tar(path):
    try:
        if tarfile.is_tarfile(path):
            return True
    except Exception:
        pass
    with path.open("rb") as fh:
        return fh.read(2) == b"\x1f\x8b"


def _resolve_result(job_dir, archive_path, started_at):
    marker = job_dir / "result.bin"
    if marker.is_file() and marker.stat().st_size > 0:
        return marker
    excluded = {"job.log", archive_path.name, "meta.json", "result.bin"}
    candidates = [
        p for p in job_dir.rglob("*")
        if p.is_file() and p.name not in excluded and p != archive_path
        and p.stat().st_mtime >= started_at
    ]
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


def _run_job(job_id, archive_path):
    job = _jobs[job_id]
    job_dir = _jobs_dir(job_id)
    log_path = job_dir / "job.log"
    started_at = job_dir.stat().st_mtime
    try:
        with log_path.open("wb") as log:
            proc = subprocess.run(
                [str(SCRIPT_PATH), str(archive_path)],
                cwd=job_dir,
                env={**os.environ, "TARDROP_RESULT_FILE": str(job_dir / "result.bin")},
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT,
            )
        if proc.returncode != 0:
            job["status"] = "failed"
            job["message"] = f"Le script a échoué (code {proc.returncode})."
        else:
            result = _resolve_result(job_dir, archive_path, started_at)
            if result is None:
                job["status"] = "failed"
                job["message"] = "Le script s'est terminé mais aucun fichier résultat n'a été trouvé."
            elif result.stat().st_size > MAX_RESULT_MB * 1024 * 1024:
                result.unlink(missing_ok=True)
                job["status"] = "failed"
                job["message"] = f"Fichier résultat trop volumineux (> {MAX_RESULT_MB} Mo)."
            else:
                job["status"] = "success"
                job["result"] = result.name
    except subprocess.TimeoutExpired:
        job["status"] = "failed"
        job["message"] = f"Délai dépassé ({TIMEOUT} s)."
    except FileNotFoundError:
        job["status"] = "failed"
        job["message"] = f"Script introuvable : {SCRIPT_PATH}"
    except Exception as exc:
        job["status"] = "failed"
        job["message"] = f"Erreur : {exc}"
    finally:
        _save_job(job)


def _start_job(job_id, archive_path):
    threading.Thread(target=_run_job, args=(job_id, archive_path), daemon=True).start()


@app.get("/")
def index():
    jobs = sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)[:25]
    return render_template("index.html", jobs=jobs)


@app.post("/jobs")
def create_job():
    if not SCRIPT_PATH.is_file() or not os.access(SCRIPT_PATH, os.X_OK):
        flash(f"Script non configuré ou non exécutable : {SCRIPT_PATH}")
        return redirect(url_for("index"))

    file = request.files.get("archive")
    if file is None or file.filename == "":
        flash("Veuillez choisir une archive tar.")
        return redirect(url_for("index"))

    name = Path(file.filename).name
    if not name.lower().endswith(ARCHIVE_SUFFIXES):
        flash("Format non supporté. Utilisez .tar, .tar.gz, .tgz, .tar.bz2, .tbz2, .tar.xz ou .txz.")
        return redirect(url_for("index"))

    job = _new_job(name)
    archive_path = _jobs_dir(job["id"]) / "archive.tar"
    file.save(archive_path)

    if not _is_valid_tar(archive_path):
        job.update(status="failed", message="Le fichier envoyé n'est pas une archive tar valide.")
        _save_job(job)
        return redirect(url_for("job_page", job_id=job["id"]))

    shutil.move(archive_path, archive_path.with_name(name))
    archive_path = archive_path.with_name(name)
    _start_job(job["id"], archive_path)
    return redirect(url_for("job_page", job_id=job["id"]))


@app.get("/jobs/<job_id>")
def job_page(job_id):
    job = _jobs.get(job_id)
    if job is None:
        abort(404)
    return render_template("job.html", job=job)


@app.get("/jobs/<job_id>/log")
def job_log(job_id):
    if job_id not in _jobs:
        abort(404)
    log_path = _jobs_dir(job_id) / "job.log"
    if not log_path.is_file():
        abort(404)
    return send_file(log_path, mimetype="text/plain", as_attachment=True,
                     download_name=f"{job_id}.log")


@app.get("/jobs/<job_id>/download")
def job_download(job_id):
    job = _jobs.get(job_id)
    if job is None or job["status"] != "success" or not job["result"]:
        abort(404)
    result_path = _jobs_dir(job_id) / job["result"]
    if not result_path.is_file():
        abort(404)
    return send_file(result_path, as_attachment=True)


_load_jobs()
