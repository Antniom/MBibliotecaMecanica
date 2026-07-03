import os
import sqlite3
import json
from datetime import datetime
from db_utils import get_db_connection

WEB_CONTENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "web", "src", "content", "biblioteca"
)

def make_placeholders():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Select all documents
    cursor.execute(
        "SELECT id, path_original, disciplina, tipo, ano, semestre, storage_release_tag, storage_url, status FROM documents"
    )
    docs = cursor.fetchall()
    
    print(f"Generating placeholders for {len(docs)} documents...")
    count = 0
    for doc in docs:
        doc_id = doc["id"]
        filepath = doc["path_original"]
        
        # Schema safety conversions
        ano = int(doc["ano"]) if doc["ano"] is not None and str(doc["ano"]).isdigit() else 1
        semestre = int(doc["semestre"]) if doc["semestre"] is not None and str(doc["semestre"]).isdigit() else 1
        disciplina = doc["disciplina"] if doc["disciplina"] else "desconhecido"
        tipo = doc["tipo"] if doc["tipo"] else "teoria"
        
        dest_dir = os.path.join(
            WEB_CONTENT_DIR,
            f"{ano}-ano",
            f"{semestre}-semestre",
            disciplina,
            tipo
        )
        
        # Sanitize basename to avoid Vite glob ENOENT errors on special characters (#, ?)
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        base_name = base_name.replace("#", "_").replace("?", "_")
        
        md_path = os.path.join(dest_dir, f"{base_name}.md")
        meta_path = os.path.join(dest_dir, f"{base_name}.meta.json")
        
        # If files already exist, don't overwrite them (keep the rich AI transcripts!)
        if os.path.exists(md_path) and os.path.exists(meta_path):
            continue
            
        os.makedirs(dest_dir, exist_ok=True)
        
        # Generate placeholder doc_meta
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
            "confianca_media": 0.0,
            "assembled_at": datetime.now().isoformat()
        }
        
        markdown_body = f"""<document>
  <section topic="geral" page="1">
    O processamento de inteligência artificial (OCR e Validação) para este documento está na fila de espera.
    O ficheiro original está disponível para download.
  </section>
</document>"""
        
        # Write files
        md_content = f"""---
title: "{doc_meta['title']}"
disciplina: "{doc_meta['disciplina']}"
ano: {doc_meta['ano']}
semestre: {doc_meta['semestre']}
tipo: "{doc_meta['tipo']}"
fonte_original: "{os.path.basename(doc_meta['path_original'])}"
confianca_media: {doc_meta['confianca_media']:.2f}
data_processamento: "{datetime.now().strftime('%Y-%m-%d')}"
storage_url: "{doc_meta['storage_url'] or ''}"
hash: "{doc_meta['id']}"
---

{markdown_body}
"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(doc_meta, f, indent=2, ensure_ascii=False)
            
        count += 1
        if count % 1000 == 0:
            print(f"Generated {count} placeholders...")
            
    conn.close()
    print(f"Finished generating {count} placeholder documents.")

if __name__ == "__main__":
    make_placeholders()
