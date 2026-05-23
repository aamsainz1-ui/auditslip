#!/usr/bin/env python3
"""Guard: telegram_get wraps network/decode errors as RuntimeError."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
import auditslip_bot as ab


def make_bot() -> ab.AuditslipBot:
    return ab.AuditslipBot(token="t", bot_key="test", company_name="t", dry_run=False)


def assert_raises_runtime(callable_, needle: str) -> None:
    try:
        callable_()
    except RuntimeError as exc:
        assert needle in str(exc), f"missing {needle!r} in {exc!r}"
        return
    raise AssertionError(f"expected RuntimeError containing {needle!r}")


bot = make_bot()

with patch.object(ab.requests, "get", side_effect=requests.ConnectionError("boom")):
    assert_raises_runtime(lambda: bot.telegram_get("getUpdates"), "network error")

resp500 = MagicMock()
resp500.status_code = 500
resp500.raise_for_status.side_effect = requests.HTTPError("500 server error")
with patch.object(ab.requests, "get", return_value=resp500):
    assert_raises_runtime(lambda: bot.telegram_get("getUpdates"), "network error")

resp_bad = MagicMock()
resp_bad.status_code = 200
resp_bad.raise_for_status.return_value = None
resp_bad.json.side_effect = ValueError("not json")
with patch.object(ab.requests, "get", return_value=resp_bad):
    assert_raises_runtime(lambda: bot.telegram_get("getUpdates"), "network error")

print("ok: auditslip_bot telegram_get wraps network/decode errors")
