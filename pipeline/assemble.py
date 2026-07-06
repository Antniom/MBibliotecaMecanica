import sys
import os
import sqlite3
import json
from datetime import datetime

# Force stdout/stderr to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from db_utils import get_db_connection, log_api_usage

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Define target output directory for Astro content collections
WEB_CONTENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "content", "biblioteca"
)

class AssembleResult(BaseModel):
    title: str = Field(description="A clean, descriptive title for the document based on content.")
    markdown_content: str = Field(description="The full merged markdown text wrapped in <document> and <section> tags.")

def get_gemini_client():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")
    return genai.Client(api_key=GEMINI_API_KEY)

def assemble_pdf_document(client, doc_title_approx, pages_data):
    """Calls Gemini to assemble multiple page transcripts into a clean structured document."""
    # Format pages content
    pages_input = []
    for p in pages_data:
        pages_input.append(f"--- PAGE {p['page_num']} ---\n{p['validated_text']}")
    
    full_pages_text = "\n\n".join(pages_input)
    
    prompt = f"""
We have validated page transcripts for a mechanical engineering document tentatively titled '{doc_title_approx}'.
Merge these pages into a single cohesive markdown document.

Format requirements:
1. Output MUST be wrapped in a single root `<document>` tag.
2. Divide the content into logical sections based on topic/exercise using `<section topic="topic-slug" page="page-number">` tags.
3. Keep all mathematical formulas formatted in LaTeX:
   - Use \\( ... \\) for inline math.
   - Use \\[ ... \\] for block math.
4. Keep table structures and handwritten blocks (e.g. `<handwritten confidence="X.XX">`).
5. Ensure a logical, continuous reading flow, cleaning up duplicate header text or page margins.

Transcripts to merge:
{full_pages_text}

Return the result as a structured JSON object.
"""

    try:
        print(f"Calling Gemini ({GEMINI_MODEL}) to assemble document...")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AssembleResult,
                temperature=0.2
            )
        )
        # Log usage (approx 1 token per 4 chars)
        log_api_usage("gemini_flash", tokens_used=len(prompt) // 4 + len(response.text) // 4)
        
        result = response.parsed
        return result.title, result.markdown_content
    except Exception as e:
        print(f"Gemini assembly failed: {e}")
        return doc_title_approx, None

def write_document_files(doc_meta, markdown_body):
    """Writes the .md and .meta.json files under the correct taxonomy directory."""
    ano = int(doc_meta['ano']) if doc_meta['ano'] is not None and str(doc_meta['ano']).isdigit() else 1
    semestre = int(doc_meta['semestre']) if doc_meta['semestre'] is not None and str(doc_meta['semestre']).isdigit() else 1
    disciplina = doc_meta["disciplina"] if doc_meta["disciplina"] else "desconhecido"
    tipo = doc_meta["tipo"] if doc_meta["tipo"] else "teoria"

    # Taxonomy path: biblioteca/{ano}-ano/{semestre}-semestre/{disciplina}/{tipo}/
    dest_dir = os.path.join(
        WEB_CONTENT_DIR,
        f"{ano}-ano",
        f"{semestre}-semestre",
        disciplina,
        tipo
    )
    os.makedirs(dest_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(doc_meta["path_original"]))[0]
    base_name = base_name.replace("#", "_").replace("?", "_")
    
    # MD file contents (including Frontmatter)
    md_content = f"""---
title: "{doc_meta['title']}"
disciplina: "{disciplina}"
ano: {ano}
semestre: {semestre}
tipo: "{tipo}"
fonte_original: "{os.path.basename(doc_meta['path_original'])}"
confianca_media: {doc_meta['confianca_media']:.2f}
data_processamento: "{datetime.now().strftime('%Y-%m-%d')}"
storage_url: "{doc_meta['storage_url'] or ''}"
hash: "{doc_meta['id']}"
---

{markdown_body}
"""

    md_path = os.path.join(dest_dir, f"{base_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    # Meta JSON file contents
    meta_path = os.path.join(dest_dir, f"{base_name}.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(doc_meta, f, indent=2, ensure_ascii=False)
        
    print(f"Saved documents to: {md_path}")

def run_assembly():
    """Runs Phase 5: Geração do documento interno final."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Find convert_done documents
    cursor.execute("SELECT id, path_original, disciplina, tipo, ano, semestre, storage_release_tag, storage_url FROM documents WHERE status = 'convert_done'")
    docs = cursor.fetchall()
    
    if not docs:
        print("No documents pending assembly.")
        conn.close()
        return

    client = None
    
    for doc in docs:
        doc_id = doc["id"]
        filepath = doc["path_original"]
        
        # Check if all pages are validated
        cursor.execute("SELECT page_num, validated_text, confidence, needs_ocr FROM pages WHERE doc_id = ?", (doc_id,))
        pages = cursor.fetchall()
        
        if not pages:
            # Document has no pages (unconvertible file type)
            print(f"Document has no extractable pages (non-convertible). Generating empty placeholder meta for {os.path.basename(filepath)}")
            doc_meta = {
                "id": doc_id,
                "title": os.path.splitext(os.path.basename(filepath))[0],
                "path_original": filepath,
                "disciplina": doc["disciplina"],
                "tipo": doc["tipo"],
                "ano": doc["ano"],
                "semestre": doc["semestre"],
                "storage_release_tag": doc["storage_release_tag"],
                "storage_url": doc["storage_url"],
                "confianca_media": 1.0,
                "assembled_at": datetime.now().isoformat()
            }
            write_document_files(doc_meta, f"<document>\n  <!-- Non-convertible file of type {os.path.splitext(filepath)[1]} -->\n</document>")
            cursor.execute("UPDATE documents SET status = 'exported' WHERE id = ?", (doc_id,))
            conn.commit()
            continue
            
        # Check if all pages are done
        cursor.execute("SELECT COUNT(*) as cnt FROM pages WHERE doc_id = ? AND validation_status != 'done'", (doc_id,))
        pending_cnt = cursor.fetchone()["cnt"]
        
        if pending_cnt > 0:
            print(f"Skipping assembly for {os.path.basename(filepath)} - {pending_cnt} page(s) still pending validation.")
            continue
            
        # Reaching here means all pages are validated!
        print(f"\nProcessing Assembly for: {os.path.basename(filepath)}")
        
        pages_list = [dict(p) for p in pages]
        pages_list.sort(key=lambda x: x["page_num"])
        
        # Calculate average confidence
        conf_sum = sum(p["confidence"] for p in pages_list)
        conf_avg = conf_sum / len(pages_list)
        
        doc_title_approx = os.path.splitext(os.path.basename(filepath))[0].replace("-", " ").title()
        
        # Check if native (no pages needed OCR)
        any_ocr_needed = any(p["needs_ocr"] == 1 for p in pages_list)
        
        if not any_ocr_needed:
            # Bypassing Gemini Assembly for native docs to save tokens/cost
            print("Document is fully native. Assembling programmatically.")
            title = doc_title_approx
            
            # Simple wrapper
            markdown_body = "<document>\n"
            for p in pages_list:
                markdown_body += f"  <section topic=\"geral\" page=\"{p['page_num']}\">\n"
                # Indent lines slightly
                lines = p["validated_text"].split("\n")
                markdown_body += "\n".join("    " + l for l in lines) + "\n"
                markdown_body += "  </section>\n"
            markdown_body += "</document>"
        else:
            # PDF contains scans. Use Gemini to assemble if API key is present, else stitch programmatically
            if GEMINI_API_KEY:
                if not client:
                    try:
                        client = get_gemini_client()
                    except ValueError as e:
                        print(e)
                        conn.close()
                        return
                title, markdown_body = assemble_pdf_document(client, doc_title_approx, pages_list)
            else:
                print("GEMINI_API_KEY not found in environment. Falling back to programmatic stitching.")
                title = doc_title_approx
                markdown_body = "<document>\n"
                for p in pages_list:
                    markdown_body += f"  <section topic=\"scanned\" page=\"{p['page_num']}\">\n"
                    # Indent lines slightly
                    lines = p["validated_text"].split("\n") if p["validated_text"] else []
                    markdown_body += "\n".join("    " + l for l in lines) + "\n"
                    markdown_body += "  </section>\n"
                markdown_body += "</document>"
            
            if not markdown_body:
                print("Failed to assemble. Will retry next time.")
                continue

        # Prepare meta dict
        doc_meta = {
            "id": doc_id,
            "title": title,
            "path_original": filepath,
            "disciplina": doc["disciplina"],
            "tipo": doc["tipo"],
            "ano": doc["ano"],
            "semestre": doc["semestre"],
            "storage_release_tag": doc["storage_release_tag"],
            "storage_url": doc["storage_url"],
            "confianca_media": conf_avg,
            "assembled_at": datetime.now().isoformat()
        }
        
        write_document_files(doc_meta, markdown_body)
        
        cursor.execute("UPDATE documents SET status = 'exported' WHERE id = ?", (doc_id,))
        conn.commit()
        print(f"Document {os.path.basename(filepath)} fully assembled and set to 'exported'.")

    conn.close()
    print("Assembly batch finished.")

if __name__ == "__main__":
    run_assembly()
