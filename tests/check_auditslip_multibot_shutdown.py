#!/usr/bin/env python3
"""Guard: multi-bot runner can stop cleanly under systemd without blocking forever on non-daemon joins."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "auditslip_bot.py").read_text()
assert "daemon=True, name=f\"auditslip-{cfg['bot_key']}\"" in source, "multi-bot runner threads must be daemonized for fast service restarts"
assert "while True:\n            time.sleep(3600)" in source, "main should sleep and let signals exit instead of blocking forever on join()"
assert "for t in threads:\n        t.join()" not in source, "blocking joins caused systemd stop timeout"
print("ok: multibot shutdown guard")
