#!/usr/bin/env python3
"""Guard: Auditslip watchdog reports queue/OCR issues in dry-run without secrets or side effects."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "auditslip_watchdog.py"


def make_db(path: Path, old_ms: int) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE ocr_jobs (
          job_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          bot_key TEXT DEFAULT 'default',
          chat_id TEXT,
          message_id INTEGER,
          attempts INTEGER DEFAULT 0,
          max_attempts INTEGER DEFAULT 3,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          error TEXT
        );
        CREATE TABLE slips (
          id TEXT PRIMARY KEY,
          status TEXT,
          is_duplicate INTEGER DEFAULT 0,
          slip_date_iso TEXT,
          created_at INTEGER,
          amount REAL DEFAULT 0
        );
        """
    )
    now_ms = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO ocr_jobs(job_id,status,bot_key,chat_id,message_id,created_at,updated_at,error) VALUES(?,?,?,?,?,?,?,?)",
        ("stuck-processing", "processing", "bot1", "CHAT1", 101, old_ms, old_ms, "locked too long"),
    )
    conn.execute(
        "INSERT INTO ocr_jobs(job_id,status,bot_key,chat_id,message_id,created_at,updated_at,error) VALUES(?,?,?,?,?,?,?,?)",
        ("recent-queued", "queued", "bot1", "CHAT1", 102, now_ms, now_ms, ""),
    )
    conn.execute(
        "INSERT INTO ocr_jobs(job_id,status,bot_key,chat_id,message_id,attempts,max_attempts,created_at,updated_at,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("failed-ocr", "failed", "bot2", "CHAT2", 201, 3, 3, old_ms, old_ms, "provider failed"),
    )
    conn.execute(
        "INSERT INTO slips(id,status,is_duplicate,slip_date_iso,created_at,amount) VALUES('ok-slip','success',0,date('now'),?,123.45)",
        (now_ms,),
    )
    conn.commit()
    conn.close()


with tempfile.TemporaryDirectory(prefix="auditslip-watchdog-test-") as tmp:
    tmp_path = Path(tmp)
    db = tmp_path / "auditslip.db"
    state = tmp_path / "watchdog-state.json"
    make_db(db, int(time.time() * 1000) - 45 * 60 * 1000)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--state-file",
            str(state),
            "--dry-run",
            "--json",
            "--no-systemctl",
            "--skip-dashboard",
            "--no-telegram",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout
    payload = json.loads(proc.stdout)
    codes = {alert["code"] for alert in payload["alerts"]}
    assert "queue_stale" in codes, payload
    assert "ocr_failed" in codes, payload
    assert payload["dry_run"] is True, payload
    assert payload["restarts"] == [], payload
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "TOKEN" not in rendered and "SECRET" not in rendered and "provider failed" not in rendered, payload

print("ok: watchdog dry-run detects stuck OCR queue without side effects")
