-- SQLite Schema for MBibliotecaMecanica

CREATE TABLE IF NOT EXISTS documents (
  id                  TEXT PRIMARY KEY,      -- hash SHA-256 of the original file
  path_original       TEXT NOT NULL,
  disciplina          TEXT,                  -- taxonomy discipline folder name
  tipo                TEXT,                  -- teoria | fichas-exercicios | resumos | resolucoes | testes-exames | trabalhos-projetos
  ano                 INTEGER,               -- 1 | 2 | 3
  semestre            INTEGER,               -- 1 | 2
  storage_release_tag TEXT,                  -- tag of the release (e.g., '1-ano', '2-ano', '3-ano')
  storage_url         TEXT,                  -- download URL of the asset in GitHub Release
  status              TEXT DEFAULT 'pending', -- pending | inventory_done | convert_done | ocr_done | validated | exported
  created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pages (
  doc_id              TEXT,
  page_num            INTEGER,               -- 1-indexed page number
  needs_ocr           BOOLEAN DEFAULT 0,
  ocr_text_ollama     TEXT,                  -- OCR transcript from Ollama (Qwen)
  ocr_text_local      TEXT,                  -- OCR transcript from PaddleOCR/Surya
  ocr_status          TEXT DEFAULT 'pending', -- pending | done | failed
  validated_text      TEXT,                  -- consolidated text output by Gemini Flash
  confidence          REAL,                  -- validation confidence (0.0 to 1.0)
  validation_status   TEXT DEFAULT 'pending', -- pending | done | failed
  attempts            INTEGER DEFAULT 0,
  last_error          TEXT,
  last_attempt_at     TIMESTAMP,
  PRIMARY KEY (doc_id, page_num),
  FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS api_usage_log (
  provider            TEXT,                  -- 'gemini_flash' etc.
  date                DATE PRIMARY KEY,
  requests_today      INTEGER DEFAULT 0,
  tokens_today        INTEGER DEFAULT 0
);
