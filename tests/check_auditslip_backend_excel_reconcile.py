#!/usr/bin/env python3
"""Guard: dashboard can reconcile backend Excel rows against captured Auditslip slips."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()

def save_slip(idx: int, date_display: str, amount: float, ref: str, name: str = "จรัญ", duplicate: int = 0) -> None:
    bot.save_slip({
        "id": f"S{idx}",
        "chat_id": "CHAT1",
        "chat_title": "Audit Room",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": date_display,
        "slip_date_iso": "2026-05-22" if date_display == "22/05/26" else "2026-05-21",
        "slip_time": f"10:{idx:02d}",
        "transferor_name": name,
        "from_bank": "SCB",
        "amount": amount,
        "reference_no": ref,
        "is_duplicate": duplicate,
    })

save_slip(1, "22/05/26", 100.0, "REF100")
save_slip(2, "21/05/26", 200.0, "REF200")
save_slip(3, "22/05/26", 333.0, "EXTRA333")
save_slip(4, "22/05/26", 999.0, "DUP999", duplicate=1)

xlsx = Path(tempfile.mkdtemp(prefix="auditslip-backend-xlsx-")) / "backend.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "backend"
ws.append(["วันที่", "ชื่อผู้โอน", "ธนาคาร", "ยอดเงิน", "เลขอ้างอิง"])
ws.append(["22/05/26", "จรัญ", "SCB", 100.0, "REF100"])
ws.append(["22/05/26", "สมชาย", "KBank", 50.0, "MISSING50"])
wb.save(xlsx)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

result = Dash.reconcile_backend_excel(Path(os.environ["AUDITSLIP_DB"]), xlsx, chat_id="CHAT1", scope="all")
assert result["ok"] is True, result
assert result["backend"]["count"] == 2, result
assert result["backend"]["amount"] == 150.0, result
assert result["slips"]["count"] == 3, result  # duplicate excluded
assert result["slips"]["amount"] == 633.0, result
assert result["matched"]["count"] == 1, result
assert result["matched"]["amount"] == 100.0, result
assert result["missing_in_slips"][0]["reference"] == "MISSING50", result
extra_refs = {row["reference"] for row in result["extra_slips"]}
assert {"REF200", "EXTRA333"}.issubset(extra_refs), result
html = Dash.render_dashboard_html("test-token")
assert "เทียบ Excel หลังบ้าน" in html and "/api/reconcile" in html, html
print("ok: backend Excel reconciles against captured slips")
