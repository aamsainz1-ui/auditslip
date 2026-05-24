#!/usr/bin/env python3
"""Guard: OCR provider circuit breaker skips flapping providers and exposes safe health metrics."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="auditslip-ocr-circuit-"))
DB_PATH = TMP / "auditslip.db"
STATE_PATH = TMP / "ocr-provider-health.json"
IMG_PATH = TMP / "slip.jpg"
IMG_PATH.write_bytes(b"fake image bytes")

os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_DATA_DIR"] = str(TMP)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(TMP / "exports")
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["OCR_PROVIDERS"] = "gemini,openai"
os.environ["OCR_RETRY_ATTEMPTS"] = "1"
os.environ["OCR_PROVIDER_BREAKER_FAILURE_THRESHOLD"] = "2"
os.environ["OCR_PROVIDER_BREAKER_COOLDOWN_SECONDS"] = "120"
os.environ["OCR_PROVIDER_HEALTH_PATH"] = str(STATE_PATH)
os.environ["AUDITSLIP_HEALTH_SYSTEMCTL"] = "0"
os.environ["AUDITSLIP_WATCHDOG_STATE"] = str(TMP / "watchdog-state.json")
Path(os.environ["AUDITSLIP_WATCHDOG_STATE"]).write_text("{}", encoding="utf-8")

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
Bot = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = Bot
bot_spec.loader.exec_module(Bot)

Bot.AuditslipBot(token="TEST_TOKEN", db_path=DB_PATH, dry_run=True).init_db()

calls = {"gemini": 0, "openai": 0}

def fake_extract_with_provider(provider: str, image_path: Path, mime: str | None = None):
    calls[provider] = calls.get(provider, 0) + 1
    if provider == "gemini":
        raise RuntimeError("HTTP 429 quota exhausted with secret gemini-test-key should not leak")
    return (
        {
            "slip_date_display": "24/05/26",
            "slip_date_iso": "2026-05-24",
            "slip_time": "12:00",
            "amount": 123.45,
            "confidence": 0.99,
            "transferor_name": "Tester",
        },
        {"provider": "openai", "model": "test-openai"},
    )

Bot.extract_with_provider = fake_extract_with_provider  # type: ignore[assignment]

# First two calls try Gemini then fall back to OpenAI. After the second Gemini failure,
# Gemini's circuit should open. The third call must skip Gemini entirely.
for _ in range(3):
    provider, data = Bot.ocr_extract(IMG_PATH, "image/jpeg")
    assert provider == "openai", (provider, data)
    assert data["ocr_provider"] == "openai", data
    assert data["amount"] == 123.45, data

assert calls["openai"] == 3, calls
assert calls["gemini"] == 2, "Gemini should be skipped after its circuit opens"

statuses = {item["provider"]: item for item in Bot.provider_status()}
assert statuses["gemini"]["has_key"] is True, statuses
assert statuses["gemini"]["active"] is False, statuses["gemini"]
assert statuses["gemini"]["circuit_open"] is True, statuses["gemini"]
assert statuses["gemini"]["consecutive_failures"] == 2, statuses["gemini"]
assert statuses["gemini"]["failure_count"] == 2, statuses["gemini"]
assert statuses["gemini"]["skipped_count"] >= 1, statuses["gemini"]
assert statuses["gemini"]["last_error_type"] == "RuntimeError", statuses["gemini"]
assert statuses["openai"]["active"] is True, statuses["openai"]
assert statuses["openai"]["success_count"] == 3, statuses["openai"]
assert statuses["openai"]["consecutive_failures"] == 0, statuses["openai"]

assert STATE_PATH.exists(), "provider health state must be persisted for dashboard health"
state_text = STATE_PATH.read_text(encoding="utf-8")
for forbidden in ["gemini-test-key", "openai-test-key", "quota exhausted", "secret"]:
    assert forbidden not in state_text, f"provider health state leaked {forbidden!r}: {state_text}"

# Dashboard health should surface the same safe provider status without requiring Telegram or provider calls.
dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)
Dash.DB_PATH = DB_PATH
health = Dash.dashboard_operational_health(DB_PATH)
checks = health["checks"]
assert "ocr_providers" in checks, health
provider_health = {item["provider"]: item for item in checks["ocr_providers"]["providers"]}
assert provider_health["gemini"]["circuit_open"] is True, provider_health
assert provider_health["openai"]["success_count"] == 3, provider_health
rendered = json.dumps(health, ensure_ascii=False)
for forbidden in ["gemini-test-key", "openai-test-key", "quota exhausted", "secret"]:
    assert forbidden not in rendered, f"dashboard health leaked {forbidden!r}: {rendered}"

print("ok: OCR provider circuit breaker skips flapping providers and exposes safe health metrics")
