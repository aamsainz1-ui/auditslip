# Auditslip

Auditslip is a single Telegram bot for slip auditing.

## Key behavior

- One supervised bot process can run either one Telegram bot token or configured multi-bot/company tokens.
- OCR provider router inside the bot: `OCR_PROVIDERS=gemini,openai`.
- Gemini and OpenAI are fallback providers, not separate services.
- SQLite ledger with WAL.
- Excel export with sheets:
  - `Slips`
  - `SummaryByTransferor`
  - `DailySummary`
  - `Issues`
  - `Settlements`
- Product-safe `/close` for เคลียร์ยอด / closing the current open period without deleting history.
- Destructive `/clear confirm` is separate.

## Commands

- `/summary [open|today|all|DD/MM/YY]`
- `/today`
- `/daily [all]`
- `/names [open|today|all|DD/MM/YY]`
- `/userall`
- `/excel [open|today|all|DD/MM/YY]`
- `/close [note]`
- `/clear` and `/clear confirm`
- `/queue`, `/failed`, `/reprocess [id]`
- `/recent`, `/stats`, `/dupes`, `/providers`

## Runtime paths

- Project: `/root/projects/auditslip`
- Env: `/etc/auditslip/auditslip.env`
- DB: `/root/projects/auditslip/data/auditslip.db`
- Exports: `/root/projects/auditslip/exports`
- Service: `auditslip-bot.service`

## Verification

```bash
cd /root/projects/auditslip
python3 -m py_compile auditslip_bot.py
python3 tests/check_auditslip_product_contract.py
systemctl status auditslip-bot.service --no-pager
```

## Runbooks

- Installation, configuration, and usage: [`docs/install-config-usage.md`](docs/install-config-usage.md)
- Bot creation, group setup, and API connections: [`docs/bot-api-setup.md`](docs/bot-api-setup.md)
- Dashboard performance workflow: [`docs/dashboard-performance-runbook.md`](docs/dashboard-performance-runbook.md)
