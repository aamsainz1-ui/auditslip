#!/usr/bin/env python3
"""Guard: OCR token usage metadata is captured and surfaced in saved slip rows."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "auditslip_bot.py"
DB_PATH = Path(tempfile.mkdtemp(prefix="auditslip-token-tracking-")) / "auditslip.db"

os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-token-export-")))
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["GEMINI_MODEL"] = "gemini-2.5-flash"
os.environ["GEMINI_FALLBACK_MODELS"] = ""
os.environ["GEMINI_THINKING_BUDGET"] = "0"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["OPENAI_MODEL"] = "gpt-4o-mini"

spec = importlib.util.spec_from_file_location("auditslip_bot", MODULE)
assert spec is not None
app = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = app
assert spec.loader is not None
spec.loader.exec_module(app)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.status_code = 200
        self.text = "OK"
        self._payload = payload

    def json(self) -> dict:
        return self._payload


image = Path(tempfile.mkdtemp(prefix="auditslip-token-img-")) / "slip.jpg"
image.write_bytes(b"fake-image")


def fake_gemini_post(url, json, timeout):  # noqa: ANN001
    assert json["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    return FakeResponse(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"slip_date_display":"24/05/69","slip_date_iso":"2026-05-24","amount":123,"confidence":0.99}'
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 700,
                "candidatesTokenCount": 40,
                "thoughtsTokenCount": 0,
                "totalTokenCount": 740,
            },
        }
    )


app.requests.post = fake_gemini_post
gemini_data, gemini_meta = app.gemini_extract(image, "image/jpeg")
assert gemini_data["amount"] == 123, gemini_data
assert gemini_meta["ocr_input_tokens"] == "700", gemini_meta
assert gemini_meta["ocr_output_tokens"] == "40", gemini_meta
assert gemini_meta["ocr_thought_tokens"] == "0", gemini_meta
assert gemini_meta["ocr_total_tokens"] == "740", gemini_meta
assert "usageMetadata" in gemini_meta["ocr_usage_json"], gemini_meta


def fake_openai_post(url, headers, json, timeout):  # noqa: ANN001
    return FakeResponse(
        {
            "choices": [
                {"message": {"content": '{"slip_date_display":"24/05/69","slip_date_iso":"2026-05-24","amount":456,"confidence":0.99}'}}
            ],
            "usage": {
                "prompt_tokens": 900,
                "completion_tokens": 80,
                "total_tokens": 980,
                "completion_tokens_details": {"reasoning_tokens": 12},
            },
        }
    )


app.requests.post = fake_openai_post
openai_data, openai_meta = app.openai_extract(image, "image/jpeg")
assert openai_data["amount"] == 456, openai_data
assert openai_meta["ocr_input_tokens"] == "900", openai_meta
assert openai_meta["ocr_output_tokens"] == "80", openai_meta
assert openai_meta["ocr_thought_tokens"] == "12", openai_meta
assert openai_meta["ocr_total_tokens"] == "980", openai_meta

bot = app.AuditslipBot(token="TEST_TOKEN", db_path=DB_PATH, dry_run=True)
bot.init_db()
bot.save_slip(
    {
        "id": "TOKEN-SLIP-1",
        "chat_id": "CHAT1",
        "message_id": 1,
        "file_id": "FILE1",
        "status": "success",
        "slip_date_display": "24/05/69",
        "slip_date_iso": "2026-05-24",
        "amount": 123.0,
        "confidence": 0.99,
        "ocr_provider": "gemini",
        "ocr_model": "gemini-2.5-flash",
        **{field: gemini_meta[field] for field in app.OCR_USAGE_FIELDS},
    }
)

with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(slips)").fetchall()}
    for col in app.OCR_USAGE_FIELDS:
        assert col in cols, cols
    row = conn.execute("SELECT * FROM slips WHERE id='TOKEN-SLIP-1'").fetchone()
    assert row["ocr_input_tokens"] == 700, dict(row)
    assert row["ocr_output_tokens"] == 40, dict(row)
    assert row["ocr_thought_tokens"] == 0, dict(row)
    assert row["ocr_total_tokens"] == 740, dict(row)
    assert "usageMetadata" in row["ocr_usage_json"], dict(row)

print("ok: OCR token usage metadata captured and saved")
