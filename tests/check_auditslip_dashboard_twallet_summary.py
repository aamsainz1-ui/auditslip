#!/usr/bin/env python3
"""Guard: Auditslip dashboard embeds a safe True Wallet summary card."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-twallet-summary-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-twallet-summary-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["AUDITSLIP_TWALLET_DASHBOARD_URL"] = "http://twallet.local"
os.environ["AUDITSLIP_TWALLET_CACHE_TTL"] = "0"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
Bot = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = Bot
bot_spec.loader.exec_module(Bot)

bot = Bot.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


calls: list[str] = []

def fake_get(url: str, timeout: float = 0):
    calls.append(url)
    if url.endswith("/health"):
        return FakeResponse({"ok": True, "tokensLoaded": True, "txCount": 2911})
    if url.endswith("/api/tm/balance"):
        return FakeResponse({"status": "ok", "data": {"balance": "1569223", "mobile_no": "0631234433", "updated_at": "2026-05-23 14:23:49"}})
    if url.endswith("/api/stats/daily?days=1"):
        return FakeResponse({"ok": True, "items": [{"date": "2026-05-23", "count": 42, "total": 12345.67}]})
    if url.endswith("/api/tm/my-last-receive"):
        return FakeResponse({"status": "ok", "data": {"amount": 20400, "sender_mobile": "0619999944", "receiver_mobile": "0631234433", "received_time": "2026-05-23 14:20:32", "transaction_id": "50099999999974", "event_type": "P2P", "message": ""}})
    raise AssertionError(url)

Dash.requests.get = fake_get
summary = Dash.fetch_twallet_summary(force=True)
assert summary["ok"] is True, summary
assert summary["tx_count"] == 2911, summary
assert summary["balance_amount"] == 15692.23, summary
assert summary["today_count"] == 42, summary
assert summary["today_total"] == 12345.67, summary
assert summary["last_receive"]["amount"] == 204.0, summary
assert summary["mobile_masked"] == "063***33", summary
assert summary["last_receive"]["sender_mobile"] == "061***44", summary
assert "0619999944" not in str(summary), summary

snap = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), bot_key="__all__", flow_type="all", scope="today")
assert snap["twallet_summary"]["today_total"] == 12345.67, snap.get("twallet_summary")

html = Dash.render_dashboard_html("test-token")
for marker in ["twalletSummary", "twalletTodayAmount", "True Wallet", "renderTWalletSummary"]:
    assert marker in html, marker
assert "twallet.local" not in html, "do not bake backend URL into rendered HTML"

print("ok: dashboard exposes safe True Wallet summary data and UI markers")
