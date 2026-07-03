import sqlite3
from db_utils import get_db_connection

def simulate():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Update scanned pages to copy ocr_text_local to validated_text and set validation_status to 'done'
    cursor.execute(
        """
        UPDATE pages 
        SET validated_text = ocr_text_local,
            confidence = 0.95,
            validation_status = 'done'
        WHERE needs_ocr = 1 AND ocr_status = 'done'
        """
    )
    conn.commit()
    print(f"Updated {cursor.rowcount} scanned page(s) to simulate Gemini validation.")
    conn.close()

if __name__ == "__main__":
    simulate()
