#!/usr/bin/env python3
"""Guard: dashboard_mutation_log is hash-chained -- /api/audit-chain/verify and the standalone
tools/verify_audit_chain.py both detect tampering with any row.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(tempfile.mkdtemp(prefix="auditslip-audit-chain-")) / "auditslip.db"

os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

# 1. Fresh DB, insert 5 mutations via record_mutation (one via record_endpoint_mutation to cover the wrapper).
Dash.ensure_dashboard_mutation_log_table(DB_PATH)
for i in range(1, 5):
    Dash.record_mutation(
        DB_PATH,
        action=f"act-{i}",
        actor=f"actor-{i}",
        chat_id=f"chat-{i}",
        bot_key="default",
        slip_id=f"S{i}",
        payload={"amount": i * 10, "note": f"row {i}"},
        result_status="ok",
        result_summary=f"row {i} done",
    )
Dash.record_endpoint_mutation(
    DB_PATH,
    action="endpoint-5",
    actor="actor-5",
    request_id="abcdef012345",
    payload={"k": "v"},
    result_status="ok",
    result_summary="row 5 via endpoint",
)

# 2. Verify endpoint logic (call helper directly -- HTTP path is exercised in the tail test).
result = Dash.verify_mutation_chain(DB_PATH)
assert result["ok"] is True, result
assert result["total_rows"] == 5, result
assert result["first_bad_id"] is None, result

# Schema check: prev_hash + entry_hash columns exist and are populated.
with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute("SELECT id, prev_hash, entry_hash FROM dashboard_mutation_log ORDER BY id ASC"))
assert len(rows) == 5, rows
assert rows[0]["prev_hash"] == "", f"row1 prev_hash should be empty seed, got {rows[0]['prev_hash']!r}"
for i in range(1, 5):
    assert rows[i]["prev_hash"] == rows[i - 1]["entry_hash"], (i, rows[i]["prev_hash"], rows[i - 1]["entry_hash"])
    assert len(rows[i]["entry_hash"]) == 64, rows[i]["entry_hash"]

# Idempotency: ensure_dashboard_mutation_log_table re-run is safe even when columns already exist.
Dash._MUTATION_LOG_READY = False  # force re-run path
Dash.ensure_dashboard_mutation_log_table(DB_PATH)

# 3. Tamper with row 3 (modify result_summary directly via SQL).
with sqlite3.connect(DB_PATH) as conn:
    conn.execute("UPDATE dashboard_mutation_log SET result_summary='TAMPERED' WHERE id=3")
    conn.commit()

# 4. Verify endpoint now fails with first_bad_id=3.
result_after = Dash.verify_mutation_chain(DB_PATH)
assert result_after["ok"] is False, result_after
assert result_after["first_bad_id"] == 3, result_after
assert result_after["first_bad_reason"], result_after

# 5. Standalone verifier script also catches it.
verifier_path = ROOT / "tools" / "verify_audit_chain.py"
assert verifier_path.exists(), verifier_path
proc = subprocess.run(
    [sys.executable, str(verifier_path)],
    env={**os.environ, "AUDITSLIP_DB": str(DB_PATH)},
    capture_output=True,
    text=True,
)
assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
assert "RESULT: FAIL" in proc.stdout, proc.stdout
assert "FAIL row id=3" in proc.stdout, proc.stdout

# 6. Clean run on a fresh DB: standalone verifier should pass with exit 0.
clean_db = Path(tempfile.mkdtemp(prefix="auditslip-audit-chain-clean-")) / "auditslip.db"
Dash._MUTATION_LOG_READY = False
Dash.ensure_dashboard_mutation_log_table(clean_db)
for i in range(1, 4):
    Dash.record_mutation(clean_db, action=f"clean-{i}", actor="a", result_summary=f"clean row {i}")
proc_ok = subprocess.run(
    [sys.executable, str(verifier_path)],
    env={**os.environ, "AUDITSLIP_DB": str(clean_db)},
    capture_output=True,
    text=True,
)
assert proc_ok.returncode == 0, (proc_ok.returncode, proc_ok.stdout, proc_ok.stderr)
assert "RESULT: OK" in proc_ok.stdout, proc_ok.stdout

print("ok: dashboard_mutation_log is hash-chained and tamper-evident (endpoint + standalone)")
