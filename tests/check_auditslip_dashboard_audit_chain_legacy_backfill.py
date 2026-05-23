#!/usr/bin/env python3
"""Guard: legacy mutation_log rows get one-time hash-chain backfill after Phase B deploy."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-chain-legacy-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-chain-legacy-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec is not None and spec.loader is not None
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

DB_PATH = Path(os.environ["AUDITSLIP_DB"])
with sqlite3.connect(DB_PATH) as conn:
    conn.execute(
        """
        CREATE TABLE dashboard_mutation_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts_iso TEXT NOT NULL,
          action TEXT NOT NULL,
          actor TEXT DEFAULT '',
          chat_id TEXT DEFAULT '',
          bot_key TEXT DEFAULT '',
          slip_id TEXT DEFAULT '',
          payload_json TEXT DEFAULT '{}',
          result_status TEXT DEFAULT '',
          result_summary TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO dashboard_mutation_log(ts_iso, action, actor, payload_json, result_status, result_summary) VALUES (?,?,?,?,?,?)",
        ("2026-05-23T00:00:00+00:00", "delete", "actor1", "{}", "ok", "legacy row"),
    )
    conn.execute(
        "INSERT INTO dashboard_mutation_log(ts_iso, action, actor, payload_json, result_status, result_summary) VALUES (?,?,?,?,?,?)",
        ("2026-05-23T00:01:00+00:00", "close", "actor2", "{}", "ok", "legacy row 2"),
    )
    conn.commit()

# ensure() must add prev_hash/entry_hash and backfill existing legacy rows exactly once.
Dash.ensure_dashboard_mutation_log_table(DB_PATH)
result = Dash.verify_mutation_chain(DB_PATH)
assert result["ok"] is True, result
assert result["total_rows"] == 2, result

with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT prev_hash, entry_hash FROM dashboard_mutation_log ORDER BY id").fetchall()
    assert rows[0]["prev_hash"] == "", dict(rows[0])
    assert rows[0]["entry_hash"], dict(rows[0])
    assert rows[1]["prev_hash"] == rows[0]["entry_hash"], [dict(r) for r in rows]
    assert rows[1]["entry_hash"], dict(rows[1])

print("ok: legacy mutation log rows are hash-chain backfilled")
