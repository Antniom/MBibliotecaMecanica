import sys
import os
import sqlite3
import time
import threading
from datetime import datetime

# Force stdout/stderr to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add current folder to path to allow direct imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db_utils import get_db_connection
from inventory import run_inventory
from convert import process_pdf, process_native_office
from ocr import ensure_ollama_and_model, get_page_pixmap, run_ollama_ocr, run_paddle_ocr
from validate import get_gemini_client, validate_page
from assemble import assemble_pdf_document, write_document_files
from deploy import deploy

def start_background_uploader():
    from upload_assets import run_uploads
    def uploader_loop():
        print("\n" + "#"*50)
        print("[BACKGROUND UPLOADER] Background upload worker started in parallel!")
        print("#"*50 + "\n")
        try:
            run_uploads()
        except Exception as e:
            print(f"\n[BACKGROUND UPLOADER ERROR] {e}\n")
        print("\n[BACKGROUND UPLOADER] Finished current background upload batch.\n")
        
    t = threading.Thread(target=uploader_loop, daemon=True)
    t.start()

def main():
    print("="*60)
    print("   SUPER-BIBLIOTECA DE ENGENHARIA MECÂNICA PIPELINE RUN   ")
    print("="*60)

    # 1. Run Inventory (Phase 1)
    print("\n[STEP 1] Running Inventory & Classification...")
    run_inventory()

    # Start parallel background uploader for all original files
    start_background_uploader()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure Ollama is running and model is pulled (Phase 3 setup)
    ensure_ollama_and_model()

    # Prepare Gemini client (Phase 4 setup)
    gemini_client = None
    try:
        gemini_client = get_gemini_client()
    except Exception as e:
        print(f"Gemini Client not initialized: {e}")

    # Track exported documents during this run
    exported_count = 0
    gemini_rate_limited = False

    # Get all active documents
    cursor.execute(
        """
        SELECT id, path_original, status, disciplina, tipo, ano, semestre, storage_release_tag, storage_url
        FROM documents 
        WHERE status NOT IN ('exported', 'failed')
        """
    )
    documents = cursor.fetchall()
    
    if not documents:
        print("\nNo documents pending processing.")
        conn.close()
        return

    print(f"\nFound {len(documents)} document(s) pending processing.")

    for doc in documents:
        doc_id = doc["id"]
        filepath = doc["path_original"]
        status = doc["status"]
        ext = os.path.splitext(filepath)[1].lower()

        print(f"\n>>> Processing Document: {os.path.basename(filepath)} (Status: {status})")

        # ----------------------------------------------------
        # PHASE 2: Conversion
        # ----------------------------------------------------
        if status == 'inventory_done':
            print("  [PHASE 2] Converting file...")
            try:
                if ext == ".pdf":
                    process_pdf(doc_id, filepath, conn)
                elif ext in [".docx", ".pptx", ".xlsx", ".csv", ".html", ".txt"]:
                    process_native_office(doc_id, filepath, conn)
                else:
                    print(f"  Skipping conversion for unsupported format: {filepath}")
                    cursor.execute("UPDATE documents SET status = 'convert_done' WHERE id = ?", (doc_id,))
                conn.commit()
                status = 'convert_done'
            except Exception as e:
                print(f"  Conversion failed: {e}")
                cursor.execute("UPDATE documents SET status = 'failed' WHERE id = ?", (doc_id,))
                conn.commit()
                continue

        # ----------------------------------------------------
        # PHASE 3: Local OCR (Ollama + PaddleOCR)
        # ----------------------------------------------------
        if status == 'convert_done':
            # Check if there are pages pending OCR
            cursor.execute(
                "SELECT page_num FROM pages WHERE doc_id = ? AND needs_ocr = 1 AND ocr_status = 'pending'",
                (doc_id,)
            )
            pending_ocr_pages = cursor.fetchall()
            
            if pending_ocr_pages:
                print(f"  [PHASE 3] Running local OCR on {len(pending_ocr_pages)} pages...")
                ocr_failed = False
                for p_row in pending_ocr_pages:
                    page_num = p_row["page_num"]
                    print(f"    OCR Page {page_num}...")
                    try:
                        pix = get_page_pixmap(filepath, page_num)
                        # Run Ollama OCR
                        ocr_text_ollama = run_ollama_ocr(pix)
                        # Run PaddleOCR
                        ocr_text_local = run_paddle_ocr(pix)
                        
                        p_status = "done"
                        if not ocr_text_ollama and not ocr_text_local:
                            p_status = "failed"
                            ocr_failed = True

                        cursor.execute(
                            """
                            UPDATE pages 
                            SET ocr_text_ollama = ?, ocr_text_local = ?, ocr_status = ?, last_attempt_at = CURRENT_TIMESTAMP
                            WHERE doc_id = ? AND page_num = ?
                            """,
                            (ocr_text_ollama, ocr_text_local, p_status, doc_id, page_num)
                        )
                        conn.commit()
                    except Exception as e:
                        print(f"    OCR failed for page {page_num}: {e}")
                        cursor.execute(
                            "UPDATE pages SET ocr_status = 'failed', last_error = ? WHERE doc_id = ? AND page_num = ?",
                            (str(e), doc_id, page_num)
                        )
                        conn.commit()
                        ocr_failed = True

                if ocr_failed:
                    print("  Some pages failed OCR. Document marked as failed.")
                    cursor.execute("UPDATE documents SET status = 'failed' WHERE id = ?", (doc_id,))
                    conn.commit()
                    continue
                else:
                    cursor.execute("UPDATE documents SET status = 'ocr_done' WHERE id = ?", (doc_id,))
                    conn.commit()
                    status = 'ocr_done'
            else:
                # No pages need OCR
                cursor.execute("UPDATE documents SET status = 'ocr_done' WHERE id = ?", (doc_id,))
                conn.commit()
                status = 'ocr_done'

        # ----------------------------------------------------
        # PHASE 4: Gemini Validation
        # ----------------------------------------------------
        if status == 'ocr_done':
            # Check if there are pages pending validation
            cursor.execute(
                "SELECT page_num, ocr_text_ollama, ocr_text_local, attempts FROM pages WHERE doc_id = ? AND needs_ocr = 1 AND validation_status = 'pending'",
                (doc_id,)
            )
            pending_val_pages = cursor.fetchall()

            if pending_val_pages:
                if gemini_rate_limited:
                    print("  [PHASE 4] Skipping validation for now (Gemini rate-limited). Will process later.")
                    continue

                print(f"  [PHASE 4] Validating {len(pending_val_pages)} pages with Gemini...")
                val_failed = False
                for p_row in pending_val_pages:
                    page_num = p_row["page_num"]
                    ocr_ollama = p_row["ocr_text_ollama"]
                    ocr_local = p_row["ocr_text_local"]
                    attempts = p_row["attempts"]

                    if not gemini_client:
                        print("    Skipping validation: Gemini client not initialized.")
                        val_failed = True
                        break

                    validated_text, confidence, err = validate_page(
                        gemini_client, doc_id, page_num, filepath, ocr_ollama, ocr_local
                    )

                    if err:
                        # Check if rate limit error
                        err_lower = err.lower()
                        if any(kw in err_lower for kw in ["429", "resource_exhausted", "quota exceeded", "rate limit"]):
                            print(f"    [GEMINI RATE LIMIT DETECTED] Error: {err}")
                            gemini_rate_limited = True
                            val_failed = True
                            break
                        
                        print(f"    Validation failed for page {page_num}: {err}")
                        cursor.execute(
                            "UPDATE pages SET attempts = ?, last_error = ?, last_attempt_at = CURRENT_TIMESTAMP WHERE doc_id = ? AND page_num = ?",
                            (attempts + 1, err, doc_id, page_num)
                        )
                        conn.commit()
                        val_failed = True
                    else:
                        cursor.execute(
                            """
                            UPDATE pages 
                            SET validated_text = ?, confidence = ?, validation_status = ?, attempts = attempts + 1, last_attempt_at = CURRENT_TIMESTAMP
                            WHERE doc_id = ? AND page_num = ?
                            """,
                            (validated_text, confidence, "done", doc_id, page_num)
                        )
                        conn.commit()
                        print(f"    Page {page_num} validated successfully. Confidence: {confidence:.2f}")

                if gemini_rate_limited:
                    # We hit the rate limit, skip the rest of validation for this doc and subsequent docs
                    continue

                if val_failed:
                    # We don't mark the whole doc as failed immediately on temporary errors, 
                    # but if it fails completely we skip assembly
                    continue
                else:
                    cursor.execute("UPDATE documents SET status = 'validated' WHERE id = ?", (doc_id,))
                    conn.commit()
                    status = 'validated'
            else:
                # No pages need validation
                cursor.execute("UPDATE documents SET status = 'validated' WHERE id = ?", (doc_id,))
                conn.commit()
                status = 'validated'

        # ----------------------------------------------------
        # PHASE 5: Assembly & Export
        # ----------------------------------------------------
        if status == 'validated':
            print("  [PHASE 5] Assembling and exporting document...")
            
            # Fetch all pages to assemble
            cursor.execute("SELECT page_num, validated_text, confidence, needs_ocr FROM pages WHERE doc_id = ?", (doc_id,))
            pages = cursor.fetchall()
            
            if not pages:
                # Placeholder for empty documents
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
                write_document_files(doc_meta, f"<document>\n  <!-- Non-convertible file of type {ext} -->\n</document>")
                cursor.execute("UPDATE documents SET status = 'exported' WHERE id = ?", (doc_id,))
                conn.commit()
                exported_count += 1
            else:
                pages_list = [dict(p) for p in pages]
                pages_list.sort(key=lambda x: x["page_num"])
                
                conf_sum = sum(p["confidence"] for p in pages_list)
                conf_avg = conf_sum / len(pages_list)
                
                doc_title_approx = os.path.splitext(os.path.basename(filepath))[0].replace("-", " ").title()
                any_ocr_needed = any(p["needs_ocr"] == 1 for p in pages_list)
                
                if not any_ocr_needed:
                    # Native doc
                    title = doc_title_approx
                    markdown_body = "<document>\n"
                    for p in pages_list:
                        markdown_body += f"  <section topic=\"geral\" page=\"{p['page_num']}\">\n"
                        lines = p["validated_text"].split("\n") if p["validated_text"] else []
                        markdown_body += "\n".join("    " + l for l in lines) + "\n"
                        markdown_body += "  </section>\n"
                    markdown_body += "</document>"
                else:
                    # OCR scanned doc
                    if gemini_client and not gemini_rate_limited:
                        try:
                            title, markdown_body = assemble_pdf_document(gemini_client, doc_title_approx, pages_list)
                        except Exception as e:
                            # If assembly fails (could also be rate limits)
                            err_str = str(e).lower()
                            if any(kw in err_str for kw in ["429", "resource_exhausted", "quota exceeded", "rate limit"]):
                                print(f"    [GEMINI RATE LIMIT DETECTED during assembly] Error: {e}")
                                gemini_rate_limited = True
                                continue
                            print(f"    Assembly failed: {e}. Falling back to programmatic stitching.")
                            title = doc_title_approx
                            markdown_body = None
                    else:
                        title = doc_title_approx
                        markdown_body = None

                    if not markdown_body:
                        # Fallback programmatic stitching
                        title = doc_title_approx
                        markdown_body = "<document>\n"
                        for p in pages_list:
                            markdown_body += f"  <section topic=\"scanned\" page=\"{p['page_num']}\">\n"
                            lines = p["validated_text"].split("\n") if p["validated_text"] else []
                            markdown_body += "\n".join("    " + l for l in lines) + "\n"
                            markdown_body += "  </section>\n"
                        markdown_body += "</document>"

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
                
                try:
                    write_document_files(doc_meta, markdown_body)
                    cursor.execute("UPDATE documents SET status = 'exported' WHERE id = ?", (doc_id,))
                    conn.commit()
                    print(f"  Finished assembly & export for: {os.path.basename(filepath)}")
                    exported_count += 1
                except Exception as e:
                    print(f"  Failed to write document files: {e}")

            # ----------------------------------------------------
            # INCREMENTAL DEPLOY: Run deploy after every 20 exported files
            # ----------------------------------------------------
            if exported_count > 0 and exported_count % 20 == 0:
                print(f"\n[INCREMENTAL DEPLOY] Exported {exported_count} documents in this run. Re-deploying library...")
                try:
                    for line in deploy():
                        print(line, end="")
                except Exception as e:
                    print(f"  Deploy failed: {e}")

    conn.close()
    
    # Run a final deploy if any files were exported
    if exported_count > 0:
        print(f"\n[FINAL DEPLOY] Run complete. Exported total of {exported_count} documents. Running final deploy...")
        try:
            for line in deploy():
                print(line, end="")
        except Exception as e:
            print(f"  Final deploy failed: {e}")
            
    print("\n" + "="*60)
    print(f"Pipeline complete. Total documents processed: {len(documents)}. Exported: {exported_count}.")
    print("="*60)

if __name__ == "__main__":
    main()
