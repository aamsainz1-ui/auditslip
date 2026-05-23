#!/usr/bin/env python3
"""Guard: dashboard merges OCR variants of the same transferor and displays bank in parentheses."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-name-norm-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-name-norm-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()

def save(idx: int, name: str, bank: str, amount: float) -> None:
    bot.save_slip({
        "id": f"N{idx}",
        "chat_id": "CHAT1",
        "chat_title": "Audit Room",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": f"11:{idx:02d}",
        "transferor_name": name,
        "from_bank": bank,
        "issuer_bank": bank,
        "amount": amount,
    })

save(1, "นาย จรัญ ส.", "SCB", 5058.0)
save(2, "นาย จริญ ส.", "SCB", 4002.0)
save(3, "MR. KUON K***", "ABA", 45044.0)
save(4, "MR. KUON K * * *", "ABA", 4908.0)
save(5, "MR. TES K***", "Krungthai", 34498.0)
save(6, "MR. TES K***", "กรุงไทย", 15358.0)
save(7, "MR. HOEURN S***", "Krungthai", 19668.0)
save(8, "MR. HOEURN S***", "กรุงไทย", 24207.0)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="open")
by_transferor = {row["name"]: row for row in snapshot["by_transferor"]}
assert "จรัญ ส. (SCB)" in by_transferor, by_transferor
assert by_transferor["จรัญ ส. (SCB)"]["count"] == 2, by_transferor
assert by_transferor["จรัญ ส. (SCB)"]["amount"] == 9060.0, by_transferor
assert "นาย จริญ ส." not in by_transferor, by_transferor
assert "KUON K*** (ABA)" in by_transferor, by_transferor
assert by_transferor["KUON K*** (ABA)"]["count"] == 2, by_transferor
assert by_transferor["KUON K*** (ABA)"]["amount"] == 49952.0, by_transferor
assert "TES K*** (KRUNGTHAI)" in by_transferor, by_transferor
assert by_transferor["TES K*** (KRUNGTHAI)"]["count"] == 2, by_transferor
assert by_transferor["TES K*** (KRUNGTHAI)"]["amount"] == 49856.0, by_transferor
assert "TES K*** (กรุงไทย)" not in by_transferor, by_transferor
assert "HOEURN S*** (KRUNGTHAI)" in by_transferor, by_transferor
assert by_transferor["HOEURN S*** (KRUNGTHAI)"]["count"] == 2, by_transferor
assert by_transferor["HOEURN S*** (KRUNGTHAI)"]["amount"] == 43875.0, by_transferor
assert "HOEURN S*** (กรุงไทย)" not in by_transferor, by_transferor
by_from_bank = {row["name"]: row for row in snapshot["by_from_bank"]}
assert by_from_bank["KRUNGTHAI"]["count"] == 4, by_from_bank
assert by_from_bank["KRUNGTHAI"]["amount"] == 93731.0, by_from_bank
assert by_transferor["TES K*** (KRUNGTHAI)"]["limit_amount"] == 50000.0, by_transferor
html = Dash.render_dashboard_html("test-token")
assert "ตั้งวงเงินจากยอดรายวัน" in html and "byTransferor" in html, html
assert "วงเงิน" in html and "transferorLimitTable" in html, html
print("ok: dashboard transferor names normalized and bank-labelled")
