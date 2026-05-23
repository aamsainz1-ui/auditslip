#!/usr/bin/env python3
"""Runtime guard for Auditslip SQLite backup timer."""
from __future__ import annotations
from pathlib import Path

script = Path('/root/projects/auditslip/auditslip-backup.py')
service = Path('/etc/systemd/system/auditslip-backup.service')
timer = Path('/etc/systemd/system/auditslip-backup.timer')
for p in [script, service, timer]:
    assert p.exists(), f'missing {p}'
assert 'EnvironmentFile=/etc/auditslip/auditslip.env' in service.read_text()
assert 'ExecStart=/usr/bin/python3 /root/projects/auditslip/auditslip-backup.py' in service.read_text()
assert 'OnUnitActiveSec=30min' in timer.read_text()
assert 'Persistent=true' in timer.read_text()
print('ok: Auditslip backup timer files')
