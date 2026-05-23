#!/usr/bin/env python3
"""Guard: watchdog restart backoff caps at 3/hour and prunes older entries."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auditslip_watchdog import check_restart_backoff, record_restart  # noqa: E402

BKK = timezone(timedelta(hours=7))
SVC = "auditslip-dashboard.service"


with tempfile.TemporaryDirectory(prefix="auditslip-backoff-") as tmp:
    log = Path(tmp) / "watchdog_restart_log.json"

    # Case 1: four restart attempts within 60 minutes -> 4th must be blocked
    base = datetime(2026, 5, 22, 12, 0, 0, tzinfo=BKK)
    for i in range(3):
        ts = base + timedelta(minutes=i * 10)
        allowed, _ = check_restart_backoff(log, SVC, ts)
        assert allowed, f"attempt {i+1} within window should be allowed"
        record_restart(log, SVC, ts)
    fourth = base + timedelta(minutes=40)
    allowed, recent = check_restart_backoff(log, SVC, fourth)
    assert not allowed, f"4th restart within 60min must be blocked, recent={recent}"
    assert len(recent) == 3, recent

    # Case 2: four restarts spread over 90 minutes -> all allowed
    log2 = Path(tmp) / "log2.json"
    base2 = datetime(2026, 5, 22, 15, 0, 0, tzinfo=BKK)
    for i in range(4):
        ts = base2 + timedelta(minutes=i * 30)  # 0, 30, 60, 90
        allowed, recent = check_restart_backoff(log2, SVC, ts)
        assert allowed, f"spread attempt {i+1} should be allowed, recent={recent}"
        record_restart(log2, SVC, ts)

    # Case 3: per-service isolation
    log3 = Path(tmp) / "log3.json"
    base3 = datetime(2026, 5, 22, 18, 0, 0, tzinfo=BKK)
    for i in range(3):
        record_restart(log3, "auditslip-bot.service", base3 + timedelta(minutes=i))
    allowed, _ = check_restart_backoff(log3, SVC, base3 + timedelta(minutes=5))
    assert allowed, "dashboard backoff must not count bot restarts"

print("ok: watchdog restart backoff caps at 3/hour and is per-service")
