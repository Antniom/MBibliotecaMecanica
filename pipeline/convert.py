import sys
import os
import sqlite3
import fitz  # PyMuPDF

# Force stdout/stderr to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from markitdown import MarkItDown
from db_utils import get_db_connection

def process_pdf(doc_id, filepath, conn):
    """Processes a PDF page by page, checking for native text layers."""
    cursor = conn.cursor()
    doc = None
    try:
        doc = fitz.open(filepath)
        if doc.is_encrypted:
            if not doc.authenticate(""):
                print(f"Warning: PDF {filepath} is encrypted and password-protected. Skipping.")
                cursor.execute("UPDATE documents SET status = 'failed' WHERE id = ?", (doc_id,))
                return
                
        num_pages = len(doc)
        print(f"Processing PDF: {filepath} ({num_pages} pages)")

        for i in range(num_pages):
            page_num = i + 1
            page = doc[i]
            text = page.get_text().strip()
            
            # Determine if the page contains a native text layer
            # A threshold of 50 characters is used to avoid noise/header-only text
            if len(text) > 50:
                needs_ocr = False
                ocr_status = "done"
                validation_status = "done"
                validated_text = text
                confidence = 1.0
            else:
                needs_ocr = True
                ocr_status = "pending"
                validation_status = "pending"
                validated_text = None
                confidence = 0.0

            # Insert or replace page state
            cursor.execute(
                """
                INSERT OR REPLACE INTO pages (
                    doc_id, page_num, needs_ocr, ocr_status, validation_status, validated_text, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, page_num, int(needs_ocr), ocr_status, validation_status, validated_text, confidence)
            )

        cursor.execute("UPDATE documents SET status = 'convert_done' WHERE id = ?", (doc_id,))
        print(f"Finished PDF: {filepath}")
    except Exception as e:
        print(f"Error processing PDF {filepath}: {e}")
        cursor.execute("UPDATE documents SET status = 'failed' WHERE id = ?", (doc_id,))
    finally:
        if doc is not None:
            doc.close()

def process_native_office(doc_id, filepath, conn):
    """Processes office documents (docx, pptx, xlsx) using MarkItDown."""
    cursor = conn.cursor()
    print(f"Processing Office document: {filepath}")
    
    try:
        md = MarkItDown()
        result = md.convert(filepath)
        text = result.text_content.strip()
        
        # Save as page 1 (non-scanned documents have single page content stream)
        cursor.execute(
            """
            INSERT OR REPLACE INTO pages (
                doc_id, page_num, needs_ocr, ocr_status, validation_status, validated_text, confidence
            ) VALUES (?, ?, 0, 'done', 'done', ?, 1.0)
            """,
            (doc_id, 1, text)
        )
        cursor.execute("UPDATE documents SET status = 'convert_done' WHERE id = ?", (doc_id,))
        print(f"Finished Office document: {filepath}")
    except Exception as e:
        print(f"Error converting {filepath} with MarkItDown: {e}")
        cursor.execute("UPDATE documents SET status = 'failed' WHERE id = ?", (doc_id,))

def run_conversion():
    """Runs Phase 2: Native Conversion for pending/newly inventoried documents."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, path_original FROM documents WHERE status = 'inventory_done'")
    docs = cursor.fetchall()
    
    if not docs:
        print("No documents pending conversion.")
        conn.close()
        return

    for doc in docs:
        doc_id = doc["id"]
        filepath = doc["path_original"]
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext == ".pdf":
            process_pdf(doc_id, filepath, conn)
        elif ext in [".docx", ".pptx", ".xlsx", ".csv", ".html", ".txt"]:
            process_native_office(doc_id, filepath, conn)
        else:
            # Non-convertible formats (CAD, code files, archives etc.)
            print(f"Skipping conversion for unsupported format: {filepath}")
            cursor.execute("UPDATE documents SET status = 'convert_done' WHERE id = ?", (doc_id,))
            
        conn.commit()

    conn.close()
    print("Conversion batch finished.")

if __name__ == "__main__":
    run_conversion()
