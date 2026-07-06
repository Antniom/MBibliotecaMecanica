-- =============================================================
-- MBibliotecaMecanica — Cloudflare D1 Setup
-- Run this ONCE in the D1 dashboard SQL editor
-- (Cloudflare Dashboard → D1 → your database → Console tab)
-- =============================================================

CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  file_name TEXT NOT NULL,
  file_size INTEGER,
  file_type TEXT,
  github_asset_id INTEGER,       -- GitHub Release asset ID (used for deletion after processing)
  github_asset_url TEXT,         -- Public download URL
  suggested_disciplina TEXT,     -- What submitter suggested
  suggested_tipo TEXT,
  submitter_name TEXT,           -- Optional
  notes TEXT,                    -- Optional notes for admin
  status TEXT DEFAULT 'pending', -- pending | approved | denied | downloading | processing | done | failed
  assigned_disciplina TEXT,      -- What admin assigned
  assigned_tipo TEXT,
  assigned_ano INTEGER,
  assigned_semestre INTEGER,
  local_doc_id TEXT,             -- SHA-256 from documents table after processing
  error_message TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipeline_status (
  id INTEGER PRIMARY KEY DEFAULT 1,
  status TEXT DEFAULT 'idle',    -- idle | running | paused | error
  last_heartbeat TEXT,
  current_doc TEXT,
  progress_total INTEGER DEFAULT 0,
  progress_done INTEGER DEFAULT 0,
  machine_name TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Seed the single status row
INSERT OR IGNORE INTO pipeline_status (id, status) VALUES (1, 'idle');

CREATE TABLE IF NOT EXISTS error_log (
  id TEXT PRIMARY KEY,
  submission_id TEXT,
  stage TEXT,                    -- download | pipeline | upload | api
  error_message TEXT,
  stack_trace TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_log_created ON error_log(created_at DESC);
