import os
import sys
import subprocess
import sqlite3
from flask import Flask, request, jsonify, render_template_string, Response
from db_utils import get_db_connection

app = Flask(__name__)

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "entrada")

# Create input dir if not exists
os.makedirs(INPUT_DIR, exist_ok=True)

def regenerate_astro_files_for_doc(doc_id, cursor):
    import json
    from datetime import datetime
    
    # Retrieve doc details
    cursor.execute(
        """
        SELECT id, path_original, disciplina, tipo, ano, semestre, storage_release_tag, storage_url, status 
        FROM documents WHERE id = ?
        """,
        (doc_id,)
    )
    doc = cursor.fetchone()
    if not doc:
        return
        
    filepath = doc["path_original"]
    ano = int(doc["ano"]) if doc["ano"] is not None else 1
    semestre = int(doc["semestre"]) if doc["semestre"] is not None else 1
    disciplina = doc["disciplina"] if doc["disciplina"] else "desconhecido"
    tipo = doc["tipo"] if doc["tipo"] else "teoria"
    status = doc["status"]
    
    # Target directory
    dest_dir = os.path.join(
        BASE_DIR, "web", "src", "content", "biblioteca",
        f"{ano}-ano", f"{semestre}-semestre", disciplina, tipo
    )
    os.makedirs(dest_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(filepath))[0].replace("#", "_").replace("?", "_")
    md_path = os.path.join(dest_dir, f"{base_name}.md")
    meta_path = os.path.join(dest_dir, f"{base_name}.meta.json")
    
    # Check if doc has pages to construct validated_text
    cursor.execute(
        "SELECT page_num, validated_text, confidence, needs_ocr FROM pages WHERE doc_id = ? ORDER BY page_num ASC",
        (doc_id,)
    )
    pages = cursor.fetchall()
    
    if pages:
        pages_list = [dict(p) for p in pages]
        conf_sum = sum(p["confidence"] for p in pages_list)
        conf_avg = conf_sum / len(pages_list) if pages_list else 0.0
        
        if status in ['exported', 'validated']:
            any_ocr_needed = any(p["needs_ocr"] == 1 for p in pages_list)
            if not any_ocr_needed:
                markdown_body = "<document>\n"
                for p in pages_list:
                    markdown_body += f"  <section topic=\"geral\" page=\"{p['page_num']}\">\n"
                    lines = p["validated_text"].split("\n") if p["validated_text"] else []
                    markdown_body += "\n".join("    " + l for l in lines) + "\n"
                    markdown_body += "  </section>\n"
                markdown_body += "</document>"
            else:
                markdown_body = "<document>\n"
                for p in pages_list:
                    markdown_body += f"  <section topic=\"scanned\" page=\"{p['page_num']}\">\n"
                    lines = p["validated_text"].split("\n") if p["validated_text"] else []
                    markdown_body += "\n".join("    " + l for l in lines) + "\n"
                    markdown_body += "  </section>\n"
                markdown_body += "</document>"
        else:
            conf_avg = 0.0
            markdown_body = """<document>
  <section topic="geral" page="1">
    O processamento de inteligência artificial (OCR e Validação) para este documento está na fila de espera.
    O ficheiro original está disponível para download.
  </section>
</document>"""
    else:
        conf_avg = 0.0
        markdown_body = """<document>
  <section topic="geral" page="1">
    O processamento de inteligência artificial (OCR e Validação) para este documento está na fila de espera.
    O ficheiro original está disponível para download.
  </section>
</document>"""

    doc_meta = {
        "id": doc_id,
        "title": base_name.replace("-", " ").title(),
        "path_original": filepath,
        "disciplina": disciplina,
        "tipo": tipo,
        "ano": ano,
        "semestre": semestre,
        "storage_release_tag": doc["storage_release_tag"],
        "storage_url": doc["storage_url"],
        "confianca_media": conf_avg,
        "assembled_at": datetime.now().isoformat()
    }
    
    # Write files
    md_content = f"""---
title: "{doc_meta['title']}"
disciplina: "{disciplina}"
ano: {ano}
semestre: {semestre}
tipo: "{tipo}"
fonte_original: "{os.path.basename(filepath)}"
confianca_media: {conf_avg:.2f}
data_processamento: "{datetime.now().strftime('%Y-%m-%d')}"
storage_url: "{doc['storage_url'] or ''}"
hash: "{doc_id}"
---

{markdown_body}
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(doc_meta, f, indent=2, ensure_ascii=False)

# HTML Template with Warm Beige Design System
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel de Ingestão — MBibliotecaMecânica</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Inter:wght@400;500;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            /* --- SURFACE COLORS --- */
            --bg-main: #F3F1E9;       /* Warm Beige canvas */
            --bg-card: #FFFFFF;       /* Clean white card surface */
            --panel-border: #E0DEC8;  /* Soft framing border */
            --card-border: #E0DEC8;

            /* --- TYPOGRAPHY COLORS --- */
            --text-primary: #191919;   /* Near-black body text */
            --text-secondary: #565656; /* Readable secondary gray */
            --text-tertiary: #8f8f8f;  /* Muted text / icons */

            /* --- ACCENT COLORS --- */
            --accent: #D96C53;               /* Burnt Orange — primary action */
            --accent-hover: #c45b42;         /* Darker hover shade */
            --accent-glow: rgba(217,108,83,0.15); /* Focus rings / subtle tints */

            /* --- STATUS COLORS --- */
            --success: #2D6A4F;   /* Deep natural green */
            --warning: #D08C60;   /* Warm earthy orange */
            --danger: #BC4749;    /* Muted terracotta red */

            /* --- FONTS --- */
            --font-heading: 'Merriweather', 'Georgia', serif;
            --font-body:    'Inter', system-ui, sans-serif;
            --font-mono:    'JetBrains Mono', monospace;

            /* --- SPACING & EFFECTS --- */
            --shadow-card:  0 4px 12px rgba(0,0,0,0.05);
            --shadow-hover: 0 8px 24px rgba(0,0,0,0.08);

            --radius-sm: 8px;   /* Buttons, inputs */
            --radius-md: 12px;  /* Cards, sections */
            --radius-lg: 16px;  /* Main containers */
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            padding: 0;
            font-family: var(--font-body);
            color: var(--text-primary);
            background: var(--bg-main);
            line-height: 1.6;
            min-height: 100vh;
        }

        h1, h2, h3, h4 {
            font-family: var(--font-heading);
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 0;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px 24px;
        }

        .header {
            border-bottom: 1px solid var(--panel-border);
            padding-bottom: 24px;
            margin-bottom: 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .title {
            font-size: 2rem;
            margin: 0 0 8px;
        }

        .subtitle {
            margin: 0;
            color: var(--text-secondary);
            font-size: 1.05rem;
        }

        .grid-layout {
            display: grid;
            grid-template-columns: 1fr;
            gap: 24px;
        }
        @media (min-width: 768px) {
            .grid-layout {
                grid-template-columns: 3fr 2fr;
            }
        }

        /* Surfaces */
        .card, .surface, .panel {
            background: var(--bg-card);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-card);
            padding: 24px;
            transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        
        /* Drag-and-drop zone */
        .dropzone {
            border: 2px dashed var(--panel-border);
            border-radius: var(--radius-md);
            padding: 48px 24px;
            text-align: center;
            background: #FAFAFA;
            cursor: pointer;
            transition: all 0.25s ease;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
        }
        .dropzone.dragover {
            border-color: var(--accent);
            background: var(--accent-glow);
            transform: scale(1.01);
        }
        .dropzone-icon {
            font-size: 3rem;
            opacity: 0.7;
            transition: transform 0.2s ease;
        }
        .dropzone:hover .dropzone-icon {
            transform: translateY(-4px);
        }

        /* Buttons */
        .btn-primary {
            background: var(--text-primary);
            color: #fff;
            padding: 10px 20px;
            border-radius: var(--radius-sm);
            font-family: var(--font-body);
            font-weight: 600;
            font-size: 0.95rem;
            border: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
            transition: all 0.2s ease;
        }
        .btn-primary:hover {
            background: var(--accent);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--accent-glow);
        }
        .btn-primary:active { transform: translateY(0); }

        .btn-secondary {
            background: transparent;
            border: 1px solid var(--panel-border);
            color: var(--text-secondary);
            padding: 10px 20px;
            border-radius: var(--radius-sm);
            font-family: var(--font-body);
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn-secondary:hover {
            border-color: var(--text-primary);
            color: var(--text-primary);
            background: #fff;
        }

        /* Stats List */
        .stats-list {
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .stats-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 14px;
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-sm);
            background: #FAF9F6;
        }
        .stats-label {
            font-weight: 500;
            font-size: 0.9rem;
        }
        .stats-val {
            font-family: var(--font-mono);
            font-weight: 600;
            font-size: 0.95rem;
            color: var(--accent);
        }

        /* File queue view */
        .queue-container {
            margin-top: 24px;
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-sm);
            display: none;
        }
        .queue-item {
            padding: 8px 12px;
            border-bottom: 1px solid var(--panel-border);
            font-size: 0.85rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #FFF;
        }
        .queue-item:last-child { border-bottom: none; }

        /* Logger console */
        .console-container {
            margin-top: 24px;
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: var(--radius-sm);
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
            max-height: 350px;
            overflow-y: auto;
            white-space: pre-wrap;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.5);
            display: none;
        }

        /* Progress Bar */
        .progress-container {
            width: 100%;
            height: 6px;
            background: var(--panel-border);
            border-radius: 99px;
            overflow: hidden;
            margin-top: 16px;
            display: none;
        }
        .progress-bar {
            height: 100%;
            width: 0%;
            background: var(--accent);
            transition: width 0.15s ease;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div>
                <h1 class="title">📐 Painel de Ingestão</h1>
                <p class="subtitle">Adiciona novos ficheiros e pastas de materiais à biblioteca.</p>
            </div>
            <a href="http://localhost:4321" target="_blank" class="btn-secondary">💻 Abrir Biblioteca</a>
        </header>

        <div class="grid-layout">
            <!-- Left: Dropzone -->
            <div>
                <div class="card" style="margin-bottom: 24px;">
                    <h2 style="font-size: 1.3rem; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                        <span>📥</span> Carregar Ficheiros ou Pastas
                    </h2>
                    
                    <div id="dropzone" class="dropzone">
                        <div class="dropzone-icon">📁</div>
                        <div>
                            <strong style="display: block; font-size: 1.05rem; margin-bottom: 4px;">Arrasta e solta aqui</strong>
                            <span style="color: var(--text-secondary); font-size: 0.9rem;">ou clica para selecionar do computador</span>
                        </div>
                        <div style="display: flex; gap: 12px; margin-top: 8px;">
                            <button id="btn-select-files" class="btn-secondary" style="padding: 6px 14px; font-size: 0.85rem;">Ficheiros</button>
                            <button id="btn-select-folder" class="btn-secondary" style="padding: 6px 14px; font-size: 0.85rem;">Pasta</button>
                        </div>
                        <input type="file" id="file-input" multiple style="display: none;">
                        <input type="file" id="folder-input" webkitdirectory directory multiple style="display: none;">
                    </div>

                    <!-- Progress & Queue -->
                    <div id="progress-wrapper" class="progress-container">
                        <div id="progress-bar" class="progress-bar"></div>
                    </div>
                    
                    <div id="queue" class="queue-container"></div>
                </div>

                <!-- Pipeline runner -->
                <div class="card">
                    <h2 style="font-size: 1.3rem; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                        <span>⚙️</span> Processamento da Biblioteca
                    </h2>
                    <p style="color: var(--text-secondary); font-size: 0.9rem; margin-top: 0; margin-bottom: 20px;">
                        Depois de adicionar novos ficheiros, clica no botão abaixo para correr o pipeline de processamento (Inventário, Conversão, OCR, Validação e Indexação Astro).
                    </p>
                    <button id="btn-run-pipeline" class="btn-primary" style="padding: 12px 24px; font-size: 1rem; width: 100%; justify-content: center;">
                        🚀 Executar Pipeline de Processamento
                    </button>

                    <!-- Console -->
                    <div id="console" class="console-container"></div>
                </div>
            </div>

            <!-- Right: Stats -->
            <div>
                <div class="card" style="position: sticky; top: 96px;">
                    <h2 style="font-size: 1.3rem; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                        <span>📊</span> Estado do Repositório
                    </h2>
                    
                    <ul class="stats-list">
                        <li class="stats-item">
                            <span class="stats-label">Total de Documentos</span>
                            <span id="stat-docs" class="stats-val">—</span>
                        </li>
                        <li class="stats-item">
                            <span class="stats-label">Páginas Registadas</span>
                            <span id="stat-pages" class="stats-val">—</span>
                        </li>
                        
                        <!-- OCR Progress -->
                        <li class="stats-item" style="flex-direction: column; align-items: stretch; gap: 8px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                                <span class="stats-label">Progresso OCR (Local)</span>
                                <span id="stat-ocr-percent" class="stats-val">0%</span>
                            </div>
                            <div style="width: 100%; height: 6px; background: #E0DEC8; border-radius: 99px; overflow: hidden; display: block; margin-top: 0;">
                                <div id="progress-bar-ocr" style="height: 100%; width: 0%; background: #2D6A4F; transition: width 0.25s ease;"></div>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-secondary);">
                                <span id="stat-ocr-pages-left">A calcular...</span>
                                <span id="stat-ocr-detail">—</span>
                            </div>
                        </li>
                        
                        <!-- Validation Progress -->
                        <li class="stats-item" style="flex-direction: column; align-items: stretch; gap: 8px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                                <span class="stats-label">Validação Vision (Gemini)</span>
                                <span id="stat-val-percent" class="stats-val">0%</span>
                            </div>
                            <div style="width: 100%; height: 6px; background: #E0DEC8; border-radius: 99px; overflow: hidden; display: block; margin-top: 0;">
                                <div id="progress-bar-val" style="height: 100%; width: 0%; background: #D96C53; transition: width 0.25s ease;"></div>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-secondary);">
                                <span id="stat-val-pages-left">A calcular...</span>
                                <span id="stat-val-detail">—</span>
                            </div>
                        </li>

                        <li class="stats-item">
                            <span class="stats-label">Documentos em Falta (Conversão)</span>
                            <span id="stat-pending" class="stats-val">—</span>
                        </li>
                        <li class="stats-item">
                            <span class="stats-label">Processados & Exportados</span>
                            <span id="stat-exported" class="stats-val">—</span>
                        </li>
                    </ul>

                    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--panel-border); font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4;">
                        ℹ️ O pipeline de processamento analisa e indexa o texto para a pesquisa client-side. Novos ficheiros são colocados na pasta <code>entrada/</code> antes do processamento.
                    </div>
                </div>
            </div>
        </div>

        <!-- File Explorer Section -->
        <div class="card" style="margin-top: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
                <h2 style="font-size: 1.3rem; margin: 0; display: flex; align-items: center; gap: 8px; font-family: var(--font-heading);">
                    <span>📂</span> Gestor de Ficheiros
                </h2>
                <div style="display: flex; gap: 8px; flex: 1; max-width: 400px;">
                    <input type="text" id="explorer-search" placeholder="🔍 Procurar por nome de ficheiro..." style="padding: 10px 14px; font-size: 0.9rem; flex: 1; border: 1px solid var(--panel-border); border-radius: var(--radius-sm); outline: none; background: #FAF9F6;" />
                </div>
            </div>
            
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem;">
                    <thead>
                        <tr style="border-bottom: 2px solid var(--panel-border); background: #FAF9F5;">
                            <th style="padding: 12px 8px; font-weight: 600;">Ficheiro</th>
                            <th style="padding: 12px 8px; font-weight: 600;">Disciplina</th>
                            <th style="padding: 12px 8px; font-weight: 600;">Tipo</th>
                            <th style="padding: 12px 8px; font-weight: 600; width: 100px;">Ano/Sem</th>
                            <th style="padding: 12px 8px; font-weight: 600; width: 120px;">Estado</th>
                            <th style="padding: 12px 8px; text-align: right; font-weight: 600; width: 180px;">Ações</th>
                        </tr>
                    </thead>
                    <tbody id="explorer-tbody">
                        <tr>
                            <td colspan="6" style="padding: 24px; text-align: center; color: var(--text-tertiary);">A carregar documentos...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Rename Modal -->
    <div id="rename-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; z-index: 1000;">
        <div class="card" style="width: 100%; max-width: 450px; background: white; padding: 24px; border-radius: var(--radius-md); box-shadow: 0 10px 30px rgba(0,0,0,0.15);">
            <h3 style="margin-bottom: 16px; font-family: var(--font-heading);">✏️ Renomear Documento</h3>
            <input type="hidden" id="rename-doc-id" />
            <div style="margin-bottom: 16px;">
                <label style="display: block; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 6px; font-weight: 600;">Novo Nome (sem extensão):</label>
                <input type="text" id="rename-input" style="width: 100%; padding: 10px; border: 1px solid var(--panel-border); border-radius: var(--radius-sm); font-size: 0.9rem; outline: none;" />
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 12px;">
                <button id="btn-cancel-rename" class="btn-secondary" style="padding: 8px 16px; font-size: 0.88rem;">Cancelar</button>
                <button id="btn-save-rename" class="btn-primary" style="padding: 8px 16px; font-size: 0.88rem;">Salvar</button>
            </div>
        </div>
    </div>

    <!-- Move Modal -->
    <div id="move-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; z-index: 1000;">
        <div class="card" style="width: 100%; max-width: 500px; background: white; padding: 24px; border-radius: var(--radius-md); box-shadow: 0 10px 30px rgba(0,0,0,0.15);">
            <h3 style="margin-bottom: 16px; font-family: var(--font-heading);">📦 Mover / Reclassificar</h3>
            <input type="hidden" id="move-doc-id" />
            
            <div style="margin-bottom: 12px;">
                <label style="display: block; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">Disciplina / UC:</label>
                <select id="move-uc-select" style="width: 100%; padding: 10px; border: 1px solid var(--panel-border); border-radius: var(--radius-sm); font-size: 0.9rem; outline: none; background: white;"></select>
            </div>
            
            <div style="margin-bottom: 12px;">
                <label style="display: block; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">Tipo / Categoria:</label>
                <select id="move-tipo-select" style="width: 100%; padding: 10px; border: 1px solid var(--panel-border); border-radius: var(--radius-sm); font-size: 0.9rem; outline: none; background: white;">
                    <option value="teoria">Slides e Teoria</option>
                    <option value="fichas-exercicios">Fichas de Exercícios</option>
                    <option value="resumos">Resumos</option>
                    <option value="resolucoes">Resoluções</option>
                    <option value="testes-exames">Testes e Exames</option>
                    <option value="trabalhos-projetos">Trabalhos e Projetos</option>
                </select>
            </div>
            
            <div style="display: flex; gap: 12px; margin-bottom: 20px;">
                <div style="flex: 1;">
                    <label style="display: block; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">Ano:</label>
                    <select id="move-ano-select" style="width: 100%; padding: 10px; border: 1px solid var(--panel-border); border-radius: var(--radius-sm); font-size: 0.9rem; outline: none; background: white;">
                        <option value="1">1º Ano</option>
                        <option value="2">2º Ano</option>
                        <option value="3">3º Ano</option>
                    </select>
                </div>
                <div style="flex: 1;">
                    <label style="display: block; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">Semestre:</label>
                    <select id="move-semestre-select" style="width: 100%; padding: 10px; border: 1px solid var(--panel-border); border-radius: var(--radius-sm); font-size: 0.9rem; outline: none; background: white;">
                        <option value="1">1º Semestre</option>
                        <option value="2">2º Semestre</option>
                    </select>
                </div>
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 12px;">
                <button id="btn-cancel-move" class="btn-secondary" style="padding: 8px 16px; font-size: 0.88rem;">Cancelar</button>
                <button id="btn-save-move" class="btn-primary" style="padding: 8px 16px; font-size: 0.88rem;">Mover</button>
            </div>
        </div>
    </div>

    <script>
        const dropzone = document.getElementById("dropzone");
        const fileInput = document.getElementById("file-input");
        const folderInput = document.getElementById("folder-input");
        const btnSelectFiles = document.getElementById("btn-select-files");
        const btnSelectFolder = document.getElementById("btn-select-folder");
        const queueDiv = document.getElementById("queue");
        const progressWrapper = document.getElementById("progress-wrapper");
        const progressBar = document.getElementById("progress-bar");
        const btnRunPipeline = document.getElementById("btn-run-pipeline");
        const consoleDiv = document.getElementById("console");

        // Load stats on load
        async function loadStats() {
            try {
                const res = await fetch("/stats");
                const stats = await res.json();
                document.getElementById("stat-docs").textContent = stats.docs;
                document.getElementById("stat-pages").textContent = stats.pages;
                document.getElementById("stat-pending").textContent = stats.pending;
                document.getElementById("stat-exported").textContent = stats.exported;
                
                // OCR Stats calculation
                const ocrTotal = stats.ocr_done + stats.ocr_pending + stats.ocr_failed;
                if (ocrTotal > 0) {
                    const ocrPercent = Math.round((stats.ocr_done / ocrTotal) * 100);
                    document.getElementById("stat-ocr-percent").textContent = `${ocrPercent}%`;
                    document.getElementById("progress-bar-ocr").style.width = `${ocrPercent}%`;
                    document.getElementById("stat-ocr-pages-left").textContent = `${stats.ocr_pending} pág. restantes`;
                    document.getElementById("stat-ocr-detail").textContent = `${stats.ocr_done} / ${ocrTotal}`;
                } else {
                    document.getElementById("stat-ocr-percent").textContent = "100%";
                    document.getElementById("progress-bar-ocr").style.width = "100%";
                    document.getElementById("stat-ocr-pages-left").textContent = "Sem páginas pendentes";
                    document.getElementById("stat-ocr-detail").textContent = "0 / 0";
                }
                
                // Validation Stats calculation
                const valTotal = stats.val_done + stats.val_pending + stats.val_failed;
                if (valTotal > 0) {
                    const valPercent = Math.round((stats.val_done / valTotal) * 100);
                    document.getElementById("stat-val-percent").textContent = `${valPercent}%`;
                    document.getElementById("progress-bar-val").style.width = `${valPercent}%`;
                    document.getElementById("stat-val-pages-left").textContent = `${stats.val_pending} pág. restantes`;
                    document.getElementById("stat-val-detail").textContent = `${stats.val_done} / ${valTotal}`;
                } else {
                    document.getElementById("stat-val-percent").textContent = "100%";
                    document.getElementById("progress-bar-val").style.width = "100%";
                    document.getElementById("stat-val-pages-left").textContent = "Sem páginas pendentes";
                    document.getElementById("stat-val-detail").textContent = "0 / 0";
                }
            } catch (e) {
                console.error("Failed to load stats", e);
            }
        }

        loadStats();
        // Poll stats every 5 seconds for real-time progress monitoring
        setInterval(loadStats, 5000);

        // Trigger clicks
        btnSelectFiles.addEventListener("click", (e) => {
            e.stopPropagation();
            fileInput.click();
        });
        btnSelectFolder.addEventListener("click", (e) => {
            e.stopPropagation();
            folderInput.click();
        });
        dropzone.addEventListener("click", () => fileInput.click());

        // Drag & Drop
        dropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        });
        dropzone.addEventListener("dragleave", () => {
            dropzone.classList.remove("dragover");
        });
        dropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
            const files = e.dataTransfer.files;
            handleFilesUpload(files);
        });

        fileInput.addEventListener("change", (e) => {
            handleFilesUpload(e.target.files);
        });
        folderInput.addEventListener("change", (e) => {
            handleFilesUpload(e.target.files, true);
        });

        // Upload handler
        async function handleFilesUpload(files, isFolder = false) {
            if (files.length === 0) return;

            queueDiv.style.display = "block";
            queueDiv.innerHTML = "";
            progressWrapper.style.display = "block";
            progressBar.style.width = "0%";

            const formData = new FormData();

            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                formData.append("files", file);
                
                // Keep relative folder path if folder upload
                const path = isFolder ? file.webkitRelativePath : file.name;
                formData.append("paths", path);

                // Add to visible queue list
                const item = document.createElement("div");
                item.className = "queue-item";
                item.innerHTML = `<span>📄 ${path}</span> <span style="color: var(--text-tertiary);">A carregar...</span>`;
                queueDiv.appendChild(item);
            }

            try {
                // Upload via XHR for progress event
                const xhr = new XMLHttpRequest();
                xhr.open("POST", "/upload", true);

                xhr.upload.addEventListener("progress", (e) => {
                    if (e.lengthComputable) {
                        const percent = Math.round((e.loaded / e.total) * 100);
                        progressBar.style.width = `${percent}%`;
                    }
                });

                xhr.onload = () => {
                    if (xhr.status === 200) {
                        progressBar.style.width = "100%";
                        setTimeout(() => {
                            progressWrapper.style.display = "none";
                            queueDiv.style.display = "none";
                            loadStats();
                            alert("Ficheiros carregados com sucesso para a pasta entrada/!");
                        }, 1000);
                    } else {
                        alert("Ocorreu um erro ao carregar ficheiros.");
                    }
                };

                xhr.send(formData);

            } catch (e) {
                console.error(e);
                alert("Upload falhou.");
            }
        }

        // Run Pipeline trigger & status polling
        let isPollingPipeline = false;
        
        async function checkPipelineStatus() {
            try {
                const res = await fetch("/pipeline-status");
                const data = await res.json();
                
                if (data.logs) {
                    consoleDiv.style.display = "block";
                    consoleDiv.textContent = data.logs;
                    consoleDiv.scrollTop = consoleDiv.scrollHeight;
                }
                
                if (data.running) {
                    btnRunPipeline.disabled = true;
                    btnRunPipeline.textContent = "⏳ Processamento em curso...";
                    if (!isPollingPipeline) {
                        isPollingPipeline = true;
                        startPollingPipeline();
                    }
                } else {
                    if (btnRunPipeline.disabled && btnRunPipeline.textContent.includes("curso")) {
                        btnRunPipeline.disabled = false;
                        btnRunPipeline.textContent = "🚀 Executar Pipeline de Processamento";
                        loadStats();
                        loadExplorer();
                    }
                    isPollingPipeline = false;
                }
            } catch (e) {
                console.error("Failed to check pipeline status:", e);
            }
        }
        
        function startPollingPipeline() {
            const interval = setInterval(async () => {
                await checkPipelineStatus();
                if (!isPollingPipeline) {
                    clearInterval(interval);
                }
            }, 1500);
        }
        
        btnRunPipeline.addEventListener("click", async () => {
            btnRunPipeline.disabled = true;
            btnRunPipeline.textContent = "⏳ A iniciar...";
            consoleDiv.style.display = "block";
            consoleDiv.textContent = ">>> A iniciar o pipeline de processamento...\n";
            
            try {
                const res = await fetch("/run-pipeline", { method: "POST" });
                const result = await res.json();
                
                if (result.status === "started" || result.status === "already_running") {
                    isPollingPipeline = true;
                    startPollingPipeline();
                } else {
                    alert("Erro ao iniciar pipeline: " + result.message);
                    btnRunPipeline.disabled = false;
                    btnRunPipeline.textContent = "🚀 Executar Pipeline de Processamento";
                }
            } catch (e) {
                console.error("Failed to start pipeline:", e);
                alert("Falha ao comunicar com o servidor.");
                btnRunPipeline.disabled = false;
                btnRunPipeline.textContent = "🚀 Executar Pipeline de Processamento";
            }
        });
        
        // Initial status check on page load
        checkPipelineStatus();

        // --- FILE EXPLORER CLIENT SIDE ---
        const explorerTbody = document.getElementById("explorer-tbody");
        const explorerSearchInput = document.getElementById("explorer-search");
        
        // Modals
        const renameModal = document.getElementById("rename-modal");
        const renameDocIdInput = document.getElementById("rename-doc-id");
        const renameInput = document.getElementById("rename-input");
        const btnCancelRename = document.getElementById("btn-cancel-rename");
        const btnSaveRename = document.getElementById("btn-save-rename");
        
        const moveModal = document.getElementById("move-modal");
        const moveDocIdInput = document.getElementById("move-doc-id");
        const moveUcSelect = document.getElementById("move-uc-select");
        const moveTipoSelect = document.getElementById("move-tipo-select");
        const moveAnoSelect = document.getElementById("move-ano-select");
        const moveSemestreSelect = document.getElementById("move-semestre-select");
        const btnCancelMove = document.getElementById("btn-cancel-move");
        const btnSaveMove = document.getElementById("btn-save-move");
        
        let allDocsList = [];
        
        const TIPO_LABELS = {
            "teoria": "Slides e Teoria",
            "fichas-exercicios": "Fichas de Exercícios",
            "resumos": "Resumos",
            "resolucoes": "Resoluções",
            "testes-exames": "Testes e Exames",
            "trabalhos-projetos": "Trabalhos e Projetos"
        };
        
        const UC_OPTIONS = {
            "analise-matematica": "Análise Matemática",
            "algebra-linear": "Álgebra Linear",
            "fisica": "Física",
            "programacao": "Programação",
            "ingles": "Inglês",
            "quimica-e-materiais": "Química e Materiais",
            "matematica-aplicada": "Matemática Aplicada",
            "estatistica": "Estatística",
            "desenho-tecnico": "Desenho Técnico",
            "tecnologia-dos-materiais": "Tecnologia dos Materiais",
            "tecnologia-mecanica-i": "Tecnologia Mecânica I",
            "mecanica-aplicada": "Mecânica Aplicada",
            "resistencia-dos-materiais": "Resistência dos Materiais",
            "tecnologia-mecanica-ii": "Tecnologia Mecânica II",
            "termodinamica": "Termodinâmica",
            "mecanica-dos-fluidos": "Mecânica dos Fluidos",
            "processos-transformacao-plasticos": "Processos de Transformação de Plásticos",
            "modelacao-assistida-por-computador": "Modelação Assistida por Computador",
            "orgaos-de-maquinas-i": "Órgãos de Máquinas I",
            "processamento-mecanica-compositos": "Processamento e Mecânica de Compósitos",
            "engenharia-assistida-por-computador": "Engenharia Assistida por Computador",
            "fabrico-assistido-por-computador": "Fabrico Assistido por Computador",
            "desenho-de-construcao-mecanica": "Desenho de Construção Mecânica",
            "desenho-de-moldes-e-plasticos": "Desenho de Moldes e Plásticos",
            "eletrotecnia-e-eletronica-industrial": "Eletrotecnia e Eletrónica Industrial",
            "orgaos-de-maquinas-ii": "Órgãos de Máquinas II",
            "processos-avancados-de-fabrico": "Processos Avançados de Fabrico",
            "projeto-mecanico": "Projeto Mecânico",
            "projeto-de-moldes": "Projeto de Moldes",
            "concecao-e-desenvolvimento-de-produto": "Conceção e Desenvolvimento de Produto",
            "simulacao-computacional-projeto-mecanico": "Simulação Computacional de Projeto Mecânico",
            "automacao-industrial": "Automação Industrial",
            "qualidade-e-gestao-de-recursos": "Qualidade e Gestão de Recursos",
            "gestao-da-producao-e-manutencao": "Gestão da Produção e Manutenção",
            "estagio": "Estágio",
            "seminario": "Seminário",
            "controlo-de-gestao": "Controlo de Gestão",
            "redes-de-fluidos": "Redes de Fluidos",
            "inovacao-e-empreendedorismo": "Inovação e Empreendedorismo"
        };
        
        function populateUcSelects() {
            moveUcSelect.innerHTML = Object.entries(UC_OPTIONS).map(([slug, name]) => `
                <option value="${slug}">${name}</option>
            `).join('');
        }
        
        async function loadExplorer(searchQuery = "") {
            try {
                const res = await fetch(`/docs-list?q=${encodeURIComponent(searchQuery)}`);
                allDocsList = await res.json();
                renderExplorerTable(allDocsList);
            } catch (e) {
                console.error("Failed to load File Explorer", e);
                explorerTbody.innerHTML = `<tr><td colspan="6" style="padding: 24px; text-align: center; color: var(--danger);">Erro ao carregar documentos.</td></tr>`;
            }
        }
        
        function renderExplorerTable(docs) {
            if (docs.length === 0) {
                explorerTbody.innerHTML = `<tr><td colspan="6" style="padding: 24px; text-align: center; color: var(--text-tertiary);">Nenhum documento encontrado.</td></tr>`;
                return;
            }
            
            explorerTbody.innerHTML = docs.map(doc => {
                const filepath = doc.path_original;
                const filename = filepath.split(/[\\\\/]/).pop();
                const cleanName = filename.replace(/\.[^/.]+$/, "");
                const ucLabel = UC_OPTIONS[doc.disciplina] || doc.disciplina;
                const catLabel = TIPO_LABELS[doc.tipo] || doc.tipo;
                
                let badgeClass = "badge-success";
                let statusLabel = doc.status;
                if (doc.status === "pending") {
                    badgeClass = "badge-danger";
                    statusLabel = "Pendente";
                } else if (doc.status === "inventory_done") {
                    badgeClass = "badge-warning";
                    statusLabel = "Inventariado";
                } else if (doc.status === "convert_done") {
                    badgeClass = "badge-warning";
                    statusLabel = "Convertido";
                } else if (doc.status === "ocr_done") {
                    badgeClass = "badge-warning";
                    statusLabel = "OCR Feito";
                } else if (doc.status === "validated") {
                    badgeClass = "badge-success";
                    statusLabel = "Validado";
                } else if (doc.status === "exported") {
                    badgeClass = "badge-success";
                    statusLabel = "Exportado";
                }
                
                const originalLink = doc.storage_url ? 
                    `<a href="${doc.storage_url}" target="_blank" style="color: var(--accent); text-decoration: none; font-weight: 500;">📥 ${filename}</a>` :
                    `<span style="color: var(--text-primary); font-weight: 500;">📄 ${filename}</span>`;
                
                return `
                    <tr style="border-bottom: 1px solid var(--panel-border);">
                        <td style="padding: 10px 8px; font-family: var(--font-body);">${originalLink}</td>
                        <td style="padding: 10px 8px; color: var(--text-secondary);">${ucLabel}</td>
                        <td style="padding: 10px 8px; color: var(--text-secondary);">${catLabel}</td>
                        <td style="padding: 10px 8px; color: var(--text-secondary); font-family: var(--font-mono);">${doc.ano}ºA / ${doc.semestre}ºS</td>
                        <td style="padding: 10px 8px;"><span class="badge ${badgeClass}">${statusLabel}</span></td>
                        <td style="padding: 10px 8px; text-align: right; white-space: nowrap;">
                            <button onclick="openRenameModal('${doc.id}', '${cleanName}')" class="btn-secondary" style="padding: 4px 8px; font-size: 0.78rem; margin-right: 4px; cursor: pointer;">✏️ Renomear</button>
                            <button onclick="openMoveModal('${doc.id}', '${doc.disciplina}', '${doc.tipo}', ${doc.ano}, ${doc.semestre})" class="btn-secondary" style="padding: 4px 8px; font-size: 0.78rem; margin-right: 4px; cursor: pointer;">📦 Mover</button>
                            <button onclick="deleteDocument('${doc.id}', '${filename}')" class="btn-secondary" style="padding: 4px 8px; font-size: 0.78rem; border-color: var(--danger); color: var(--danger); cursor: pointer;">🗑️ Excluir</button>
                        </td>
                    </tr>
                `;
            }).join('');
        }
        
        let searchTimeout = null;
        explorerSearchInput.addEventListener("input", (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                loadExplorer(e.target.value);
            }, 300);
        });
        
        window.openRenameModal = function(docId, name) {
            renameDocIdInput.value = docId;
            renameInput.value = name;
            renameModal.style.display = "flex";
        };
        
        btnCancelRename.addEventListener("click", () => {
            renameModal.style.display = "none";
        });
        
        btnSaveRename.addEventListener("click", async () => {
            const docId = renameDocIdInput.value;
            const newName = renameInput.value.trim();
            if (!newName) return;
            
            btnSaveRename.disabled = true;
            btnSaveRename.textContent = "A salvar...";
            
            try {
                const res = await fetch("/rename-document", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ doc_id: docId, new_name: newName })
                });
                const result = await res.json();
                if (result.status === "success") {
                    renameModal.style.display = "none";
                    loadExplorer(explorerSearchInput.value);
                    loadStats();
                } else {
                    alert("Erro: " + result.message);
                }
            } catch (e) {
                alert("Falha ao ligar ao servidor.");
            } finally {
                btnSaveRename.disabled = false;
                btnSaveRename.textContent = "Salvar";
            }
        });
        
        window.openMoveModal = function(docId, uc, tipo, ano, semestre) {
            moveDocIdInput.value = docId;
            moveUcSelect.value = uc || "analise-matematica";
            moveTipoSelect.value = tipo || "teoria";
            moveAnoSelect.value = ano || "1";
            moveSemestreSelect.value = semestre || "1";
            moveModal.style.display = "flex";
        };
        
        btnCancelMove.addEventListener("click", () => {
            moveModal.style.display = "none";
        });
        
        btnSaveMove.addEventListener("click", async () => {
            const docId = moveDocIdInput.value;
            const uc = moveUcSelect.value;
            const tipo = moveTipoSelect.value;
            const ano = moveAnoSelect.value;
            const semestre = moveSemestreSelect.value;
            
            btnSaveMove.disabled = true;
            btnSaveMove.textContent = "A mover...";
            
            try {
                const res = await fetch("/move-document", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        doc_id: docId,
                        new_uc: uc,
                        new_tipo: tipo,
                        new_ano: ano,
                        new_semestre: semestre
                    })
                });
                const result = await res.json();
                if (result.status === "success") {
                    moveModal.style.display = "none";
                    loadExplorer(explorerSearchInput.value);
                    loadStats();
                } else {
                    alert("Erro: " + result.message);
                }
            } catch (e) {
                alert("Falha ao ligar ao servidor.");
            } finally {
                btnSaveMove.disabled = false;
                btnSaveMove.textContent = "Mover";
            }
        });
        
        window.deleteDocument = async function(docId, filename) {
            if (!confirm(`Tens a certeza que desejas excluir o ficheiro "${filename}"?\nEsta ação apagará o ficheiro físico, os dados da base de dados e a página no portal web.`)) {
                return;
            }
            
            try {
                const res = await fetch("/delete-document", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ doc_id: docId })
                });
                const result = await res.json();
                if (result.status === "success") {
                    loadExplorer(explorerSearchInput.value);
                    loadStats();
                } else {
                    alert("Erro ao excluir: " + result.message);
                }
            } catch (e) {
                alert("Falha ao ligar ao servidor.");
            }
        };
        
        // Initialize File Explorer
        populateUcSelects();
        loadExplorer();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/stats")
def stats():
    try:
        conn = get_db_connection()
        docs = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        pages = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
        
        # Count pending conversion or ocr
        pending = conn.execute("SELECT count(*) FROM documents WHERE status != 'exported' AND status != 'failed'").fetchone()[0]
        exported = conn.execute("SELECT count(*) FROM documents WHERE status = 'exported'").fetchone()[0]
        
        # Detailed OCR stats
        ocr_done = conn.execute("SELECT count(*) FROM pages WHERE needs_ocr = 1 AND ocr_status = 'done'").fetchone()[0]
        ocr_pending = conn.execute("SELECT count(*) FROM pages WHERE needs_ocr = 1 AND ocr_status = 'pending'").fetchone()[0]
        ocr_failed = conn.execute("SELECT count(*) FROM pages WHERE needs_ocr = 1 AND ocr_status = 'failed'").fetchone()[0]
        
        # Detailed Validation stats
        val_done = conn.execute("SELECT count(*) FROM pages WHERE needs_ocr = 1 AND validation_status = 'done'").fetchone()[0]
        val_pending = conn.execute("SELECT count(*) FROM pages WHERE needs_ocr = 1 AND validation_status = 'pending'").fetchone()[0]
        val_failed = conn.execute("SELECT count(*) FROM pages WHERE needs_ocr = 1 AND validation_status = 'failed'").fetchone()[0]
        
        conn.close()
    except Exception:
        docs, pages, pending, exported = 0, 0, 0, 0
        ocr_done, ocr_pending, ocr_failed = 0, 0, 0
        val_done, val_pending, val_failed = 0, 0, 0
        
    return jsonify({
        "docs": docs,
        "pages": pages,
        "pending": pending,
        "exported": exported,
        "ocr_done": ocr_done,
        "ocr_pending": ocr_pending,
        "ocr_failed": ocr_failed,
        "val_done": val_done,
        "val_pending": val_pending,
        "val_failed": val_failed
    })

@app.route("/docs-list", methods=["GET"])
def docs_list():
    query = request.args.get("q", "").strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if query:
        cursor.execute(
            """
            SELECT id, path_original, disciplina, tipo, ano, semestre, status, storage_url 
            FROM documents 
            WHERE path_original LIKE ?
            ORDER BY path_original ASC
            """,
            (f"%{query}%",)
        )
    else:
        cursor.execute(
            """
            SELECT id, path_original, disciplina, tipo, ano, semestre, status, storage_url 
            FROM documents 
            ORDER BY path_original ASC
            """
        )
    docs = cursor.fetchall()
    conn.close()
    
    return jsonify([dict(doc) for doc in docs])

@app.route("/delete-document", methods=["POST"])
def delete_document():
    data = request.json
    doc_id = data.get("doc_id")
    if not doc_id:
        return jsonify({"status": "error", "message": "Falta o ID do documento."}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT path_original, disciplina, tipo, ano, semestre FROM documents WHERE id = ?", (doc_id,))
        doc = cursor.fetchone()
        
        if not doc:
            conn.close()
            return jsonify({"status": "error", "message": "Documento não encontrado."}), 404
            
        filepath = doc["path_original"]
        ano = int(doc["ano"]) if doc["ano"] is not None else 1
        semestre = int(doc["semestre"]) if doc["semestre"] is not None else 1
        disciplina = doc["disciplina"] if doc["disciplina"] else "desconhecido"
        tipo = doc["tipo"] if doc["tipo"] else "teoria"
        
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting physical file: {e}")
                
        cursor.execute("DELETE FROM pages WHERE doc_id = ?", (doc_id,))
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
        
        base_name = os.path.splitext(os.path.basename(filepath))[0].replace("#", "_").replace("?", "_")
        dest_dir = os.path.join(
            BASE_DIR, "web", "src", "content", "biblioteca",
            f"{ano}-ano", f"{semestre}-semestre", disciplina, tipo
        )
        for ext in [".md", ".meta.json"]:
            astro_f = os.path.join(dest_dir, base_name + ext)
            if os.path.exists(astro_f):
                try:
                    os.remove(astro_f)
                except Exception as e:
                    print(f"Error deleting Astro file: {e}")
                    
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/rename-document", methods=["POST"])
def rename_document():
    data = request.json
    doc_id = data.get("doc_id")
    new_name = data.get("new_name", "").strip()
    
    if not doc_id or not new_name:
        return jsonify({"status": "error", "message": "Parâmetros inválidos."}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT path_original, disciplina, tipo, ano, semestre FROM documents WHERE id = ?", (doc_id,))
        doc = cursor.fetchone()
        
        if not doc:
            conn.close()
            return jsonify({"status": "error", "message": "Documento não encontrado."}), 404
            
        old_path = doc["path_original"]
        old_dir = os.path.dirname(old_path)
        old_ext = os.path.splitext(old_path)[1]
        
        new_filename = new_name + old_ext
        new_path = os.path.join(old_dir, new_filename)
        
        if os.path.exists(old_path):
            try:
                os.rename(old_path, new_path)
            except Exception as e:
                print(f"Error renaming file physically: {e}")
                
        cursor.execute("UPDATE documents SET path_original = ? WHERE id = ?", (new_path, doc_id))
        
        old_base = os.path.splitext(os.path.basename(old_path))[0].replace('#', '_').replace('?', '_')
        old_dest_dir = os.path.join(
            BASE_DIR, "web", "src", "content", "biblioteca",
            f"{doc['ano']}-ano", f"{doc['semestre']}-semestre", doc["disciplina"], doc["tipo"]
        )
        for ext_f in [".md", ".meta.json"]:
            f_path = os.path.join(old_dest_dir, old_base + ext_f)
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except Exception as e:
                    print(f"Error removing old Astro file: {e}")
                    
        regenerate_astro_files_for_doc(doc_id, cursor)
        
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/move-document", methods=["POST"])
def move_document():
    data = request.json
    doc_id = data.get("doc_id")
    new_uc = data.get("new_uc")
    new_tipo = data.get("new_tipo")
    new_ano = int(data.get("new_ano"))
    new_semestre = int(data.get("new_semestre"))
    
    if not doc_id or not new_uc or not new_tipo:
        return jsonify({"status": "error", "message": "Parâmetros inválidos."}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT path_original, disciplina, tipo, ano, semestre FROM documents WHERE id = ?", (doc_id,))
        doc = cursor.fetchone()
        
        if not doc:
            conn.close()
            return jsonify({"status": "error", "message": "Documento não encontrado."}), 404
            
        old_path = doc["path_original"]
        
        old_base = os.path.splitext(os.path.basename(old_path))[0].replace('#', '_').replace('?', '_')
        old_dest_dir = os.path.join(
            BASE_DIR, "web", "src", "content", "biblioteca",
            f"{doc['ano']}-ano", f"{doc['semestre']}-semestre", doc["disciplina"], doc["tipo"]
        )
        for ext_f in [".md", ".meta.json"]:
            f_path = os.path.join(old_dest_dir, old_base + ext_f)
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except Exception as e:
                    print(f"Error removing old Astro file: {e}")
                    
        cursor.execute(
            """
            UPDATE documents 
            SET disciplina = ?, tipo = ?, ano = ?, semestre = ?
            WHERE id = ?
            """,
            (new_uc, new_tipo, new_ano, new_semestre, doc_id)
        )
        
        regenerate_astro_files_for_doc(doc_id, cursor)
        
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    paths = request.form.getlist("paths")
    
    for file, path in zip(files, paths):
        # Prevent path traversal vulnerabilities
        clean_path = path.replace("../", "").replace("..\\", "")
        dest_path = os.path.join(INPUT_DIR, clean_path)
        
        # Ensure parent folder exists
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Save file
        file.save(dest_path)
        print(f"Ingested file: {dest_path}")
        
    return jsonify({"status": "success", "count": len(files)})

active_process = None
active_log_file = os.path.join(BASE_DIR, "pipeline_run.log")

@app.route("/run-pipeline", methods=["GET", "POST"])
def run_pipeline():
    global active_process
    if active_process is not None and active_process.poll() is None:
        return jsonify({"status": "already_running"})
        
    try:
        with open(active_log_file, "w", encoding="utf-8") as f:
            f.write(">>> A iniciar o pipeline de processamento...\n\n")
            
        log_f = open(active_log_file, "a", encoding="utf-8")
        python_exe = sys.executable
        pipeline_script = os.path.join(os.path.dirname(__file__), "run_pipeline.py")
        
        env_vars = os.environ.copy()
        env_vars["PYTHONIOENCODING"] = "utf-8"
        active_process = subprocess.Popen(
            [python_exe, "-u", pipeline_script],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=BASE_DIR,
            env=env_vars
        )
        
        def monitor_process(proc, f_handle):
            proc.wait()
            f_handle.close()
            print("Pipeline background process completed.")
            
        import threading
        threading.Thread(target=monitor_process, args=(active_process, log_f), daemon=True).start()
        
        return jsonify({"status": "started"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/pipeline-status", methods=["GET"])
def pipeline_status():
    global active_process
    is_running = active_process is not None and active_process.poll() is None
    
    log_content = ""
    if os.path.exists(active_log_file):
        try:
            with open(active_log_file, "r", encoding="utf-8") as f:
                log_content = f.read()
        except Exception as e:
            log_content = f"Erro ao ler log: {e}"
            
    return jsonify({
        "running": is_running,
        "logs": log_content
    })

@app.route("/build-site", methods=["POST"])
def build_site():
    from deploy import deploy
    return Response(deploy(), mimetype="text/plain")

if __name__ == "__main__":
    import webbrowser
    from threading import Timer
    
    # Automatically open web browser to the port
    def open_browser():
        webbrowser.open_new("http://localhost:5000")
        
    Timer(1.5, open_browser).start()
    
    print("Starting Ingestion UI App on http://localhost:5000...")
    app.run(host="localhost", port=5000, debug=False)
