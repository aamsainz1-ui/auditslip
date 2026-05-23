#!/usr/bin/env python3
"""Guard: bank aliases cover common Thai banks and masked values stay reviewable."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-aliases-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-aliases-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
Bot = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = Bot
bot_spec.loader.exec_module(Bot)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

cases = {
    "ธ.กรุงไทย": "KRUNGTHAI",
    "KTB Next": "KRUNGTHAI",
    "ธนาคารกสิกรไทย จำกัด": "KBANK",
    "SCB EASY": "SCB",
    "Bualuang / BBL": "BANGKOK BANK",
    "ธ.กรุงเทพ": "BANGKOK BANK",
    "ธนาคารออมสิน": "GSB",
    "ธ.ก.ส.": "BAAC",
    "กรุงศรีอยุธยา": "KRUNGSRI",
    "UOB TMRW": "UOB",
    "ธ.ยูโอบี": "UOB",
    "CIMB THAI": "CIMB",
    "ซีไอเอ็มบี ไทย": "CIMB",
    "แลนด์ แอนด์ เฮ้าส์": "LH BANK",
    "LH Bank": "LH BANK",
    "ธอส": "GHB",
    "ธนาคารอาคารสงเคราะห์": "GHB",
    "Thai Credit": "THAI CREDIT",
    "ไทยเครดิต": "THAI CREDIT",
    "TISCO": "TISCO",
    "ทิสโก้": "TISCO",
    "ICBC Thai": "ICBC",
    "ไอซีบีซี": "ICBC",
    "Standard Chartered": "STANDARD CHARTERED",
}
for raw, canonical in cases.items():
    assert Bot.canonical_bank(raw) == canonical, (raw, Bot.canonical_bank(raw))
    assert Dash.display_bank(raw) == canonical, (raw, Dash.display_bank(raw))
    assert Dash.is_known_bank(raw), raw

for masked in ["", "-", "unknown", "N/A", "XXX", "xxxx", "xxx bank", "ไม่ทราบ", "masked"]:
    assert Bot.canonical_bank(masked) == "", (masked, Bot.canonical_bank(masked))
    assert Dash.bank_needs_review(masked), masked
    assert not Dash.is_known_bank(masked), masked

normalized = Bot.normalize_record({"amount": "1,234.50", "from_bank": "xxx bank", "to_bank": "ธ.ยูโอบี", "issuer_bank": "CIMB Thai"})
assert normalized["from_bank"] == "", normalized
assert normalized["to_bank"] == "UOB", normalized
assert normalized["issuer_bank"] == "CIMB", normalized

print("ok: common bank aliases normalize and masked banks remain review items")
