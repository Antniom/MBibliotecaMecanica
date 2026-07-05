import sys
import os
import sqlite3
import base64
import requests
import fitz  # PyMuPDF
import subprocess
import time

# Force stdout/stderr to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from db_utils import get_db_connection

# Load configurations
load_dotenv()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# Optional PaddleOCR import
try:
    from paddleocr import PaddleOCR
    # Initialize PaddleOCR on startup if installed
    paddle_ocr_engine = PaddleOCR(lang='pt', enable_mkldnn=False)
    print("PaddleOCR loaded successfully.")
except Exception as e:
    paddle_ocr_engine = None
    print(f"PaddleOCR not available (optional): {e}")

# Optional Surya OCR import
try:
    from surya.ocr import run_ocr
    from surya.model.detection.model import load_model as load_det_model, load_processor as load_det_processor
    from surya.model.recognition.model import load_model as load_rec_model, load_processor as load_rec_processor
    # We will initialize models lazily if Surya is used
    surya_available = True
    print("Surya OCR libraries imported successfully.")
except Exception as e:
    surya_available = False
    print(f"Surya OCR not available (optional): {e}")

def ensure_ollama_and_model():
    """Tries to ensure Ollama is running and has the configured model."""
    # 1. Check if Ollama is online
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        print("Ollama is already running.")
    except Exception:
        print("Ollama is offline. Attempting to start Ollama server...")
        try:
            # On Windows, try launching the Ollama app or 'ollama serve'
            # Launch in background
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Wait up to 10 seconds for it to start
            for _ in range(10):
                time.sleep(1)
                try:
                    requests.get(f"{OLLAMA_HOST}/api/tags", timeout=1)
                    print("Ollama server started successfully.")
                    break
                except Exception:
                    pass
            else:
                print("Could not start Ollama server automatically.")
                return False
        except Exception as e:
            print(f"Failed to start Ollama process: {e}")
            return False
            
    # 2. Check if the model is pulled
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        
        # Check matching tag
        target_model = OLLAMA_MODEL
        if ":" not in target_model:
            target_model = f"{target_model}:latest"
            
        installed = False
        for m in models:
            if m == OLLAMA_MODEL or m == target_model or m.startswith(OLLAMA_MODEL + ":"):
                installed = True
                break
                
        if installed:
            print(f"Ollama model {OLLAMA_MODEL} is already installed.")
        else:
            print(f"Ollama model {OLLAMA_MODEL} not found. Pulling model... (this may take a while)")
            # Pull model synchronously and print progress
            process = subprocess.Popen(
                ["ollama", "pull", OLLAMA_MODEL],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8"
            )
            for line in iter(process.stdout.readline, ""):
                print(line.strip())
            process.wait()
            if process.returncode == 0:
                print(f"Successfully pulled {OLLAMA_MODEL}.")
            else:
                print(f"Failed to pull model {OLLAMA_MODEL} with exit code {process.returncode}.")
    except Exception as e:
        print(f"Error checking/pulling Ollama model: {e}")
        return False
        
    return True

def get_page_pixmap(pdf_path, page_num):
    """Renders a PDF page to a 300 DPI pixmap for OCR."""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    # 300 DPI is standard for high-quality OCR
    zoom = 300 / 72
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    doc.close()
    return pix

def run_ollama_ocr(pix):
    """Calls local Ollama API to run OCR on the page image."""
    try:
        # Check if Ollama is running
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
    except Exception:
        print(f"Ollama is offline or unreachable at {OLLAMA_HOST}. Skipping Ollama OCR.")
        return None

    try:
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        
        url = f"{OLLAMA_HOST}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Extract and transcribe all text, equations, and tables from this document image. "
                        "Do not explain, do not summarize, do not add any markdown titles other than transcription content. "
                        "Just output the exact transcribed text."
                    ),
                    "images": [img_b64]
                }
            ],
            "stream": False
        }
        
        print(f"Sending page to Ollama ({OLLAMA_MODEL})...")
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        result = response.json()
        return result["message"]["content"].strip()
    except Exception as e:
        print(f"Ollama OCR failed: {e}")
        return None

def run_paddle_ocr(pix):
    """Runs PaddleOCR on the page image."""
    if not paddle_ocr_engine:
        return None

    try:
        # Write to temporary file for PaddleOCR path execution
        temp_img_path = "temp_ocr_page.png"
        pix.save(temp_img_path)
        
        print("Running PaddleOCR...")
        result = paddle_ocr_engine.predict(temp_img_path)
        
        # Clean up
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)
            
        if not result or not result[0] or 'rec_texts' not in result[0]:
            return ""

        text_lines = result[0]['rec_texts']
        return "\n".join(text_lines)
    except Exception as e:
        print(f"PaddleOCR failed: {e}")
        return None

def run_surya_ocr(pix):
    """Runs Surya OCR on the page image if available."""
    # Surya OCR requires PIL Image
    if not surya_available:
        return None
    # Lazily implement if needed, otherwise fallback to Paddle
    return None

def process_ocr_batch():
    """Runs Phase 3: OCR Local for pending pages."""
    # Ensure Ollama is running and model is pulled
    ensure_ollama_and_model()

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query pages needing OCR that are pending
    cursor.execute(
        """
        SELECT p.doc_id, p.page_num, d.path_original 
        FROM pages p
        JOIN documents d ON p.doc_id = d.id
        WHERE p.needs_ocr = 1 AND p.ocr_status = 'pending'
        """
    )
    pages_to_process = cursor.fetchall()
    
    if not pages_to_process:
        print("No pages pending OCR.")
        conn.close()
        return

    print(f"Found {len(pages_to_process)} page(s) pending OCR.")

    for row in pages_to_process:
        doc_id = row["doc_id"]
        page_num = row["page_num"]
        pdf_path = row["path_original"]
        
        print(f"\n--- Running OCR on Doc: {os.path.basename(pdf_path)} - Page {page_num} ---")
        
        try:
            pix = get_page_pixmap(pdf_path, page_num)
        except Exception as e:
            print(f"Failed to render page image: {e}")
            cursor.execute(
                "UPDATE pages SET ocr_status = 'failed', last_error = ? WHERE doc_id = ? AND page_num = ?",
                (str(e), doc_id, page_num)
            )
            conn.commit()
            continue

        # 1. Run Ollama OCR
        ocr_text_ollama = run_ollama_ocr(pix)
        
        # 2. Run PaddleOCR (or Surya)
        ocr_text_local = run_paddle_ocr(pix)
        if not ocr_text_local and surya_available:
            ocr_text_local = run_surya_ocr(pix)

        # Check outcomes
        status = "done"
        if ocr_text_ollama is None and ocr_text_local is None:
            status = "failed"
            print("Both OCR methods failed/skipped.")
        else:
            print(f"OCR finished. Ollama size: {len(ocr_text_ollama) if ocr_text_ollama else 0} chars, Local size: {len(ocr_text_local) if ocr_text_local else 0} chars")

        cursor.execute(
            """
            UPDATE pages 
            SET ocr_text_ollama = ?, ocr_text_local = ?, ocr_status = ?, last_attempt_at = CURRENT_TIMESTAMP
            WHERE doc_id = ? AND page_num = ?
            """,
            (ocr_text_ollama, ocr_text_local, status, doc_id, page_num)
        )
        
        # If all pages of a document are processed, we'll check later in validation
        conn.commit()

    conn.close()
    print("\nOCR batch processing complete.")

if __name__ == "__main__":
    process_ocr_batch()
