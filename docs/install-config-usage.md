# Auditslip installation, configuration, and usage

This document is the operator/developer setup guide for Auditslip: Telegram slip OCR bot, SQLite ledger, dashboard, exports, reconciliation, bank-ledger preview/import, watchdog, and backups.

For the detailed “create bot → add to group → connect every API” walkthrough, use [`docs/bot-api-setup.md`](bot-api-setup.md).

No real tokens or production secrets belong in git. Put real secrets only in `/etc/auditslip/auditslip.env` on the server.

## 1. What Auditslip does

- Receives payment slip images from Telegram groups/chats.
- OCRs slips through configured providers (`gemini`, `openai`).
- Stores normalized slip evidence in SQLite WAL mode.
- Excludes duplicates from financial totals by default.
- Shows an operator dashboard with company/flow/date filters.
- Exports Excel/ZIP workbooks for audit/accounting.
- Supports safe read-only previews for export/reconcile/statement-ledger workflows.
- Routes high-risk mutations through pending approval/audit-chain logs.
- Runs watchdog and backup timers for production reliability.

## 2. Runtime layout

Default production layout:

- Project: `/root/projects/auditslip`
- Environment file: `/etc/auditslip/auditslip.env`
- SQLite DB: `/root/projects/auditslip/data/auditslip.db`
- Slip images: `/root/projects/auditslip/data/slip-images/`
- Exports: `/root/projects/auditslip/exports/`
- Backend/statement imports: `/root/projects/auditslip/imports/backend/`
- DB backups: `/root/projects/auditslip/backups/db/`
- Bot service: `auditslip-bot.service`
- Dashboard service: `auditslip-dashboard.service`
- Watchdog timer: `auditslip-bot-watchdog.timer`
- Backup timer: `auditslip-backup.timer`

## 3. Fresh install on Ubuntu/VPS

### 3.1 Install OS packages

The production systemd templates use `/usr/bin/python3`.

```bash
sudo apt update
sudo apt install -y git python3 python3-requests python3-openpyxl sqlite3 curl
```

Alternative: use a Python venv, install `requirements.txt`, and edit the `ExecStart=` lines in `systemd/*.service` to point to the venv Python.

### 3.2 Clone the repository

```bash
sudo mkdir -p /root/projects
cd /root/projects
git clone https://github.com/aamsainz1-ui/auditslip.git
cd /root/projects/auditslip
```

### 3.3 Create runtime directories

```bash
sudo mkdir -p \
  /etc/auditslip \
  /root/projects/auditslip/data/slip-images \
  /root/projects/auditslip/exports \
  /root/projects/auditslip/imports/backend \
  /root/projects/auditslip/backups/db
```

### 3.4 Create environment file

```bash
sudo cp /root/projects/auditslip/.env.example /etc/auditslip/auditslip.env
sudo chmod 600 /etc/auditslip/auditslip.env
sudo nano /etc/auditslip/auditslip.env
```

Fill real tokens/API keys in `/etc/auditslip/auditslip.env` only. Do not edit `.env.example` with real secrets.

Minimum required values:

- Telegram token:
  - single bot: `BOT_TOKEN=...`
  - multi-bot: `BOT_TOKEN_1=...` etc + `AUDITSLIP_TELEGRAM_BOTS=bot1:BOT_TOKEN_1:บริษัท 1,...`
- OCR provider key:
  - `GEMINI_API_KEY=...` and/or `OPENAI_API_KEY=...`
- Dashboard/admin:
  - `AUDITSLIP_DASHBOARD_TOKEN=...`
  - `AUDITSLIP_DASHBOARD_OWNER_USER=owner`
  - `AUDITSLIP_DASHBOARD_OWNER_PASSWORD=...`

### 3.5 Install systemd units

```bash
sudo cp systemd/auditslip-bot.service /etc/systemd/system/
sudo cp systemd/auditslip-dashboard.service /etc/systemd/system/
sudo cp systemd/auditslip-bot-watchdog.service /etc/systemd/system/
sudo cp systemd/auditslip-bot-watchdog.timer /etc/systemd/system/
sudo cp systemd/auditslip-backup.service /etc/systemd/system/
sudo cp systemd/auditslip-backup.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now auditslip-bot.service auditslip-dashboard.service
sudo systemctl enable --now auditslip-bot-watchdog.timer auditslip-backup.timer
```

Optional owner digest:

```bash
sudo cp systemd/auditslip-owner-digest.service /etc/systemd/system/
sudo cp systemd/auditslip-owner-digest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now auditslip-owner-digest.timer
```

### 3.6 Verify install

```bash
cd /root/projects/auditslip
python3 -m py_compile auditslip_bot.py auditslip_dashboard.py auditslip_watchdog.py auditslip_bank_ledger.py
python3 tests/check_auditslip_product_contract.py
systemctl is-active auditslip-bot.service auditslip-dashboard.service
curl -fsS 'http://127.0.0.1:8095/api/health?quick=1'
```

If the dashboard is public behind a reverse proxy, verify the public URL separately.

## 4. Configuration reference

### 4.1 Telegram bot config

For step-by-step BotFather creation, group insertion, chat ID discovery, `AUDITSLIP_TELEGRAM_BOTS`, flow mapping, and Telegram API verification, see [`docs/bot-api-setup.md`](bot-api-setup.md).

Single bot:

```env
BOT_TOKEN=
BOT_DISPLAY_NAME=Auditslip
```

Multi-company/multi-bot:

```env
BOT_TOKEN_1=
BOT_TOKEN_2=
AUDITSLIP_TELEGRAM_BOTS="bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2"
```

`AUDITSLIP_TELEGRAM_BOTS` entries are `bot_key:TOKEN_ENV_NAME:company_name`.

Telegram group checklist:

1. Create a bot with BotFather.
2. Put the token into `/etc/auditslip/auditslip.env`.
3. Add the bot to each Telegram group that sends slips.
4. If the bot must read all group slip images, make sure Telegram privacy settings/permissions allow it. In many group setups, disable privacy mode with BotFather or make the bot an admin.
5. Send a test slip image and verify `/recent` or dashboard recent rows.

### 4.2 OCR provider config

Recommended default:

```env
OCR_PROVIDERS=gemini,openai
GEMINI_MODEL=gemini-2.5-flash
GEMINI_THINKING_BUDGET=0
GEMINI_THINKING_FALLBACK_ENABLED=1
GEMINI_FALLBACK_THINKING_BUDGET=-1
OPENAI_MODEL=gpt-4o-mini
OCR_RETRY_ATTEMPTS=3
OCR_RETRY_BASE_DELAY=2
```

At least one provider key must be set:

```env
GEMINI_API_KEY=
OPENAI_API_KEY=
```

Notes:

- Gemini no-thinking-first (`GEMINI_THINKING_BUDGET=0`) keeps simple slip extraction cheaper.
- Keep fallback thinking enabled so unclear/invalid parse cases can retry with dynamic thinking.
- Token/cost metrics are recorded only for rows processed after usage tracking is enabled.

### 4.3 Queue and Telegram reply config

```env
AUDITSLIP_POLL_TIMEOUT=30
AUDITSLIP_MAX_SLIPS_PER_POLL=100
AUDITSLIP_OCR_WORKERS=4
AUDITSLIP_OCR_JOB_MAX_ATTEMPTS=3
AUDITSLIP_OCR_JOB_STALE_MS=600000
AUDITSLIP_OCR_WORKER_IDLE_SLEEP=0.5
AUDITSLIP_UNCLEAR_MIN_CONFIDENCE=0.65
AUDITSLIP_REPLY_ON_QUEUE=0
AUDITSLIP_REPLY_ON_RESULT=1
```

Production groups often set queue replies off to avoid noise. Result replies depend on operator preference.

### 4.4 Dashboard config

```env
AUDITSLIP_DASHBOARD_HOST=0.0.0.0
AUDITSLIP_DASHBOARD_PORT=8095
AUDITSLIP_DASHBOARD_TOKEN=
AUDITSLIP_DASHBOARD_OWNER_USER=owner
AUDITSLIP_DASHBOARD_OWNER_PASSWORD=
AUDITSLIP_SIMPLE_APPROVAL=1
AUDITSLIP_ALERT_ON_MUTATION=1
```

Access patterns:

- Public/read-only dashboard routes can be used for viewing when configured.
- Mutations/admin actions require an authorized role/session/token.
- Owner login uses `AUDITSLIP_DASHBOARD_OWNER_USER` + `AUDITSLIP_DASHBOARD_OWNER_PASSWORD` and sets a session cookie.
- Avoid spreading token-in-URL links; prefer owner login/session for admin actions.

### 4.5 Deposit/withdraw flow mapping

If group titles are generic, use explicit mapping instead of title heuristics:

```env
AUDITSLIP_FLOW_MAP="bot1|CHAT_ID_DEPOSIT=deposit,bot1|CHAT_ID_WITHDRAW=withdraw"
```

Valid flow values:

- `deposit`
- `withdraw`
- `other`
- `all` for dashboard/API filter usage

This mapping affects dashboard display and SQL-filtered totals.

### 4.6 Backup/watchdog config

```env
AUDITSLIP_WATCHDOG_AUTO_RESTART=1
AUDITSLIP_WATCHDOG_STALE_MINUTES=15
AUDITSLIP_WATCHDOG_FAILED_THRESHOLD=1
AUDITSLIP_WATCHDOG_ALERT_THROTTLE_SEC=1800
AUDITSLIP_WATCHDOG_ALERT_CHAT_ID=
AUDITSLIP_ADMIN_IDS=
AUDITSLIP_BACKUP_DIR=/root/projects/auditslip/backups/db
AUDITSLIP_BACKUP_RETENTION_DAYS=14
```

Watchdog checks service state, quick dashboard health, queue stale/failed rows, provider status, and optional alert delivery.

## 5. How to use Telegram commands

Send these commands in a Telegram chat/group where the bot is present:

- `/help` — show commands.
- `/summary [open|today|all|DD/MM/YY]` — totals for the selected scope.
- `/today` — today summary.
- `/daily [all]` — daily totals.
- `/names [open|today|all|DD/MM/YY]` — totals by transferor/name.
- `/userall` — alias for name summary.
- `/excel [open|today|all|DD/MM/YY]` — send Excel export.
- `/close [note]` — close/settle current open period while preserving history.
- `/clear` — show permanent clear instructions.
- `/clear confirm` — permanently clear this chat scope; use carefully.
- `/queue` or `/failed` — show unclear/error OCR queue.
- `/reprocess [id]` — retry OCR for a failed/unclear item.
- `/recent` — show latest slips.
- `/stats` — show bot/chat statistics.
- `/dupes` — show duplicate pairs.
- `/providers` — show OCR provider status.
- `/usage [today|open|all]` — show recorded OCR call/token/cost usage.

Operator notes:

- Financial totals normally count only `status='success' AND is_duplicate=0`.
- Duplicate slips remain visible for audit but are excluded from normal totals.
- `/close` is the normal end-of-period action; it does not delete historical evidence.
- `/clear confirm` is destructive and should not be used for normal daily settlement.

## 6. How to use the dashboard

Default local URL:

```text
http://127.0.0.1:8095/
```

Common public production URL shape:

```text
http://SERVER_IP:8095/
```

Main operator workflow:

1. Open the dashboard.
2. Select company/bot from the company selector.
3. Select flow: `all`, `deposit`, `withdraw`, or `other`.
4. Select scope: `today`, a date, date range, `open`, or `all` depending on the control.
5. Review totals/cards.
6. Open exception/review sections for:
   - duplicate slips
   - bank/source/destination review
   - queue/errors
   - account daily limits
   - cross-company withdrawal-account checks
7. Use export/reconcile/ledger tools only after confirming the selected company/flow/scope.

Important dashboard behavior:

- Background polling uses `detail=lite` to keep the page fast.
- Manual loads/actions fetch full details when needed.
- Admin/mutation actions are protected by role/session/token.
- Pending approval prevents one-click destructive or high-risk mutations.

## 7. Export, reconcile, and bank-ledger workflows

### 7.1 Export preview

Use export preview/dry-run surfaces before generating operator artifacts when possible. Preview should return metadata/counts/sheet names without writing XLSX/ZIP output.

### 7.2 Reconcile preview

Use reconcile preview/dry-run before creating actions. Preview should compare backend Excel and slip data without creating pending actions or mutation rows.

### 7.3 Bank statement ledger preview/import

Safe workflow:

1. Put the bank statement `.xlsx`, `.xlsm`, or `.csv` under `AUDITSLIP_BACKEND_IMPORT_DIR`.
2. Fill dashboard fields:
   - company/bot
   - bank
   - account number
   - account name
   - flow type
   - date/scope
   - statement file/path
3. Run ledger preview first.
4. Confirm the preview shows expected incoming/matched/unmatched rows.
5. Request import only after preview is correct.
6. Approve with a different authorized actor if two-person approval is required.
7. Execute the approved pending action.
8. Verify import idempotency: repeated import should report duplicates, not double-insert rows.

Production smoke rule: never execute a real import just to test production. Use a tiny temporary statement fixture, verify preview/dry-run and missing-file rejection, then delete the fixture.

## 8. Operations commands

### Service status

```bash
systemctl status auditslip-bot.service --no-pager -l
systemctl status auditslip-dashboard.service --no-pager -l
systemctl list-timers 'auditslip*' --no-pager
```

### Logs

```bash
journalctl -u auditslip-bot.service -n 100 --no-pager
journalctl -u auditslip-dashboard.service -n 100 --no-pager
journalctl -u auditslip-bot-watchdog.service -n 100 --no-pager
```

### Restart safely

Dashboard-only change:

```bash
systemctl restart auditslip-dashboard.service
curl -fsS 'http://127.0.0.1:8095/api/health?quick=1'
```

Bot/queue change:

```bash
systemctl status auditslip-bot.service --no-pager -l
sqlite3 /root/projects/auditslip/data/auditslip.db "SELECT status, COUNT(*) FROM ocr_jobs GROUP BY status;"
systemctl restart auditslip-bot.service
journalctl -u auditslip-bot.service -n 80 --no-pager
```

Do not restart the bot blindly during active queue/backlog work unless the change requires it.

### Backups

Run manual backup:

```bash
python3 /root/projects/auditslip/auditslip-backup.py
```

Check backup timer:

```bash
systemctl list-timers auditslip-backup.timer --no-pager
```

### Audit chain verification

```bash
cd /root/projects/auditslip
python3 tools/verify_audit_chain.py --db data/auditslip.db | tail -5
```

Expected result:

```text
RESULT: OK
```

## 9. Development and test workflow

Before editing production code:

```bash
cd /root/projects/auditslip
git fetch origin
git status -sb
git rev-list --left-right --count origin/main...HEAD
```

Run targeted checks for the area you touch. Common full verification:

```bash
python3 -m py_compile auditslip_bot.py auditslip_dashboard.py auditslip_watchdog.py auditslip_bank_ledger.py
python3 - <<'PY'
import pathlib, subprocess, sys, time

tests = sorted(pathlib.Path('tests').glob('check_auditslip*.py'))
failed = []
start = time.time()
for index, test in enumerate(tests, 1):
    result = subprocess.run([sys.executable, str(test)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    status = 'PASS' if result.returncode == 0 else 'FAIL'
    print(f'[{index:03d}/{len(tests):03d}] {status} {test}')
    if result.returncode != 0:
        print(result.stdout)
        failed.append(str(test))
print(f'SUMMARY total={len(tests)} passed={len(tests)-len(failed)} failed={len(failed)} seconds={time.time()-start:.1f}')
if failed:
    raise SystemExit(1)
PY
```

Rendered dashboard JavaScript check:

```bash
python3 - <<'PY'
import importlib.util, os, re, tempfile
from pathlib import Path

root = Path('.')
os.environ.setdefault('BOT_TOKEN', 'TEST_TOKEN')
os.environ.setdefault('AUDITSLIP_DB', str(Path(tempfile.mkdtemp(prefix='auditslip-render-')) / 'auditslip.db'))
os.environ.setdefault('AUDITSLIP_HOME', str(root.resolve()))
os.environ.setdefault('AUDITSLIP_EXPORT_DIR', str(Path(tempfile.mkdtemp(prefix='auditslip-render-export-'))))
os.environ.setdefault('AUDITSLIP_BACKEND_IMPORT_DIR', str(Path(tempfile.mkdtemp(prefix='auditslip-render-import-'))))
os.environ.setdefault('AUDITSLIP_DASHBOARD_TOKEN', 'test-token')

spec = importlib.util.spec_from_file_location('auditslip_dashboard', root / 'auditslip_dashboard.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
html = mod.render_dashboard_html('test-token')
scripts = []
for match in re.finditer(r'<script([^>]*)>(.*?)</script>', html, flags=re.S | re.I):
    attrs = match.group(1) or ''
    body = match.group(2) or ''
    if 'application/json' not in attrs and body.strip():
        scripts.append(body)
Path('/tmp/auditslip-rendered.js').write_text('\n;\n'.join(scripts), encoding='utf-8')
PY
node --check /tmp/auditslip-rendered.js
```

Secret scan before push:

```bash
git diff --cached | grep '^+' | grep -Ei '(api_key|secret|password|token|private_key)\s*[:=]\s*[^[:space:]]{12,}' || true
```

Never stage data/runtime directories:

- `/etc/auditslip/auditslip.env`
- `data/`
- `exports/`
- `imports/`
- `backups/`
- `*.db`, `*.db-wal`, `*.db-shm`
- generated `.xlsx`, `.zip`, `.gz`

## 10. Update/deploy workflow

```bash
cd /root/projects/auditslip
git fetch origin
git status -sb
# edit files
# run targeted + full verification
git add <intended files only>
git commit -m "type(scope): short description"
git push origin main
```

After push:

- Dashboard-only change: restart `auditslip-dashboard.service` and smoke `/api/health?quick=1` + relevant `/api/summary` URL.
- Bot/queue change: check queue state first, restart `auditslip-bot.service`, verify logs and queue resume.
- Data/mutation change: run audit-chain verifier.

## 11. Troubleshooting

### Dashboard `Unauthorized`

- Check owner username/password in `/etc/auditslip/auditslip.env`.
- Prefer owner login/session over token-in-URL links.
- Mutating endpoints require admin/operator/auditor roles depending on action.

### Bot receives nothing from group

- Verify service is active.
- Verify bot token belongs to the intended bot.
- Verify bot is in the Telegram group.
- Check Telegram privacy/permissions; for group slip images, bot may need privacy disabled or admin permissions.
- Check bot offsets/state before calling Telegram APIs that can advance offsets.

### OCR fails or queue grows

```bash
sqlite3 /root/projects/auditslip/data/auditslip.db "SELECT status, COUNT(*) FROM ocr_jobs GROUP BY status;"
journalctl -u auditslip-bot.service -n 120 --no-pager
```

Common causes:

- Missing provider key.
- Provider circuit breaker/cooldown.
- Network/provider errors.
- Invalid/malformed slip image.

Cooldown-only provider errors should be requeued, not counted as permanently bad slips.

### Dashboard slow

Use [`docs/dashboard-performance-runbook.md`](dashboard-performance-runbook.md). Measure live latency, profile Python vs SQL, add regression guards, restart dashboard only, then re-measure.

### Export/reconcile looks empty

- Verify selected company/bot and flow filter.
- Verify date scope uses slip-visible date normalization.
- Prefer preview/dry-run before generating artifacts.
- Open generated workbook/ZIP to inspect sheets and row counts.

### Need rollback

For code rollback:

```bash
cd /root/projects/auditslip
git log --oneline -5
git revert <bad_commit_sha>
git push origin main
systemctl restart auditslip-dashboard.service
```

For DB rollback, use backups under `/root/projects/auditslip/backups/db/`; do not overwrite production DB without taking a fresh backup and stopping affected services first.

## 12. Quick production checklist

After any meaningful change, report evidence, not guesses:

- Git status clean and `main == origin/main`.
- Relevant tests passed.
- Rendered JS check passed for dashboard changes.
- Services active.
- Quick health returns `ok`.
- Queue has no unexpected stuck/failed rows.
- Audit chain verifies `RESULT: OK` for mutation/audit changes.
- No real keys/tokens/data files were staged or pushed.
