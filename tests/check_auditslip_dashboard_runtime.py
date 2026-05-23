#!/usr/bin/env python3
"""Runtime guard for Auditslip dashboard service."""
from __future__ import annotations

from pathlib import Path
import stat

env = Path('/etc/auditslip/auditslip.env')
service = Path('/etc/systemd/system/auditslip-dashboard.service')
assert env.exists()
text = env.read_text()
for marker in [
    'AUDITSLIP_DASHBOARD_HOST=0.0.0.0',
    'AUDITSLIP_DASHBOARD_PORT=8095',
    'AUDITSLIP_DASHBOARD_TOKEN=',
]:
    assert marker in text, f'missing env marker {marker}'
token = [line.split('=', 1)[1] for line in text.splitlines() if line.startswith('AUDITSLIP_DASHBOARD_TOKEN=')][0]
assert len(token) >= 24
assert stat.S_IMODE(env.stat().st_mode) == 0o600
assert service.exists()
s = service.read_text()
assert 'EnvironmentFile=/etc/auditslip/auditslip.env' in s
assert 'ExecStart=/usr/bin/python3 /root/projects/auditslip/auditslip_dashboard.py' in s
assert 'Restart=always' in s
print('ok: Auditslip dashboard runtime files')
