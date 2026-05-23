#!/usr/bin/env python3
"""Standalone audit-chain verifier for Auditslip Phase B.

Designed to run with ONLY read-only access to the sqlite DB -- no auditslip_dashboard imports
-- so an external auditor (e.g. company owner / CEO) can independently re-verify the
dashboard_mutation_log hash-chain.

Usage:
    AUDITSLIP_DB=/path/to/auditslip.db python3 tools/verify_audit_chain.py

Exit code:
    0  all rows verified
    1  one or more rows mismatch (or DB missing/unreadable)

IMPORTANT: the canonical-hash algorithm below MUST stay byte-identical to
auditslip_dashboard.py::compute_mutation_hash (keep both in sync if you ever change it).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "/root/projects/auditslip/data/auditslip.db"

# Mirror of _MUTATION_HASH_EXCLUDE_KEYS in auditslip_dashboard.py
_EXCLUDE_KEYS = ("id", "entry_hash")


def compute_mutation_hash(prev_hash: str, row: dict) -> str:
    canonical_obj = {k: row[k] for k in sorted(row.keys()) if k not in _EXCLUDE_KEYS}
    canonical = json.dumps(canonical_obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(((prev_hash or "") + "|" + canonical).encode("utf-8")).hexdigest()


def main() -> int:
    db_path = Path(os.environ.get("AUDITSLIP_DB") or DEFAULT_DB)
    if not db_path.exists():
        print(f"FAIL: db not found: {db_path}", file=sys.stderr)
        return 1
    # Open read-only via URI to make accidental mutation impossible.
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as exc:
        print(f"FAIL: cannot open db {db_path}: {exc}", file=sys.stderr)
        return 1
    conn.row_factory = sqlite3.Row
    try:
        try:
            cursor = conn.execute(
                "SELECT id, ts_iso, action, actor, chat_id, bot_key, slip_id, payload_json, "
                "       result_status, result_summary, prev_hash, entry_hash "
                "FROM dashboard_mutation_log ORDER BY id ASC"
            )
        except sqlite3.OperationalError as exc:
            print(f"FAIL: dashboard_mutation_log not readable: {exc}", file=sys.stderr)
            return 1

        total = 0
        bad = 0
        last_entry_hash = ""
        for row in cursor:
            total += 1
            d = dict(row)
            stored_entry = d.get("entry_hash") or ""
            stored_prev = d.get("prev_hash") or ""
            row_id = d["id"]
            problems = []
            if stored_prev != last_entry_hash:
                problems.append(
                    f"prev_hash={stored_prev[:12]}... != prior entry_hash={last_entry_hash[:12]}..."
                )
            recomputed = compute_mutation_hash(stored_prev, d)
            if recomputed != stored_entry:
                problems.append(
                    f"entry_hash mismatch: stored={stored_entry[:12]}... recomputed={recomputed[:12]}..."
                )
            if problems:
                bad += 1
                print(f"FAIL row id={row_id} action={d.get('action')}: {'; '.join(problems)}")
            else:
                print(f"PASS row id={row_id} action={d.get('action')} entry_hash={stored_entry[:12]}...")
            last_entry_hash = stored_entry
        print("---")
        print(f"total_rows={total} bad_rows={bad}")
        if bad:
            print("RESULT: FAIL")
            return 1
        print("RESULT: OK")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
