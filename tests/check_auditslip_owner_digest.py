#!/usr/bin/env python3
"""Guard: tools/owner_digest.py produces a correct digest from a fixture DB and
flags audit-chain tamper with exit code 4.

This test only uses --dry-run; no Telegram traffic is generated.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = ROOT / "tools" / "owner_digest.py"
assert DIGEST.exists(), DIGEST


# Mirror compute_mutation_hash so the fixture builds a valid chain without
# depending on auditslip_dashboard.
_EXCLUDE = ("id", "entry_hash")


def compute_mutation_hash(prev_hash: str, row: dict) -> str:
    canonical_obj = {k: row[k] for k in sorted(row.keys()) if k not in _EXCLUDE}
    canonical = json.dumps(canonical_obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(((prev_hash or "") + "|" + canonical).encode("utf-8")).hexdigest()


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE slips (
          id TEXT PRIMARY KEY,
          chat_id TEXT NOT NULL,
          chat_title TEXT,
          status TEXT NOT NULL DEFAULT 'success',
          transferor_name TEXT,
          from_account TEXT,
          amount REAL DEFAULT 0,
          is_duplicate INTEGER DEFAULT 0,
          created_at INTEGER NOT NULL,
          created_at_iso TEXT NOT NULL,
          bot_key TEXT NOT NULL DEFAULT 'default'
        );
        CREATE TABLE ocr_jobs (
          job_id TEXT PRIMARY KEY,
          slip_id TEXT NOT NULL,
          chat_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          file_id TEXT NOT NULL,
          next_run_at INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3
        );
        CREATE TABLE dashboard_mutation_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts_iso TEXT NOT NULL,
          action TEXT NOT NULL,
          actor TEXT,
          chat_id TEXT,
          bot_key TEXT,
          slip_id TEXT,
          payload_json TEXT,
          result_status TEXT NOT NULL,
          result_summary TEXT,
          prev_hash TEXT DEFAULT '',
          entry_hash TEXT DEFAULT ''
        );
        CREATE TABLE pending_actions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          requested_by TEXT NOT NULL,
          requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          approved_by TEXT,
          approved_at TEXT,
          executed_at TEXT,
          executed_result TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          expires_at TEXT NOT NULL,
          request_id TEXT NOT NULL
        );
        """
    )
    now = int(time.time())
    # withdraw chat (matches token 'withdraw') -- 4 slips: 2 from A, 1 from B, 1 dup (must NOT count)
    rows = [
        ("S1", "C1", "Company-X (withdraw)", "success", "นาย ก ทดสอบ", "1234567890", 12000.0, 0),
        ("S2", "C1", "Company-X (withdraw)", "success", "นาย ก ทดสอบ", "1234567890", 8000.0, 0),
        ("S3", "C1", "Company-X (withdraw)", "success", "นาง ข ทดสอบ", "9876543210", 5000.0, 0),
        ("S4", "C1", "Company-X (withdraw)", "success", "นาง ข ทดสอบ", "9876543210", 9999.0, 1),  # duplicate -> excluded
        ("S5", "C2", "Company-X (ฝาก)", "success", "นาย ค", "5555444433", 3000.0, 0),  # deposit
        ("S6", "C2", "Company-X (ฝาก)", "success", "นาย ค", "5555444433", 7000.0, 0),  # deposit
        ("S7", "C3", "misc group", "unclear", "", "", 0.0, 0),   # stuck
        ("S8", "C3", "misc group", "unclear", "", "", 0.0, 0),   # stuck
        ("S9", "C3", "misc group", "error", "", "", 0.0, 0),     # failed
    ]
    for sid, cid, title, status, name, acct, amt, dup in rows:
        cur.execute(
            "INSERT INTO slips(id,chat_id,chat_title,status,transferor_name,from_account,amount,is_duplicate,created_at,created_at_iso) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, cid, title, status, name, acct, amt, dup, now, "2026-05-23T02:00:00Z"),
        )
    cur.execute(
        "INSERT INTO ocr_jobs(job_id,slip_id,chat_id,status,created_at,updated_at,file_id) "
        "VALUES('J1','S7','C3','failed',?,?,'fid1')",
        (now, now),
    )

    # Build a 3-row valid hash chain.
    base_rows = [
        {"ts_iso": "2026-05-23T01:00:00", "action": "delete", "actor": "owner", "chat_id": "C1", "bot_key": "default", "slip_id": "S1", "payload_json": "{}", "result_status": "ok", "result_summary": "row 1"},
        {"ts_iso": "2026-05-23T02:00:00", "action": "reprocess", "actor": "owner", "chat_id": "C1", "bot_key": "default", "slip_id": "S2", "payload_json": "{}", "result_status": "ok", "result_summary": "row 2"},
        {"ts_iso": "2026-05-23T03:00:00", "action": "reprocess", "actor": "owner", "chat_id": "C1", "bot_key": "default", "slip_id": "S3", "payload_json": "{}", "result_status": "ok", "result_summary": "row 3"},
    ]
    last_hash = ""
    for i, br in enumerate(base_rows, start=1):
        row_for_hash = dict(br)
        row_for_hash["id"] = i
        row_for_hash["prev_hash"] = last_hash
        eh = compute_mutation_hash(last_hash, row_for_hash)
        cur.execute(
            "INSERT INTO dashboard_mutation_log(ts_iso,action,actor,chat_id,bot_key,slip_id,payload_json,result_status,result_summary,prev_hash,entry_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (br["ts_iso"], br["action"], br["actor"], br["chat_id"], br["bot_key"], br["slip_id"], br["payload_json"], br["result_status"], br["result_summary"], last_hash, eh),
        )
        last_hash = eh

    # Pending actions: 2 pending, 1 approved, 1 expired.
    for status in ("pending", "pending", "approved", "expired"):
        cur.execute(
            "INSERT INTO pending_actions(action,payload_json,requested_by,status,expires_at,request_id) "
            "VALUES('delete','{}','owner',?, '2099-01-01T00:00:00','rid-' || ?)",
            (status, status),
        )

    conn.commit()
    conn.close()


def run_digest(db_path: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "AUDITSLIP_WATCHDOG_BOT_TOKEN", "AUDITSLIP_WATCHDOG_ALERT_CHAT_ID", "AUDITSLIP_ADMIN_IDS"))}
    return subprocess.run(
        [sys.executable, str(DIGEST), "--dry-run", "--db", str(db_path)],
        env=env,
        capture_output=True,
        text=True,
    )


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="auditslip-owner-digest-"))
    db_path = tmpdir / "auditslip.db"
    make_db(db_path)

    # 1. Healthy run -> exit 0, expected sections + totals.
    proc = run_digest(db_path)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    out = proc.stdout
    # section headers
    assert "Auditslip Daily Digest" in out, out
    assert "💰 ยอด 24h" in out, out
    assert "ฝาก:" in out and "ถอน:" in out, out
    assert "📊 Top 5 ผู้โอน (ถอน)" in out, out
    assert "🔧 Mutations 24h" in out, out
    assert "⏳ Pending approvals:" in out, out
    assert "🔐 Audit chain:" in out, out
    assert "⚠️ Queue:" in out, out

    # totals: withdraw counted = S1+S2+S3 = 25,000; deposit = 10,000; total slips counted = 5
    assert "ถอน: ฿25,000" in out, out
    assert "ฝาก: ฿10,000" in out, out
    # excluded duplicate -> total amount 35,000 / 5 slips
    assert "(สลิป 5 ใบ)" in out, out
    assert "฿35,000" in out, out
    # top transferors: นาย ก 20,000 (2 ครั้ง), นาง ข 5,000 (1 ครั้ง)
    assert "นาย ก ทดสอบ" in out and "20,000" in out and "(2 ครั้ง)" in out, out
    assert "นาง ข ทดสอบ" in out and "5,000" in out, out
    # account masking last-4
    assert "xxx7890" in out and "xxx3210" in out, out
    # mutations
    assert "delete: 1" in out, out
    assert "reprocess: 2" in out, out
    # pending bucket counts
    assert "Pending approvals: 4" in out, out
    assert "pending: 2" in out and "approved: 1" in out and "expired: 1" in out, out
    # chain OK
    assert "Audit chain: ✅ OK (3 rows)" in out, out
    # queue: 2 stuck + 1 failed slip + 1 failed job = 2 stuck, 2 failed
    assert "Queue: 2 stuck, 2 failed" in out, out

    # 2. Tamper row 2 (modify result_summary directly) -> chain breaks at row 2 + exit code 4.
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE dashboard_mutation_log SET result_summary='TAMPERED' WHERE id=2")
        conn.commit()
    proc2 = run_digest(db_path)
    assert proc2.returncode == 4, (proc2.returncode, proc2.stdout, proc2.stderr)
    assert "Audit chain: ❌ TAMPER at row 2" in proc2.stdout, proc2.stdout
    # Digest should still be fully rendered even when tampered.
    assert "Auditslip Daily Digest" in proc2.stdout, proc2.stdout
    assert "📊 Top 5 ผู้โอน (ถอน)" in proc2.stdout, proc2.stdout

    print("ok: owner_digest renders sections + totals, flags tamper with exit code 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
