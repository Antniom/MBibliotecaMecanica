import sys
import os
import time
import threading
from datetime import datetime

# Force UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import psutil
from db_utils import get_db_connection
from inventory import run_inventory
from convert import process_pdf, process_native_office
from ocr import get_page_pixmap, run_paddle_ocr
from validate import get_gemini_client, validate_page
from assemble import assemble_pdf_document, write_document_files
from deploy import deploy

# ── Resource management ─────────────────────────────────────────
DISABLE_OLLAMA = os.getenv("DISABLE_OLLAMA", "0") == "1"
RAM_PAUSE_PCT  = 75   # pause if RAM > 75%
CPU_PAUSE_PCT  = 90   # pause if CPU > 90%

def wait_for_resources():
    """Block until RAM and CPU are below safe thresholds."""
    while True:
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=0.5)
        if ram < RAM_PAUSE_PCT and cpu < CPU_PAUSE_PCT:
            break
        print(f"  [RECURSOS] RAM {ram:.0f}% / CPU {cpu:.0f}% — a aguardar recursos disponíveis...")
        time.sleep(5)

def ram_free_gb():
    return psutil.virtual_memory().available / 1024**3

# ── Background uploader ─────────────────────────────────────────
def start_background_uploader():
    from upload_assets import run_uploads
    def _loop():
        print("\n[UPLOAD] A iniciar upload paralelo dos ficheiros originais para o GitHub...")
        try:
            run_uploads()
        except Exception as e:
            print(f"[UPLOAD ERRO] {e}")
        print("[UPLOAD] Upload batch concluído.")
    threading.Thread(target=_loop, daemon=True).start()


def main():
    print("=" * 60)
    print("   BIBLIOTECA DE ENGENHARIA MECÂNICA — PIPELINE COMPLETO")
    print("=" * 60)
    print(f"\nRecursos disponíveis: {psutil.cpu_count()} cores, "
          f"{psutil.virtual_memory().total/1024**3:.1f} GB RAM total, "
          f"{ram_free_gb():.1f} GB livres")

    if ram_free_gb() < 1.5:
        print("⚠️  Pouca memória RAM disponível. Ollama será desativado nesta sessão.")
        os.environ["DISABLE_OLLAMA"] = "1"

    # ── Phase 1: Inventory ──────────────────────────────────────
    print("\n[PASSO 1] Inventário e classificação de ficheiros...")
    run_inventory()

    # ── Start background file uploader ──────────────────────────
    start_background_uploader()

    # ── Immediate deploy: push any already-exported markdown files ──
    print("\n[DEPLOY INICIAL] A verificar se há conteúdo já pronto para publicar...")
    try:
        for line in deploy():
            print(line, end="")
    except Exception as e:
        print(f"  Deploy inicial falhou: {e}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # ── Gemini client (optional) ────────────────────────────────
    gemini_client = None
    try:
        gemini_client = get_gemini_client()
        print("[OK] Cliente Gemini inicializado.")
    except Exception as e:
        print(f"[AVISO] Gemini não disponível: {e}")
        print("       Será usado stitching local como fallback.")

    # ── Ollama (only if RAM available and not disabled) ──────────
    use_ollama = not (DISABLE_OLLAMA or os.getenv("DISABLE_OLLAMA") == "1" or ram_free_gb() < 2.0)
    if use_ollama:
        try:
            from ocr import ensure_ollama_and_model
            ensure_ollama_and_model()
        except Exception as e:
            print(f"[AVISO] Ollama não disponível: {e}. Usando apenas PaddleOCR.")
            use_ollama = False
    else:
        print("[OCR] Ollama desativado (pouca RAM). A usar apenas PaddleOCR.")

    # ── Load all pending documents ───────────────────────────────
    cursor.execute("""
        SELECT id, path_original, status, disciplina, tipo, ano, semestre,
               storage_release_tag, storage_url
        FROM documents
        WHERE status NOT IN ('exported', 'failed')
        ORDER BY id ASC
    """)
    documents = cursor.fetchall()

    if not documents:
        print("\nNenhum documento pendente. Tudo já processado!")
        conn.close()
        return

    total = len(documents)
    print(f"\nEncontrados {total} documentos pendentes de processamento.\n")

    exported_count = 0
    gemini_rate_limited = False

    for idx, doc in enumerate(documents, 1):
        doc_id   = doc["id"]
        filepath = doc["path_original"]
        status   = doc["status"]
        ext      = os.path.splitext(filepath)[1].lower()
        name     = os.path.basename(filepath)

        print(f"\n[{idx}/{total}] {name}  (estado: {status})")

        # Check file exists
        if not os.path.exists(filepath):
            print(f"  ⚠️  Ficheiro não encontrado no disco, a saltar.")
            cursor.execute("UPDATE documents SET status='failed' WHERE id=?", (doc_id,))
            conn.commit()
            continue

        # Wait for resources before processing each document
        wait_for_resources()

        # ── Phase 2: Conversion ──────────────────────────────
        if status == 'inventory_done':
            print("  [2] A converter ficheiro...")
            try:
                if ext == ".pdf":
                    process_pdf(doc_id, filepath, conn)
                elif ext in [".docx", ".pptx", ".xlsx", ".csv", ".html", ".txt"]:
                    process_native_office(doc_id, filepath, conn)
                else:
                    cursor.execute("UPDATE documents SET status='convert_done' WHERE id=?", (doc_id,))
                conn.commit()
                status = 'convert_done'
                print("  [2] ✓ Conversão concluída.")
            except Exception as e:
                print(f"  [2] ✗ Falha na conversão: {e}")
                cursor.execute("UPDATE documents SET status='failed' WHERE id=?", (doc_id,))
                conn.commit()
                continue

        # ── Phase 3: OCR ────────────────────────────────────
        if status == 'convert_done':
            cursor.execute(
                "SELECT page_num FROM pages WHERE doc_id=? AND needs_ocr=1 AND ocr_status='pending'",
                (doc_id,)
            )
            pending = cursor.fetchall()

            if pending:
                print(f"  [3] A fazer OCR em {len(pending)} páginas (PaddleOCR)...")
                ocr_failed = False
                for p_row in pending:
                    page_num = p_row["page_num"]
                    wait_for_resources()
                    try:
                        pix = get_page_pixmap(filepath, page_num)

                        # PaddleOCR always
                        ocr_local = run_paddle_ocr(pix)

                        # Ollama only if RAM allows
                        ocr_ollama = None
                        if use_ollama and ram_free_gb() > 2.0:
                            try:
                                from ocr import run_ollama_ocr
                                ocr_ollama = run_ollama_ocr(pix)
                            except Exception:
                                pass  # silently skip Ollama on error

                        p_status = "done" if (ocr_local or ocr_ollama) else "failed"
                        if p_status == "failed":
                            ocr_failed = True

                        cursor.execute("""
                            UPDATE pages
                            SET ocr_text_ollama=?, ocr_text_local=?, ocr_status=?,
                                last_attempt_at=CURRENT_TIMESTAMP
                            WHERE doc_id=? AND page_num=?
                        """, (ocr_ollama, ocr_local, p_status, doc_id, page_num))
                        conn.commit()

                    except Exception as e:
                        print(f"    Página {page_num} falhou: {e}")
                        cursor.execute(
                            "UPDATE pages SET ocr_status='failed', last_error=? WHERE doc_id=? AND page_num=?",
                            (str(e), doc_id, page_num)
                        )
                        conn.commit()
                        ocr_failed = True

                if ocr_failed:
                    # Don't hard-fail — some pages may be blank. Only fail if ALL failed.
                    cursor.execute(
                        "SELECT COUNT(*) FROM pages WHERE doc_id=? AND ocr_status='done'",
                        (doc_id,)
                    )
                    done_count = cursor.fetchone()[0]
                    if done_count == 0:
                        print(f"  [3] ✗ OCR falhou em todas as páginas.")
                        cursor.execute("UPDATE documents SET status='failed' WHERE id=?", (doc_id,))
                        conn.commit()
                        continue
                    else:
                        print(f"  [3] ⚠️  Algumas páginas falharam, mas {done_count} OK. A continuar.")

            cursor.execute("UPDATE documents SET status='ocr_done' WHERE id=?", (doc_id,))
            conn.commit()
            status = 'ocr_done'
            print("  [3] ✓ OCR concluído.")

        # ── Phase 4: Gemini Validation ───────────────────────
        if status == 'ocr_done':
            cursor.execute(
                "SELECT page_num, ocr_text_ollama, ocr_text_local, attempts FROM pages "
                "WHERE doc_id=? AND needs_ocr=1 AND validation_status='pending'",
                (doc_id,)
            )
            pending_val = cursor.fetchall()

            if pending_val and not gemini_rate_limited and gemini_client:
                print(f"  [4] A validar {len(pending_val)} páginas com Gemini...")
                for p_row in pending_val:
                    page_num   = p_row["page_num"]
                    ocr_ollama = p_row["ocr_text_ollama"]
                    ocr_local  = p_row["ocr_text_local"]
                    attempts   = p_row["attempts"]

                    wait_for_resources()
                    validated_text, confidence, err = validate_page(
                        gemini_client, doc_id, page_num, filepath, ocr_ollama, ocr_local
                    )

                    if err:
                        err_lower = err.lower()
                        if any(k in err_lower for k in ["429", "resource_exhausted", "quota"]):
                            print(f"  [4] ⚠️  Limite de taxa Gemini atingido. A continuar sem validação por agora.")
                            gemini_rate_limited = True
                            break
                        cursor.execute(
                            "UPDATE pages SET attempts=?, last_error=?, last_attempt_at=CURRENT_TIMESTAMP "
                            "WHERE doc_id=? AND page_num=?",
                            (attempts + 1, err, doc_id, page_num)
                        )
                        conn.commit()
                    else:
                        cursor.execute("""
                            UPDATE pages
                            SET validated_text=?, confidence=?, validation_status='done',
                                attempts=attempts+1, last_attempt_at=CURRENT_TIMESTAMP
                            WHERE doc_id=? AND page_num=?
                        """, (validated_text, confidence, doc_id, page_num))
                        conn.commit()

                if gemini_rate_limited:
                    # Skip to next doc; will be retried on next run
                    continue
            else:
                # No Gemini → copy local OCR text into validated_text directly
                cursor.execute("""
                    UPDATE pages
                    SET validated_text = COALESCE(ocr_text_local, ocr_text_ollama, ''),
                        confidence = 0.70,
                        validation_status = 'done'
                    WHERE doc_id=? AND needs_ocr=1 AND validation_status='pending'
                """, (doc_id,))
                conn.commit()

            cursor.execute("UPDATE documents SET status='validated' WHERE id=?", (doc_id,))
            conn.commit()
            status = 'validated'
            print("  [4] ✓ Validação concluída.")

        # ── Phase 5: Assembly & Export ───────────────────────
        if status == 'validated':
            print("  [5] A montar e exportar documento...")

            cursor.execute(
                "SELECT page_num, validated_text, confidence, needs_ocr FROM pages WHERE doc_id=?",
                (doc_id,)
            )
            pages = cursor.fetchall()
            pages_list = sorted([dict(p) for p in pages], key=lambda x: x["page_num"])

            conf_avg = (sum(p["confidence"] for p in pages_list) / len(pages_list)) if pages_list else 0.0
            doc_title = os.path.splitext(name)[0].replace("-", " ").title()
            any_ocr = any(p["needs_ocr"] == 1 for p in pages_list)

            # Build markdown body
            markdown_body = None
            if any_ocr and gemini_client and not gemini_rate_limited:
                try:
                    wait_for_resources()
                    doc_title, markdown_body = assemble_pdf_document(gemini_client, doc_title, pages_list)
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower():
                        gemini_rate_limited = True
                    print(f"  [5] ⚠️  Montagem Gemini falhou ({e}). A usar stitching local.")

            if not markdown_body:
                # Always-works fallback: stitch OCR text directly
                tag_type = "scanned" if any_ocr else "geral"
                markdown_body = "<document>\n"
                for p in pages_list:
                    markdown_body += f'  <section topic="{tag_type}" page="{p["page_num"]}">\n'
                    for line in (p["validated_text"] or "").split("\n"):
                        markdown_body += f"    {line}\n"
                    markdown_body += "  </section>\n"
                markdown_body += "</document>"

            doc_meta = {
                "id": doc_id,
                "title": doc_title,
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
                cursor.execute("UPDATE documents SET status='exported' WHERE id=?", (doc_id,))
                conn.commit()
                exported_count += 1
                print(f"  [5] ✓ Exportado. (Total: {exported_count})")
            except Exception as e:
                print(f"  [5] ✗ Falha ao escrever ficheiros: {e}")
                cursor.execute("UPDATE documents SET status='failed' WHERE id=?", (doc_id,))
                conn.commit()

            # Incremental deploy every 20 docs
            if exported_count > 0 and exported_count % 20 == 0:
                print(f"\n[DEPLOY INCREMENTAL] {exported_count} documentos exportados. A publicar no site...")
                try:
                    for line in deploy():
                        print(line, end="")
                except Exception as e:
                    print(f"  Deploy falhou: {e}")

    conn.close()

    # Final deploy
    if exported_count > 0:
        print(f"\n[DEPLOY FINAL] {exported_count} documentos exportados. A publicar no site...")
        try:
            for line in deploy():
                print(line, end="")
        except Exception as e:
            print(f"  Deploy final falhou: {e}")

    print("\n" + "=" * 60)
    print(f"Pipeline concluído! Exportados: {exported_count}/{total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
