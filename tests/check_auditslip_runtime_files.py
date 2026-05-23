#!/usr/bin/env python3
"""Runtime file guard for Auditslip production service."""
from __future__ import annotations

from pathlib import Path
import stat

project = Path('/root/projects/auditslip')
unit = Path('/etc/systemd/system/auditslip-bot.service')
watchdog_service = Path('/etc/systemd/system/auditslip-bot-watchdog.service')
watchdog_timer = Path('/etc/systemd/system/auditslip-bot-watchdog.timer')
env = Path('/etc/auditslip/auditslip.env')

assert (project / 'auditslip_bot.py').exists()
assert unit.exists()
unit_text = unit.read_text()
assert 'EnvironmentFile=/etc/auditslip/auditslip.env' in unit_text
assert 'ExecStart=/usr/bin/python3 /root/projects/auditslip/auditslip_bot.py' in unit_text
assert 'Restart=always' in unit_text
assert watchdog_service.exists()
assert watchdog_timer.exists()
assert env.exists()
assert stat.S_IMODE(env.stat().st_mode) == 0o600
text = env.read_text()
assert 'BOT_DISPLAY_NAME=Auditslip' in text
assert 'OCR_PROVIDERS=gemini,openai' in text
assert 'AUDITSLIP_MAX_SLIPS_PER_POLL=100' in text
assert 'AUDITSLIP_OCR_WORKERS=4' in text
assert 'BOT_TOKEN=' in text and len([line for line in text.splitlines() if line.startswith('BOT_TOKEN=')][0].split('=', 1)[1]) > 20
assert 'OPENAI_MODEL=gpt-4o-mini' in text
print('ok: Auditslip runtime files')
