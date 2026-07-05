import sys
import os
import time
import threading
import subprocess
import sqlite3
import psutil
from datetime import datetime
from flask import Flask, request, jsonify, Response

# Force UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "entrada")
LOG_FILE = os.path.join(BASE_DIR, "pipeline_run.log")

os.makedirs(INPUT_DIR, exist_ok=True)

app = Flask(__name__)

# ── Resource Caps ───────────────────────────────────────────────
CPU_CORES = psutil.cpu_count(logical=True) or 4
MAX_WORKERS = max(1, int(CPU_CORES * 0.6))   # 60% of cores
RAM_PAUSE_PCT = 75                             # pause when RAM > 75%

def resource_ok():
    """Return True if we have enough resources to keep processing."""
    ram_pct = psutil.virtual_memory().percent
    cpu_pct = psutil.cpu_percent(interval=0.5)
    return ram_pct < RAM_PAUSE_PCT and cpu_pct < 90

def wait_for_resources(log_fn=print):
    """Block until RAM/CPU are below the threshold."""
    while not resource_ok():
        log_fn("[RECURSOS] Sistema sobrecarregado. A aguardar...")
        time.sleep(5)

# ── Background Process State ────────────────────────────────────
_active_process = None
_process_lock = threading.Lock()

# ── Flask Routes ────────────────────────────────────────────────
@app.route("/")
def index():
    return Response(HTML_PAGE, mimetype="text/html; charset=utf-8")

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    paths = request.form.getlist("paths")
    count = 0
    for file, path in zip(files, paths):
        clean = path.replace("../", "").replace("..\\", "")
        dest = os.path.join(INPUT_DIR, clean)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        file.save(dest)
        count += 1
    return jsonify({"ok": True, "count": count})

@app.route("/stats")
def stats():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM documents")
        docs = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM documents WHERE status = 'exported'")
        exported = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM documents WHERE status NOT IN ('exported','failed')")
        pending = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM documents WHERE storage_url IS NOT NULL AND storage_url != '' AND storage_url != 'skipped'")
        uploaded = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM pages")
        pages = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM pages WHERE ocr_status = 'done'")
        ocr_done = c.fetchone()[0]
        conn.close()
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        return jsonify({
            "docs": docs, "exported": exported, "pending": pending,
            "uploaded": uploaded,
            "pages": pages, "ocr_done": ocr_done,
            "ram_pct": round(ram.percent, 1),
            "cpu_pct": round(cpu, 1),
            "ram_free_gb": round(ram.available / 1024**3, 1)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/run", methods=["POST"])
def run():
    global _active_process
    with _process_lock:
        if _active_process and _active_process.poll() is None:
            return jsonify({"status": "already_running"})

        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] Pipeline iniciado...\n\n")

            log_f = open(LOG_FILE, "a", encoding="utf-8")
            python_exe = sys.executable
            script = os.path.join(os.path.dirname(__file__), "run_pipeline.py")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PIPELINE_MAX_WORKERS"] = str(MAX_WORKERS)
            # Prevent Ollama from being used (not enough RAM)
            env["DISABLE_OLLAMA"] = "1"

            _active_process = subprocess.Popen(
                [python_exe, "-u", script],
                stdout=log_f, stderr=subprocess.STDOUT,
                cwd=BASE_DIR, env=env
            )

            def monitor(proc, fh):
                proc.wait()
                fh.close()
                print("[Server] Pipeline process finished.")
            threading.Thread(target=monitor, args=(_active_process, log_f), daemon=True).start()

            return jsonify({"status": "started"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/status")
def status():
    global _active_process
    running = _active_process is not None and _active_process.poll() is None
    logs = ""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                # Return last 8000 chars to avoid flooding the browser
                logs = content[-8000:] if len(content) > 8000 else content
        except Exception:
            pass
    return jsonify({"running": running, "logs": logs})

# ── HTML (single-page, dead simple) ─────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Biblioteca Mecânica — Painel</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',sans-serif;background:#F5F3EE;color:#2C2A26;min-height:100vh}
  header{background:#2C2A26;color:#FAF9F6;padding:18px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25)}
  header h1{font-size:1.15rem;font-weight:600;letter-spacing:-.01em}
  header span{font-size:.82rem;opacity:.55}
  .wrap{max-width:960px;margin:0 auto;padding:32px 16px;display:grid;gap:20px}
  .card{background:#fff;border-radius:14px;padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
  h2{font-size:1rem;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
  /* Drop zone */
  #drop{border:2.5px dashed #C8C4B4;border-radius:12px;padding:40px 24px;text-align:center;cursor:pointer;transition:all .2s;background:#FAFAF7}
  #drop.over{border-color:#2C6A4F;background:#F0FFF4}
  #drop .icon{font-size:2.8rem;margin-bottom:10px}
  #drop p{color:#6B6860;font-size:.9rem}
  #drop strong{display:block;font-size:1rem;color:#2C2A26;margin-bottom:4px}
  #upload-progress{height:4px;background:#E8E4D8;border-radius:99px;margin-top:14px;overflow:hidden;display:none}
  #upload-bar{height:100%;width:0;background:#2C6A4F;transition:width .3s}
  /* Big button */
  #btn-run{width:100%;padding:18px;font-size:1.1rem;font-weight:700;border:none;border-radius:12px;background:#2C6A4F;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px;transition:all .2s;letter-spacing:-.01em}
  #btn-run:hover:not(:disabled){background:#235C43;transform:translateY(-1px)}
  #btn-run:disabled{background:#9DB5AB;cursor:not-allowed;transform:none}
  #btn-run .dot{width:10px;height:10px;border-radius:50%;background:#6EE7B7;display:none;animation:pulse 1.2s infinite}
  #btn-run.running .dot{display:block}
  @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.85)}}
  /* Console */
  #console{background:#1A1A1A;color:#D4E8DA;font-family:monospace;font-size:.78rem;padding:16px;border-radius:10px;height:320px;overflow-y:auto;white-space:pre-wrap;display:none;margin-top:16px;line-height:1.5}
  /* Stats grid */
  .stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
  .stat{background:#F5F3EE;border-radius:10px;padding:14px 16px}
  .stat .val{font-size:1.5rem;font-weight:700;color:#2C6A4F}
  .stat .lbl{font-size:.76rem;color:#6B6860;margin-top:2px}
  /* Resource bar */
  .res-row{display:flex;align-items:center;gap:10px;margin-top:12px;font-size:.82rem;color:#6B6860}
  .res-bar{flex:1;height:6px;background:#E8E4D8;border-radius:99px;overflow:hidden}
  .res-fill{height:100%;border-radius:99px;transition:width .5s}
  .res-fill.ok{background:#2C6A4F}
  .res-fill.warn{background:#D97706}
  .res-fill.danger{background:#DC2626}
</style>
</head>
<body>
<header>
  <h1>📐 Biblioteca de Engenharia Mecânica</h1>
  <span id="hdr-status">A aguardar...</span>
</header>
<div class="wrap">

  <!-- Step 1: Drop files -->
  <div class="card">
    <h2>1️⃣ Adicionar Ficheiros</h2>
    <div id="drop">
      <div class="icon">📂</div>
      <strong>Arrasta e solta PDFs ou pastas aqui</strong>
      <p>ou clica para selecionar do computador</p>
      <input type="file" id="file-in" multiple style="display:none">
      <input type="file" id="folder-in" webkitdirectory multiple style="display:none">
      <div style="margin-top:12px;display:flex;gap:8px;justify-content:center">
        <button id="btn-files" onclick="event.stopPropagation();document.getElementById('file-in').click()"
          style="padding:6px 14px;border:1px solid #C8C4B4;border-radius:8px;background:#fff;cursor:pointer;font-size:.85rem">
          📄 Ficheiros
        </button>
        <button id="btn-folder" onclick="event.stopPropagation();document.getElementById('folder-in').click()"
          style="padding:6px 14px;border:1px solid #C8C4B4;border-radius:8px;background:#fff;cursor:pointer;font-size:.85rem">
          📁 Pasta
        </button>
      </div>
    </div>
    <div id="upload-progress"><div id="upload-bar"></div></div>
    <p id="upload-msg" style="font-size:.82rem;color:#6B6860;margin-top:8px;text-align:center"></p>
  </div>

  <!-- Step 2: Run everything -->
  <div class="card">
    <h2>2️⃣ Processar e Publicar</h2>
    <p style="font-size:.88rem;color:#6B6860;margin-bottom:18px">
      Clica no botão para iniciar automaticamente: inventário → conversão → OCR → montagem → upload → publicação online.
      Podes fechar o browser e reabrir a qualquer momento — o processamento continua.
    </p>
    <button id="btn-run" onclick="startPipeline()">
      <span class="dot"></span>
      🚀 Processar Tudo Automaticamente
    </button>
    <div id="console"></div>
  </div>

  <!-- Stats -->
  <div class="card">
    <h2>📊 Estado da Biblioteca</h2>
    <div class="stat-grid">
      <div class="stat"><div class="val" id="s-docs">—</div><div class="lbl">Total de Documentos</div></div>
      <div class="stat"><div class="val" id="s-uploaded">—</div><div class="lbl">Ficheiros no GitHub (para download)</div></div>
      <div class="stat"><div class="val" id="s-exp">—</div><div class="lbl">Com Conteúdo no Site (IA processou)</div></div>
      <div class="stat"><div class="val" id="s-pend">—</div><div class="lbl">A Aguardar Processamento IA</div></div>
      <div class="stat"><div class="val" id="s-pages">—</div><div class="lbl">Páginas Totais</div></div>
      <div class="stat"><div class="val" id="s-ocr">—</div><div class="lbl">Páginas com OCR Feito</div></div>
      <div class="stat"><div class="val" id="s-ram">—</div><div class="lbl">RAM Disponível</div></div>
    </div>
    <div class="res-row">
      <span style="min-width:30px">CPU</span>
      <div class="res-bar"><div class="res-fill ok" id="cpu-bar" style="width:0%"></div></div>
      <span id="cpu-txt" style="min-width:40px;text-align:right">—</span>
    </div>
    <div class="res-row">
      <span style="min-width:30px">RAM</span>
      <div class="res-bar"><div class="res-fill ok" id="ram-bar" style="width:0%"></div></div>
      <span id="ram-txt" style="min-width:40px;text-align:right">—</span>
    </div>
  </div>

</div>

<script>
// ─ Upload ────────────────────────────────────────────────────────
const drop = document.getElementById('drop');
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); handleFiles(e.dataTransfer.files); });
drop.addEventListener('click', () => document.getElementById('file-in').click());
document.getElementById('file-in').addEventListener('change', e => handleFiles(e.target.files));
document.getElementById('folder-in').addEventListener('change', e => handleFiles(e.target.files, true));

function handleFiles(files, isFolder = false) {
  if (!files.length) return;
  const msg = document.getElementById('upload-msg');
  const prog = document.getElementById('upload-progress');
  const bar = document.getElementById('upload-bar');
  prog.style.display = 'block';
  bar.style.width = '0%';
  msg.textContent = `A carregar ${files.length} ficheiro(s)...`;

  const fd = new FormData();
  for (const f of files) {
    fd.append('files', f);
    fd.append('paths', isFolder ? f.webkitRelativePath : f.name);
  }
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/upload');
  xhr.upload.addEventListener('progress', e => {
    if (e.lengthComputable) bar.style.width = (e.loaded / e.total * 100) + '%';
  });
  xhr.onload = () => {
    bar.style.width = '100%';
    const r = JSON.parse(xhr.responseText);
    msg.textContent = r.ok ? `✅ ${r.count} ficheiro(s) adicionados com sucesso!` : '❌ Erro no upload.';
    setTimeout(() => { prog.style.display = 'none'; }, 2000);
    loadStats();
  };
  xhr.send(fd);
}

// ─ Pipeline ─────────────────────────────────────────────────────
let polling = false;
let pollInterval = null;

async function startPipeline() {
  const btn = document.getElementById('btn-run');
  const con = document.getElementById('console');
  btn.disabled = true;
  btn.classList.add('running');
  btn.innerHTML = '<span class="dot"></span> ⏳ A processar...';
  con.style.display = 'block';
  con.textContent = 'A iniciar pipeline...\\n';

  try {
    const res = await fetch('/run', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'started' || data.status === 'already_running') {
      startPolling();
    } else {
      con.textContent += '\\n❌ Erro: ' + (data.message || 'Falha ao iniciar.');
      btn.disabled = false;
      btn.classList.remove('running');
      btn.innerHTML = '🚀 Processar Tudo Automaticamente';
    }
  } catch (e) {
    con.textContent += '\\n❌ Erro de ligação: ' + e.message;
    btn.disabled = false;
    btn.classList.remove('running');
    btn.innerHTML = '🚀 Processar Tudo Automaticamente';
  }
}

function startPolling() {
  if (polling) return;
  polling = true;
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch('/status');
      const data = await res.json();
      const con = document.getElementById('console');
      const btn = document.getElementById('btn-run');
      if (data.logs) {
        con.style.display = 'block';
        con.textContent = data.logs;
        con.scrollTop = con.scrollHeight;
      }
      if (!data.running && polling) {
        polling = false;
        clearInterval(pollInterval);
        btn.disabled = false;
        btn.classList.remove('running');
        btn.innerHTML = '✅ Concluído — Clica para reiniciar';
        document.getElementById('hdr-status').textContent = 'Pipeline concluído!';
        loadStats();
      } else if (data.running) {
        btn.disabled = true;
        btn.classList.add('running');
        btn.innerHTML = '<span class="dot"></span> ⏳ A processar...';
      }
    } catch (e) {}
  }, 2000);
}

// ─ Stats ─────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await fetch('/stats');
    const s = await res.json();
    if (s.error) return;
    document.getElementById('s-docs').textContent = (s.docs || 0).toLocaleString();
    document.getElementById('s-uploaded').textContent = (s.uploaded || 0).toLocaleString();
    document.getElementById('s-exp').textContent = (s.exported || 0).toLocaleString();
    document.getElementById('s-pend').textContent = (s.pending || 0).toLocaleString();
    document.getElementById('s-pages').textContent = (s.pages || 0).toLocaleString();
    document.getElementById('s-ocr').textContent = (s.ocr_done || 0).toLocaleString();
    document.getElementById('s-ram').textContent = (s.ram_free_gb || 0) + ' GB';

    const cpuPct = s.cpu_pct || 0;
    const ramPct = s.ram_pct || 0;
    const cpuEl = document.getElementById('cpu-bar');
    const ramEl = document.getElementById('ram-bar');
    cpuEl.style.width = cpuPct + '%';
    cpuEl.className = 'res-fill ' + (cpuPct < 60 ? 'ok' : cpuPct < 85 ? 'warn' : 'danger');
    document.getElementById('cpu-txt').textContent = cpuPct + '%';
    ramEl.style.width = ramPct + '%';
    ramEl.className = 'res-fill ' + (ramPct < 60 ? 'ok' : ramPct < 80 ? 'warn' : 'danger');
    document.getElementById('ram-txt').textContent = ramPct + '%';

    document.getElementById('hdr-status').textContent =
      s.exported + '/' + s.docs + ' documentos online';
  } catch(e) {}
}

// On load: check if pipeline is already running
(async function init() {
  loadStats();
  setInterval(loadStats, 6000);
  try {
    const res = await fetch('/status');
    const data = await res.json();
    if (data.running) {
      document.getElementById('console').style.display = 'block';
      startPolling();
      const btn = document.getElementById('btn-run');
      btn.disabled = true;
      btn.classList.add('running');
      btn.innerHTML = '<span class="dot"></span> ⏳ A processar...';
    }
    if (data.logs) {
      const con = document.getElementById('console');
      con.textContent = data.logs;
      con.scrollTop = con.scrollHeight;
    }
  } catch(e) {}
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import webbrowser
    from threading import Timer
    Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    print(f"Servidor a iniciar em http://localhost:5000 ...")
    print(f"Limite de recursos: {MAX_WORKERS}/{CPU_CORES} cores (~60%), RAM pause > {RAM_PAUSE_PCT}%")
    app.run(host="localhost", port=5000, debug=False)
