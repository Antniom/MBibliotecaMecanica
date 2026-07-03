import sys
import os
import sqlite3
import fitz  # PyMuPDF
from PIL import Image
import io

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

# Define Pydantic schema for structured output
class ValidationResult(BaseModel):
    validated_text: str = Field(description="The final consolidated clean markdown text of the page.")
    confidence: float = Field(description="Confidence score between 0.0 (unreadable) and 1.0 (perfect).")

def get_gemini_client():
    """Returns a configured GenAI Client."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in .env.")
    return genai.Client(api_key=GEMINI_API_KEY)

def get_page_image(pdf_path, page_num):
    """Renders a page as a PIL Image for Gemini vision input."""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    # 150 DPI is a good compromise for Gemini vision (saves tokens while retaining detail)
    zoom = 150 / 72
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    img_data = pix.tobytes("png")
    doc.close()
    return Image.open(io.BytesIO(img_data))

def validate_page(client, doc_id, page_num, pdf_path, ocr_ollama, ocr_local):
    """Sends page image + redundant OCR texts to Gemini for consolidation and validation."""
    try:
        img = get_page_image(pdf_path, page_num)
    except Exception as e:
        print(f"Failed to load image for validation: {e}")
        return None, 0.0, str(e)

    prompt = f"""
We have run two different OCR methods on the attached image of page {page_num} of a mechanical engineering document.
One is from an LLM-based OCR and the other from a local engine. They might contain typos, spelling errors, structural formatting issues, or misrecognized math.

OCR Output 1 (Ollama):
---
{ocr_ollama or "(No transcription generated)"}
---

OCR Output 2 (Local OCR):
---
{ocr_local or "(No transcription generated)"}
---

Your task is to:
1. Examine the attached page image carefully.
2. Cross-reference the image with the two OCR outputs to reconstruct the exact text.
3. Clean up formatting, resolve any OCR discrepancies, and output a clean markdown transcript.
4. Ensure mathematical formulas/equations are formatted in LaTeX:
   - Use \\( ... \\) for inline math.
   - Use \\[ ... \\] for block math equations (e.g. \\[ M_{{max}} = \\frac{{q L^2}}{{8}} \\]).
5. Reconstruct tables in clean GFM markdown table format if any exist.
6. Handle handwritten notes if present (wrap them in HTML tags like `<handwritten confidence="X.XX">notes</handwritten>`).
7. Evaluate a confidence score from 0.0 to 1.0 based on transcription completeness and legibility.

Return the result as a structured JSON object.
"""

    try:
        print(f"Calling Gemini Flash ({GEMINI_MODEL}) for page {page_num}...")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[img, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ValidationResult,
                temperature=0.1
            )
        )
        
        # Log API call usage
        # Estimate token usage if not provided in response metadata (approx 1 token per 4 chars)
        prompt_tokens = len(prompt) // 4 + 258 # image token estimate
        candidates_tokens = len(response.text) // 4
        total_tokens = prompt_tokens + candidates_tokens
        log_api_usage("gemini_flash", tokens_used=total_tokens)
        
        # Parse the structured JSON response
        result = response.parsed
        return result.validated_text, result.confidence, None
        
    except Exception as e:
        print(f"Gemini API call failed: {e}")
        return None, 0.0, str(e)

def run_validation():
    """Runs Phase 4: Validation final for pending pages."""
    try:
        client = get_gemini_client()
    except ValueError as e:
        print(e)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all pages that finished OCR but have not been validated yet
    cursor.execute(
        """
        SELECT p.doc_id, p.page_num, d.path_original, p.ocr_text_ollama, p.ocr_text_local, p.attempts
        FROM pages p
        JOIN documents d ON p.doc_id = d.id
        WHERE p.needs_ocr = 1 AND p.ocr_status = 'done' AND p.validation_status = 'pending'
        LIMIT 10 -- Process in small batches to respect rate limits
        """
    )
    pages_to_validate = cursor.fetchall()
    
    if not pages_to_validate:
        print("No pages pending Gemini validation.")
        conn.close()
        return

    print(f"Found {len(pages_to_validate)} page(s) ready for validation.")

    for row in pages_to_validate:
        doc_id = row["doc_id"]
        page_num = row["page_num"]
        pdf_path = row["path_original"]
        ocr_ollama = row["ocr_text_ollama"]
        ocr_local = row["ocr_text_local"]
        attempts = row["attempts"]
        
        print(f"\n--- Validating Doc: {os.path.basename(pdf_path)} - Page {page_num} ---")
        
        validated_text, confidence, err = validate_page(
            client, doc_id, page_num, pdf_path, ocr_ollama, ocr_local
        )
        
        if err:
            cursor.execute(
                """
                UPDATE pages 
                SET attempts = ?, last_error = ?, last_attempt_at = CURRENT_TIMESTAMP
                WHERE doc_id = ? AND page_num = ?
                """,
                (attempts + 1, err, doc_id, page_num)
            )
        else:
            cursor.execute(
                """
                UPDATE pages 
                SET validated_text = ?, confidence = ?, validation_status = 'done', attempts = attempts + 1, last_attempt_at = CURRENT_TIMESTAMP
                WHERE doc_id = ? AND page_num = ?
                """,
                (validated_text, confidence, doc_id, page_num)
            )
            print(f"Validation successful. Confidence: {confidence:.2f}")
            
        conn.commit()

    conn.close()
    print("\nValidation batch complete.")

if __name__ == "__main__":
    run_validation()
