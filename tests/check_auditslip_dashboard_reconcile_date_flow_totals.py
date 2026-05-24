#!/usr/bin/env python3
"""Guard: backend reconciliation can compare only deposit/withdraw totals for a selected date."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-date-flow-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-date-flow-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()


def save_slip(idx: int, flow: str, date_iso: str, amount: float, ref: str) -> None:
    bot.save_slip({
        "id": f"S{idx}",
        "bot_key": "botA",
        "company_name": "บริษัท A",
        "chat_id": f"CHAT_{flow}",
        "chat_title": "บริษัท A เติมมือ" if flow == "deposit" else "บริษัท A ถอน",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "22/05/26" if date_iso == "2026-05-22" else "23/05/26",
        "slip_date_iso": date_iso,
        "slip_time": f"10:{idx:02d}",
        "transferor_name": "ลูกค้า",
        "from_bank": "SCB",
        "from_account": "111-222-333",
        "to_bank": "KBANK",
        "to_account": "999-888-777",
        "amount": amount,
        "reference_no": ref,
    })


save_slip(1, "deposit", "2026-05-22", 100.0, "DEP22")
save_slip(2, "withdraw", "2026-05-22", 250.0, "WD22")
save_slip(3, "deposit", "2026-05-23", 999.0, "DEP23")
save_slip(4, "withdraw", "2026-05-23", 888.0, "WD23")

xlsx = Path(tempfile.mkdtemp(prefix="auditslip-backend-date-flow-xlsx-")) / "backend.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "Transactions"
ws.append(["รหัส", "เวลา", "ประเภท", "ประเภทดำเนินการ", "ยูสเซอร์", "ธนาคาร", "จำนวน", "จำนวนที่ได้รับ", "ค่าธรรรมเนียม", "เวลาทำรายการ", "หมายเหตุ"])
ws.append(["D22", "2026-05-22 01:00", "ฝาก", "ออโต้", "u1", "SCB", 100.0, "", "", "2026-05-22 01:00", ""])
ws.append(["W22", "2026-05-22 02:00", "ถอน", "ถอน", "u2", "SCB", 250.0, 0.0, 0.0, "2026-05-22 02:00", ""])
ws.append(["BONUS22", "2026-05-22 03:00", "โบนัส", "โบนัส", "u3", "-", 777.0, "", "", "2026-05-22 03:00", "ต้องไม่เอามารวมฝากถอน"])
ws.append(["CANCEL22", "2026-05-22 04:00", "ยกเลิก", "ยกเลิก", "u4", "-", 555.0, "", "", "2026-05-22 04:00", "ต้องไม่เอามารวมฝากถอน"])
ws.append(["D23", "2026-05-23 01:00", "ฝาก", "ออโต้", "u5", "SCB", 999.0, "", "", "2026-05-23 01:00", "ต้องถูกตัดออกเมื่อเลือก 22"])
ws.append(["W23", "2026-05-23 02:00", "ถอน", "ถอน", "u6", "SCB", 888.0, "", "", "2026-05-23 02:00", "ต้องถูกตัดออกเมื่อเลือก 22"])
wb.save(xlsx)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

res_dep = Dash.reconcile_backend_excel(db_path, xlsx, bot_key="botA", flow_type="deposit", scope="2026-05-22")
assert res_dep["backend"]["count"] == 1, res_dep
assert res_dep["backend"]["amount"] == 100.0, res_dep
assert res_dep["slips"]["count"] == 1 and res_dep["slips"]["amount"] == 100.0, res_dep
assert res_dep["scope"]["date_scope"] == "2026-05-22", res_dep["scope"]
assert res_dep.get("backend_filtered_out", {}).get("count", 0) >= 4, res_dep

res_wd = Dash.reconcile_backend_excel(db_path, xlsx, bot_key="botA", flow_type="withdraw", scope="2026-05-22")
assert res_wd["backend"]["count"] == 1, res_wd
assert res_wd["backend"]["amount"] == 250.0, res_wd
assert res_wd["slips"]["count"] == 1 and res_wd["slips"]["amount"] == 250.0, res_wd

html = Dash.render_dashboard_html("test-token")
for marker in [
    "reconcileDateScope",
    "3 เลือกวันที่เทียบ",
    "reconcileScopeValue()",
    "form.append('scope', scope)",
    "scope, excel_path",
]:
    assert marker in html, marker

print("ok: reconcile filters backend Excel by selected date and deposit/withdraw flow")
