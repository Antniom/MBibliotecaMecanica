"""
pipeline/worker.py
MBibliotecaMecanica — Background Worker

Automatically runs when double-clicked via start_worker.bat.
Polls the cloud for approved submissions, downloads files,
runs the existing pipeline, and reports results back.

No new Python packages required — uses only requests (already in venv).
"""

import sys
import os
import time
import socket
import signal
import traceback
from pathlib import Path

# Force UTF-8 output (Windows compatibility)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure pipeline/ is in path
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR  = os.path.dirname(PIPELINE_DIR)
sys.path.insert(0, PIPELINE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

import cloud_sync

ENTRADA_DIR = os.path.join(PROJECT_DIR, 'entrada')
POLL_INTERVAL = 30  # seconds between polls

_running = True
_current_submission_id = None


def handle_signal(sig, frame):
    """Graceful shutdown on Ctrl+C."""
    global _running
    print("\n[WORKER] A parar... (a aguardar tarefa actual terminar)")
    _running = False
    cloud_sync.sync(status='paused')


signal.signal(signal.SIGINT, handle_signal)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, handle_signal)


def print_banner():
    print("=" * 60)
    print("   MBIBLIOTECAMECANICA — WORKER DE PROCESSAMENTO")
    print("=" * 60)
    print(f"  Máquina   : {socket.gethostname()}")
    print(f"  Projeto   : {PROJECT_DIR}")
    print(f"  Intervalo : a cada {POLL_INTERVAL}s")
    if cloud_sync.is_configured():
        print(f"  Cloud     : {cloud_sync.SITE_URL}")
    else:
        print("  Cloud     : ⚠️  CLOUDFLARE_PAGES_URL / WORKER_API_TOKEN não configurados")
        print("              Define estas variáveis no .env para activar o modo cloud.")
    print("=" * 60)
    print("  Prima Ctrl+C para parar.")
    print()


def process_submission(submission: dict) -> bool:
    """
    Download and process a single approved submission.
    Returns True on success, False on failure.
    """
    global _current_submission_id

    sub_id   = submission['id']
    filename = submission['file_name']
    url      = submission.get('github_asset_url', '')

    _current_submission_id = sub_id

    print(f"\n[WORKER] ── Nova submissão ──────────────────────────────")
    print(f"  ID   : {sub_id}")
    print(f"  File : {filename}")
    print(f"  URL  : {url[:60]}..." if len(url) > 60 else f"  URL  : {url}")

    # 1. Download
    cloud_sync.mark_downloading(sub_id)
    try:
        local_path = cloud_sync.download_file(url, ENTRADA_DIR, filename)
    except Exception as e:
        print(f"[WORKER] ❌ Falha no download: {e}")
        cloud_sync.mark_failed(sub_id, 'download', str(e), e)
        return False

    # 2. Run the existing pipeline
    print(f"[WORKER] 🔄 A processar com pipeline...")
    try:
        import run_pipeline

        # Override disciplina/tipo from cloud assignment if available
        if submission.get('assigned_disciplina'):
            os.environ['FORCE_DISCIPLINA'] = submission['assigned_disciplina']
        if submission.get('assigned_tipo'):
            os.environ['FORCE_TIPO'] = submission['assigned_tipo']
        if submission.get('assigned_ano'):
            os.environ['FORCE_ANO'] = str(submission['assigned_ano'])
        if submission.get('assigned_semestre'):
            os.environ['FORCE_SEMESTRE'] = str(submission['assigned_semestre'])

        run_pipeline.main()

        # Clear overrides
        for k in ['FORCE_DISCIPLINA', 'FORCE_TIPO', 'FORCE_ANO', 'FORCE_SEMESTRE']:
            os.environ.pop(k, None)

    except SystemExit:
        pass  # run_pipeline.main() may call sys.exit(0) on success
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[WORKER] ❌ Erro no pipeline:\n{tb}")
        cloud_sync.mark_failed(sub_id, 'pipeline', str(e), e)
        return False

    # 3. Check final document status in local SQLite DB and mark done or failed
    from inventory import calculate_sha256
    from db_utils import get_db_connection

    local_doc_id = None
    db_status = 'failed'
    try:
        local_doc_id = calculate_sha256(local_path)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM documents WHERE id = ?", (local_doc_id,))
        row = cursor.fetchone()
        if row:
            db_status = row["status"] if hasattr(row, "keys") else row[0]
        conn.close()
    except Exception as e:
        print(f"[WORKER] Não foi possível verificar o estado do documento na base de dados local: {e}")

    if db_status == 'exported':
        print(f"[WORKER] ✅ Submissão processada com sucesso.")
        cloud_sync.mark_done(sub_id, local_doc_id)
        _current_submission_id = None
        return True
    else:
        err_msg = f"O pipeline local terminou com o estado: '{db_status}'"
        print(f"[WORKER] ❌ {err_msg}")
        cloud_sync.mark_failed(sub_id, 'pipeline', err_msg)
        _current_submission_id = None
        return False


def resume_interrupted():
    """
    On startup, check for submissions that were interrupted mid-process.
    The cloud API returns them in the 'approved' list with status
    'downloading' or 'processing', so they're automatically retried.
    """
    if not cloud_sync.is_configured():
        return

    print("[WORKER] A verificar submissões interrompidas...")
    approved = cloud_sync.sync(status='idle')
    interrupted = [s for s in approved if s.get('status') in ('downloading', 'processing')]
    if interrupted:
        print(f"[WORKER] ⚡ {len(interrupted)} submissão(ões) interrompida(s) serão retomadas.")
    else:
        print("[WORKER] Nenhuma submissão interrompida encontrada.")


def main():
    print_banner()

    if not cloud_sync.is_configured():
        print("[WORKER] ⚠️  Modo cloud não configurado.")
        print("         O worker ainda pode processar ficheiros locais em entrada/")
        print("         mas não receberá novas submissões da web.")
        print()

    resume_interrupted()

    poll_count = 0
    total_processed = 0
    total_failed = 0

    print("\n[WORKER] A iniciar ciclo de polling...\n")

    while _running:
        poll_count += 1

        # Get approved submissions + send heartbeat
        if cloud_sync.is_configured():
            approved = cloud_sync.sync(
                status='running' if total_processed > 0 else 'idle',
                progress_done=total_processed,
                progress_total=total_processed + total_failed,
            )
        else:
            approved = []

        if approved:
            print(f"[WORKER] 📥 {len(approved)} submissão(ões) aprovada(s) para processar.")
            for submission in approved:
                if not _running:
                    break
                success = process_submission(submission)
                if success:
                    total_processed += 1
                else:
                    total_failed += 1

                # Final heartbeat after each submission
                cloud_sync.sync(
                    status='running',
                    progress_done=total_processed,
                    progress_total=total_processed + total_failed,
                )
        else:
            # Quiet poll — just print a dot every 10 polls
            if poll_count % 10 == 0:
                print(f"[WORKER] 💤 A aguardar... (sondagens: {poll_count}, processados: {total_processed})")

        if _running:
            time.sleep(POLL_INTERVAL)

    # Shutdown
    cloud_sync.sync(status='paused', progress_done=total_processed, progress_total=total_processed+total_failed)
    print(f"\n[WORKER] Worker parado. Processados: {total_processed}, Falhados: {total_failed}")


if __name__ == '__main__':
    main()
