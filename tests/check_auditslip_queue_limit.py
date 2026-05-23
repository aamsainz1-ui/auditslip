#!/usr/bin/env python3
"""Guard: Auditslip processes at most 3 slip images per polling round."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "auditslip_bot.py"
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-queue-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-queue-export-")))
os.environ["AUDITSLIP_MAX_SLIPS_PER_POLL"] = "3"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

spec = importlib.util.spec_from_file_location("auditslip_bot", MODULE)
assert spec is not None
app = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = app
assert spec.loader is not None
spec.loader.exec_module(app)
assert app.MAX_SLIPS_PER_POLL == 3

class FakeBot(app.AuditslipBot):
    def __init__(self):
        super().__init__(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
        self.processed = []
        self.offsets = []
        self.updates = [
            {
                "update_id": i,
                "message": {
                    "message_id": i,
                    "chat": {"id": "CHAT1"},
                    "from": {"id": "U1"},
                    "photo": [{"file_id": f"FILE{i}"}],
                },
            }
            for i in range(1, 6)
        ]

    def telegram_get(self, method, params=None):
        offset = int((params or {}).get("offset", 0) or 0)
        return {"ok": True, "result": [u for u in self.updates if u["update_id"] >= offset]}

    def process_update(self, update):
        self.processed.append(update["update_id"])

    def persist_offset(self, offset):
        self.offsets.append(offset)

bot = FakeBot()
next_offset = bot.poll_once(1)
assert bot.processed == [1, 2, 3], bot.processed
assert next_offset == 4, next_offset
assert bot.offsets[-1] == 4, bot.offsets

next_offset = bot.poll_once(next_offset)
assert bot.processed == [1, 2, 3, 4, 5], bot.processed
assert next_offset == 6, next_offset
print("ok: Auditslip OCR queue limited to 3 slips per polling round")
