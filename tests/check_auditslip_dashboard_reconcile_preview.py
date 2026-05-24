#!/usr/bin/env python3
"""Guard: reconcile preview/dry-run compares Excel without pending actions or mutation logs."""
from __future__ import annotations

import email.message
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-preview-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-preview-export-")))
os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-preview-import-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()
bot.save_slip({
    "id": "DEP1",
    "bot_key": "botA",
    "company_name": "บริษัท A",
    "chat_id": "CHAT_DEP",
    "chat_title": "บริษัท A เติมมือ",
    "message_id": 1,
    "file_id": "FILE1",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "from_bank": "SCB",
    "from_account": "111-222-333",
    "to_bank": "KBANK",
    "to_account": "999-888-777",
    "amount": 100.0,
    "reference_no": "DEP22",
})

xlsx = Path(os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"]) / "backend-preview.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "Transactions"
ws.append(["รหัส", "เวลา", "ประเภท", "ประเภทดำเนินการ", "ยูสเซอร์", "ธนาคาร", "จำนวน", "จำนวนที่ได้รับ", "ค่าธรรรมเนียม", "เวลาทำรายการ", "หมายเหตุ"])
ws.append(["D22", "2026-05-22 01:00", "ฝาก", "ออโต้", "u1", "SCB", 100.0, "", "", "2026-05-22 01:00", ""])
ws.append(["BONUS", "2026-05-22 02:00", "โบนัส", "โบนัส", "u2", "SCB", 999.0, "", "", "2026-05-22 02:00", "filtered"])
wb.save(xlsx)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)


class _FakeHandler(Dash.DashboardHandler):
    def __init__(self, path: str, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.client_address = ("127.0.0.1", 0)
        self.request_version = "HTTP/1.1"
        self.requestline = f"POST {path} HTTP/1.1"
        self.command = "POST"
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = email.message.Message()
        self.headers["Authorization"] = "Bearer test-token"
        self.headers["X-Auditslip-Action"] = "dashboard"
        self.headers["Content-Type"] = "application/json"
        self.headers["Content-Length"] = str(len(body))
        self._status_code: int = 0
        self._sent_headers: List[Tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:  # type: ignore[override]
        return

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        return

    def json_body(self) -> Dict[str, Any]:
        return json.loads(self.wfile.getvalue().decode("utf-8") or "{}")


def count_rows(table: str) -> int:
    with Dash.connect(db_path) as conn:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
            return int(row["c"] if row else 0)
        except Exception:
            return 0

before_pending = count_rows("pending_actions")
before_mutations = count_rows("dashboard_mutation_log")
handler = _FakeHandler("/api/reconcile?dry_run=1", {"bot_key": "botA", "flow_type": "deposit", "scope": "2026-05-22", "excel_path": str(xlsx)})
handler.do_POST()
assert handler._status_code == 200, (handler._status_code, handler.wfile.getvalue()[:400])
data = handler.json_body()
assert data.get("ok") is True and data.get("dry_run") is True, data
assert data["backend"]["count"] == 1 and data["backend"]["amount"] == 100.0, data
assert data["slips"]["count"] == 1 and data["slips"]["amount"] == 100.0, data
assert data["scope"]["bot_key"] == "botA" and data["scope"]["flow_type"] == "deposit", data
assert data.get("backend_filtered_out", {}).get("count", 0) == 1, data
assert count_rows("pending_actions") == before_pending, data
assert count_rows("dashboard_mutation_log") == before_mutations, data

print("ok: reconcile preview/dry-run compares Excel without pending actions or mutation logs")
