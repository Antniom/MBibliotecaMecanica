"""
pipeline/cloud_sync.py
Helper module for communicating with the Cloudflare D1 API.
Used by worker.py and optionally by run_pipeline.py for heartbeat reporting.

Zero new dependencies — uses only `requests` which is already in the venv.
"""

import os
import socket
import traceback
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────
WORKER_API_TOKEN = os.getenv("WORKER_API_TOKEN", "")
SITE_URL = os.getenv("CLOUDFLARE_PAGES_URL", "").rstrip("/")

# CLOUDFLARE_PAGES_URL must be set to your deployed Pages URL, e.g.
# https://mbibliotecamecanica.pages.dev
# or your custom domain.


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {WORKER_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    if not SITE_URL:
        raise RuntimeError(
            "CLOUDFLARE_PAGES_URL não está definida no .env. "
            "Define-a como a URL da tua Cloudflare Pages (ex: https://mbibliotecamecanica.pages.dev)"
        )
    return f"{SITE_URL}{path}"


def is_configured() -> bool:
    """Return True if cloud sync is configured (both env vars set)."""
    return bool(WORKER_API_TOKEN and SITE_URL)


def sync(
    status: str = "idle",
    current_doc: str | None = None,
    progress_done: int = 0,
    progress_total: int = 0,
) -> list[dict]:
    """
    Send heartbeat to the cloud and return list of approved submissions.
    Returns [] if not configured or on network error (graceful degradation).
    """
    if not is_configured():
        return []

    payload = {
        "status": status,
        "current_doc": current_doc,
        "progress_done": progress_done,
        "progress_total": progress_total,
        "machine_name": socket.gethostname(),
    }

    try:
        res = requests.post(_url("/api/worker/sync"), json=payload, headers=_headers(), timeout=15)
        res.raise_for_status()
        data = res.json()
        return data.get("approved", [])
    except requests.exceptions.ConnectionError:
        print("[CLOUD] Sem ligação ao servidor. A continuar em modo local...")
        return []
    except requests.exceptions.Timeout:
        print("[CLOUD] Timeout ao ligar ao servidor.")
        return []
    except Exception as e:
        print(f"[CLOUD] Erro no sync: {e}")
        return []


def download_file(url: str, dest_folder: str, filename: str) -> str:
    """
    Download a file from a URL to dest_folder/filename.
    Returns the local file path on success. Raises on failure.
    """
    os.makedirs(dest_folder, exist_ok=True)
    dest_path = os.path.join(dest_folder, filename)

    print(f"[CLOUD] A descarregar: {filename} ...")
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        size_mb = os.path.getsize(dest_path) / 1024 / 1024
        print(f"[CLOUD] Download completo: {filename} ({size_mb:.1f} MB)")
        return dest_path
    except Exception as e:
        # Clean up partial file
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise RuntimeError(f"Falha ao descarregar {filename}: {e}") from e


def mark_downloading(submission_id: str):
    """Mark a submission as 'downloading' so the admin panel shows progress."""
    if not is_configured():
        return
    try:
        requests.post(
            _url("/api/worker/sync"),
            json={"status": "running", "current_doc": f"A descarregar..."},
            headers=_headers(),
            timeout=10,
        )
    except Exception:
        pass  # Non-fatal


def mark_done(submission_id: str, local_doc_id: str | None = None):
    """Mark a submission as successfully processed."""
    if not is_configured():
        return
    try:
        res = requests.post(
            _url("/api/worker/done"),
            json={"submission_id": submission_id, "local_doc_id": local_doc_id},
            headers=_headers(),
            timeout=15,
        )
        res.raise_for_status()
        print(f"[CLOUD] Submissão {submission_id[:8]}... marcada como concluída.")
    except Exception as e:
        print(f"[CLOUD] Erro ao marcar submissão como concluída: {e}")


def mark_failed(submission_id: str, stage: str, error_message: str, exc: Exception | None = None):
    """Mark a submission as failed and log the error."""
    if not is_configured():
        return
    stack = traceback.format_exc() if exc else None
    try:
        res = requests.post(
            _url("/api/worker/failed"),
            json={
                "submission_id": submission_id,
                "stage": stage,
                "error_message": str(error_message),
                "stack_trace": stack,
            },
            headers=_headers(),
            timeout=15,
        )
        res.raise_for_status()
        print(f"[CLOUD] Submissão {submission_id[:8]}... marcada como falhada ({stage}).")
    except Exception as e:
        print(f"[CLOUD] Erro ao registar falha: {e}")
