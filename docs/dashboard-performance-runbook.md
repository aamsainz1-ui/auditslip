# Auditslip Dashboard Performance Runbook

Use this when continuing Phase C dashboard performance work, especially for slow `/api/summary` calls on production-sized SQLite data.

## Scope

This runbook covers dashboard-only performance changes in `auditslip_dashboard.py`.

- Safe to restart: `auditslip-dashboard.service`
- Do **not** restart the Telegram bot unless the change touches bot ingestion/queue code.
- Do **not** commit runtime data, `.env`, DB files, exports, backups, or generated slip images.

## 1. Baseline before editing

From the production repo:

```bash
cd /root/projects/auditslip
git status -sb
git rev-list --left-right --count origin/main...HEAD
systemctl is-active auditslip-dashboard.service auditslip-bot.service
```

Measure live HTTP latency/bytes before changing code:

```bash
python3 - <<'PY'
import json, statistics, time, urllib.request

variants = [
    ("today-lite", "http://127.0.0.1:8095/api/summary?scope=today&detail=lite"),
    ("today-full", "http://127.0.0.1:8095/api/summary?scope=today&detail=full"),
    ("open-lite", "http://127.0.0.1:8095/api/summary?scope=open&detail=lite"),
    ("open-full", "http://127.0.0.1:8095/api/summary?scope=open&detail=full"),
]

for name, url in variants:
    times = []
    sizes = []
    for _ in range(5 if "full" not in name else 3):
        start = time.perf_counter()
        with urllib.request.urlopen(url, timeout=40) as response:
            body = response.read()
            status = response.status
        times.append((time.perf_counter() - start) * 1000)
        sizes.append(len(body))
    print(json.dumps({
        "name": name,
        "status": status,
        "p50_ms": round(statistics.median(times), 1),
        "max_ms": round(max(times), 1),
        "bytes_median": int(statistics.median(sizes)),
    }, ensure_ascii=False))
PY
```

## 2. Profile Python vs SQL before choosing a fix

Profile `dashboard_snapshot()` against the live DB/env:

```bash
python3 - <<'PY'
import cProfile, io, os, pstats, time
from pathlib import Path

pid = int(os.popen('systemctl show -p MainPID --value auditslip-dashboard.service').read().strip() or '0')
if pid:
    for part in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
        if b'=' in part:
            key, value = part.split(b'=', 1)
            os.environ[key.decode()] = value.decode(errors='replace')

import auditslip_dashboard as dashboard

for fn in [getattr(dashboard, 'display_bank', None), getattr(dashboard, 'date_bucket', None)]:
    if hasattr(fn, 'cache_clear'):
        fn.cache_clear()

profile = cProfile.Profile()
start = time.perf_counter()
profile.enable()
snapshot = dashboard.dashboard_snapshot(dashboard.DB_PATH, scope='open', detail_level='lite')
profile.disable()

stream = io.StringIO()
pstats.Stats(profile, stream=stream).sort_stats('cumtime').print_stats(30)
print('elapsed', round(time.perf_counter() - start, 3), 'selected', snapshot.get('totals', {}).get('selected_success_count'))
print(stream.getvalue())
PY
```

Count SQL statements separately:

```bash
python3 - <<'PY'
import os, sqlite3, time
from pathlib import Path

pid = int(os.popen('systemctl show -p MainPID --value auditslip-dashboard.service').read().strip() or '0')
if pid:
    for part in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
        if b'=' in part:
            key, value = part.split(b'=', 1)
            os.environ[key.decode()] = value.decode(errors='replace')

import auditslip_dashboard as dashboard

original_connect = dashboard.connect
counts = {"total": 0, "select": 0, "by_sql": {}}

def traced_connect(db_path):
    conn = original_connect(db_path)
    def trace(sql):
        text = ' '.join(str(sql).split())
        counts['total'] += 1
        if text.upper().startswith('SELECT'):
            counts['select'] += 1
            key = text[:160]
            counts['by_sql'][key] = counts['by_sql'].get(key, 0) + 1
    conn.set_trace_callback(trace)
    return conn

dashboard.connect = traced_connect
start = time.perf_counter()
dashboard.dashboard_snapshot(dashboard.DB_PATH, scope='open', detail_level='lite')
print('elapsed', round(time.perf_counter() - start, 3), 'trace_total', counts['total'], 'selects', counts['select'])
for sql, count in sorted(counts['by_sql'].items(), key=lambda item: item[1], reverse=True)[:25]:
    print(count, sql)
PY
```

## 3. Fix patterns already used

### Pure helper hot paths

If CPU is dominated by repeated normalization helpers:

- Wrap internal sanitized-string helpers with `functools.lru_cache`.
- Keep public helpers accepting `Any`, but call cached helpers with `clean_display(...)` values.
- Expose `cache_clear` on the public helper for regression tests.
- Do not rebuild static bank alias sets inside the hot path.

Regression guard: `tests/check_auditslip_dashboard_hotpath_caches.py`

### `detail=lite` payloads

Lite auto-refresh must not compute detail rows and then strip them. It should skip expensive helpers before they run.

Keep these in lite:

- totals
- company menu / selected company summary
- exception counts
- bot/chat navigation

Skip these in lite:

- recent slip cards
- duplicate pair rows
- source-bank review rows
- account slip search rows
- cross-company detail rows
- date/bank/sender aggregate detail tables
- provider usage detail rows
- recent OCR job rows

Regression guard: `tests/check_auditslip_dashboard_lite_summary_payload.py`

The guard monkeypatches detail-only helpers to raise. `dashboard_snapshot(..., detail_level="lite")` must still succeed.

### Duplicate review full snapshots

If `open-full` is dominated by duplicate review rows/submitted-time lookups, ensure these durable indexes exist:

- `idx_slips_duplicate_created`
  - partial index for successful duplicate slips ordered by `created_at DESC`
- `idx_ocr_jobs_slip_bot_created`
  - index for `MIN(ocr_jobs.created_at)` submitted-time subqueries by `slip_id` + `bot_key`

Regression guard: `tests/check_auditslip_dashboard_performance_indexes.py`

## 4. Verification before commit

For dashboard performance changes, run at least:

```bash
python3 -m py_compile auditslip_dashboard.py
python3 tests/check_auditslip_dashboard_lite_summary_payload.py
python3 tests/check_auditslip_dashboard_hotpath_caches.py
python3 tests/check_auditslip_dashboard_performance_indexes.py
```

If duplicate/review UI changed, also run:

```bash
python3 tests/check_auditslip_dashboard_duplicate_pairs_source_bank_review.py
```

Run the full local guard suite before pushing:

```bash
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

Check rendered dashboard JavaScript, because dashboard JS is embedded in a Python template:

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

Verify the audit chain is still intact:

```bash
python3 tools/verify_audit_chain.py --db data/auditslip.db | tail -5
```

## 5. Commit, push, and deploy

Stage only intended source/test/doc files:

```bash
git status --short
git diff --stat
git add auditslip_dashboard.py tests/check_auditslip_dashboard_lite_summary_payload.py tests/check_auditslip_dashboard_performance_indexes.py
git commit -m "perf(dashboard): <short description>"
git push origin main
```

For doc-only changes, stage only docs and use `docs(dashboard): ...`.

Restart only the dashboard:

```bash
systemctl restart auditslip-dashboard.service
for i in $(seq 1 20); do
  if curl -fsS --max-time 3 'http://127.0.0.1:8095/api/health?quick=1' >/tmp/auditslip-health.json; then
    python3 -m json.tool /tmp/auditslip-health.json | sed -n '1,40p'
    break
  fi
  sleep 1
done
```

Re-measure live latency/bytes after restart using the baseline script in section 1.

Also verify:

```bash
git status -sb
git rev-list --left-right --count origin/main...HEAD
systemctl is-active auditslip-dashboard.service auditslip-bot.service
journalctl -u auditslip-dashboard.service --since '5 minutes ago' --no-pager -p warning..alert | tail -40
```

## 6. Expected success shape

Report concise evidence:

- commit hash pushed to `origin/main`
- full tests passed count
- rendered JS passed
- audit-chain result
- service health
- before/after p50 for affected endpoints
- any remaining bottleneck if profiling still shows one

Do not claim a performance fix is done from code review alone; use real live measurements.
