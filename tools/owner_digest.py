#!/usr/bin/env python3
"""Auditslip Owner Daily Digest -- Phase C1.

Sends a compact Thai Telegram message to the company owner each morning summarising:
  - Slip totals (success + non-duplicate) over the last N hours
  - Deposit vs withdraw split (classified by chat_title tokens, matching the
    dashboard's flow_type_for_title -- spec referenced a `slips.flow_type` column
    which does NOT exist; we mirror dashboard tokens here instead)
  - Top 5 transferors by withdraw amount (account number masked to last 4 digits)
  - dashboard_mutation_log mutation counts by action
  - pending_actions counts by status
  - Audit chain integrity (re-uses tools/verify_audit_chain.compute_mutation_hash)
  - Failed/stuck OCR queue depth (slips with status='error'|'unclear' + ocr_jobs failed)

Read-only sqlite access via URI ?mode=ro.

Exit codes:
    0  digest sent (or dry-run printed) ok
    1  config missing (no bot token / no chat id, and not --dry-run)
    2  DB error
    3  telegram send error
    4  chain integrity failure (digest is still produced/sent, but exit non-zero)
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB = "/root/projects/auditslip/data/auditslip.db"
BKK = dt.timezone(dt.timedelta(hours=7))

# Mirror of auditslip_dashboard.DEPOSIT_TITLE_TOKENS / WITHDRAW_TITLE_TOKENS
# (kept inline so this tool stays standalone -- DO NOT import dashboard.py).
DEPOSIT_TOKENS = ["ฝาก", "deposit", "deposits", "รับฝาก", "เติมเงิน", "เติมมือ", "topup", "top-up"]
WITHDRAW_TOKENS = ["ถอน", "withdraw", "withdrawal", "withdrawals"]


# ---------------------------------------------------------------------------
# audit-chain helper -- reuse the canonical verify_audit_chain.py beside us
# ---------------------------------------------------------------------------

def _load_verify_audit_chain():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("verify_audit_chain", here / "verify_audit_chain.py")
    if not spec or not spec.loader:
        raise RuntimeError("cannot locate verify_audit_chain.py beside owner_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def classify_flow(title: str) -> str:
    """Return 'deposit', 'withdraw' or 'other' from chat title tokens."""
    lower = (title or "").lower()
    for tok in DEPOSIT_TOKENS:
        if tok.lower() in lower:
            return "deposit"
    for tok in WITHDRAW_TOKENS:
        if tok.lower() in lower:
            return "withdraw"
    return "other"


def mask_account(acct: str) -> str:
    s = (acct or "").strip()
    if not s:
        return "xxxx"
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 4:
        return "xxx" + digits[-4:]
    return "xxx" + (digits or "----")


def fmt_amount(value: float) -> str:
    try:
        v = float(value or 0.0)
    except Exception:
        return str(value)
    if abs(v - round(v)) < 0.005:
        return f"{int(round(v)):,}"
    return f"{v:,.2f}"


def open_ro(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# data gathering
# ---------------------------------------------------------------------------

def fetch_slip_aggregates(conn: sqlite3.Connection, since_ts: int) -> Dict[str, Any]:
    """24h aggregates from slips (success + non-duplicate)."""
    cur = conn.execute(
        "SELECT chat_title, transferor_name, from_account, amount "
        "FROM slips "
        "WHERE created_at >= ? AND status = 'success' AND COALESCE(is_duplicate, 0) = 0",
        (since_ts,),
    )
    total_count = 0
    total_amount = 0.0
    deposit_count = 0
    deposit_amount = 0.0
    withdraw_count = 0
    withdraw_amount = 0.0
    withdraw_by_transferor: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in cur:
        amt = float(row["amount"] or 0.0)
        total_count += 1
        total_amount += amt
        flow = classify_flow(row["chat_title"] or "")
        if flow == "deposit":
            deposit_count += 1
            deposit_amount += amt
        elif flow == "withdraw":
            withdraw_count += 1
            withdraw_amount += amt
            name = (row["transferor_name"] or "(ไม่ระบุชื่อ)").strip() or "(ไม่ระบุชื่อ)"
            acct_masked = mask_account(row["from_account"] or "")
            key = (name, acct_masked)
            entry = withdraw_by_transferor.setdefault(key, {"name": name, "account": acct_masked, "amount": 0.0, "count": 0})
            entry["amount"] += amt
            entry["count"] += 1
    top5 = sorted(withdraw_by_transferor.values(), key=lambda x: x["amount"], reverse=True)[:5]
    return {
        "total_count": total_count,
        "total_amount": total_amount,
        "deposit_count": deposit_count,
        "deposit_amount": deposit_amount,
        "withdraw_count": withdraw_count,
        "withdraw_amount": withdraw_amount,
        "top5_transferors": top5,
    }


def fetch_mutation_counts(conn: sqlite3.Connection, since_iso: str) -> Dict[str, int]:
    try:
        cur = conn.execute(
            "SELECT action, COUNT(*) AS n FROM dashboard_mutation_log "
            "WHERE ts_iso >= ? GROUP BY action ORDER BY n DESC",
            (since_iso,),
        )
        return {row["action"]: int(row["n"]) for row in cur}
    except sqlite3.OperationalError:
        return {}


def fetch_pending_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    try:
        cur = conn.execute("SELECT status, COUNT(*) AS n FROM pending_actions GROUP BY status")
        return {row["status"]: int(row["n"]) for row in cur}
    except sqlite3.OperationalError:
        return {}


def fetch_audit_chain_status(conn: sqlite3.Connection, db_path: Path) -> Dict[str, Any]:
    """Verify hash chain. Returns {ok, total_rows, first_bad_id, message}."""
    try:
        vac = _load_verify_audit_chain()
    except Exception as exc:
        return {"ok": None, "total_rows": 0, "first_bad_id": None, "message": f"verifier unavailable: {exc}"}
    try:
        try:
            cur = conn.execute(
                "SELECT id, ts_iso, action, actor, chat_id, bot_key, slip_id, payload_json, "
                "       result_status, result_summary, prev_hash, entry_hash "
                "FROM dashboard_mutation_log ORDER BY id ASC"
            )
        except sqlite3.OperationalError as exc:
            return {"ok": None, "total_rows": 0, "first_bad_id": None, "message": f"not migrated: {exc}"}
        total = 0
        first_bad_id = None
        last_entry_hash = ""
        for row in cur:
            total += 1
            d = dict(row)
            stored_entry = d.get("entry_hash") or ""
            stored_prev = d.get("prev_hash") or ""
            if stored_prev != last_entry_hash and first_bad_id is None:
                first_bad_id = d["id"]
            recomputed = vac.compute_mutation_hash(stored_prev, d)
            if recomputed != stored_entry and first_bad_id is None:
                first_bad_id = d["id"]
            last_entry_hash = stored_entry
        return {
            "ok": first_bad_id is None,
            "total_rows": total,
            "first_bad_id": first_bad_id,
            "message": "",
        }
    except sqlite3.OperationalError as exc:
        return {"ok": None, "total_rows": 0, "first_bad_id": None, "message": f"db error: {exc}"}


def fetch_queue_depth(conn: sqlite3.Connection) -> Dict[str, int]:
    stuck_slips = 0
    failed_slips = 0
    try:
        cur = conn.execute("SELECT status, COUNT(*) AS n FROM slips WHERE status IN ('error','unclear') GROUP BY status")
        for row in cur:
            if row["status"] == "unclear":
                stuck_slips = int(row["n"])
            elif row["status"] == "error":
                failed_slips = int(row["n"])
    except sqlite3.OperationalError:
        pass
    failed_jobs = 0
    try:
        cur = conn.execute("SELECT COUNT(*) AS n FROM ocr_jobs WHERE status IN ('failed','error','dead')")
        row = cur.fetchone()
        failed_jobs = int(row["n"]) if row else 0
    except sqlite3.OperationalError:
        pass
    return {"stuck": stuck_slips, "failed": failed_slips + failed_jobs}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render_digest(data: Dict[str, Any], now_bkk: dt.datetime, hours: int) -> str:
    agg = data["slips"]
    muts = data["mutations"]
    pends = data["pending"]
    chain = data["chain"]
    queue = data["queue"]

    lines: List[str] = []
    title_date = now_bkk.strftime("%d/%m/%Y")
    window = f" ({hours}h)" if hours != 24 else ""
    lines.append(f"🧾 Auditslip Daily Digest — {title_date}{window}")
    lines.append("")
    lines.append(f"💰 ยอด 24h: ฿{fmt_amount(agg['total_amount'])} (สลิป {agg['total_count']} ใบ)")
    lines.append(f"ฝาก: ฿{fmt_amount(agg['deposit_amount'])} | ถอน: ฿{fmt_amount(agg['withdraw_amount'])}")
    lines.append("")
    lines.append("📊 Top 5 ผู้โอน (ถอน)")
    if agg["top5_transferors"]:
        for idx, t in enumerate(agg["top5_transferors"], start=1):
            lines.append(f"{idx}. {t['name']} {t['account']} — ฿{fmt_amount(t['amount'])} ({t['count']} ครั้ง)")
    else:
        lines.append("(ไม่มีรายการถอน)")
    lines.append("")
    lines.append("🔧 Mutations 24h")
    if muts:
        lines.append(" | ".join(f"{k}: {v}" for k, v in muts.items()))
    else:
        lines.append("(ไม่มีการแก้ไข)")
    lines.append("")
    if pends:
        total_pending = sum(pends.values())
        parts = " | ".join(f"{k}: {v}" for k, v in sorted(pends.items()))
        lines.append(f"⏳ Pending approvals: {total_pending} ({parts})")
    else:
        lines.append("⏳ Pending approvals: 0")
    lines.append("")
    if chain["ok"] is True:
        lines.append(f"🔐 Audit chain: ✅ OK ({chain['total_rows']} rows)")
    elif chain["ok"] is False:
        lines.append(f"🔐 Audit chain: ❌ TAMPER at row {chain['first_bad_id']} ({chain['total_rows']} rows)")
    else:
        msg = chain.get("message") or "unknown"
        lines.append(f"🔐 Audit chain: ⚠️ {msg}")
    lines.append("")
    lines.append(f"⚠️ Queue: {queue['stuck']} stuck, {queue['failed']} failed")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# telegram
# ---------------------------------------------------------------------------

def resolve_telegram_target(cli_chat_id: Optional[str]) -> Tuple[str, str]:
    token = (
        os.environ.get("AUDITSLIP_WATCHDOG_BOT_TOKEN")
        or os.environ.get("BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()
    if cli_chat_id:
        chat_id = cli_chat_id.strip()
    else:
        chat_id = (
            os.environ.get("AUDITSLIP_WATCHDOG_ALERT_CHAT_ID")
            or next((x.strip() for x in os.environ.get("AUDITSLIP_ADMIN_IDS", "").split(",") if x.strip()), "")
        ).strip()
    return token, chat_id


def send_telegram(token: str, chat_id: str, text: str) -> Tuple[bool, str]:
    try:
        import requests  # type: ignore
    except ImportError:
        return False, "python-requests not installed"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as exc:
        return False, f"network error: {exc}"
    if resp.status_code != 200:
        return False, f"http {resp.status_code}: {resp.text[:200]}"
    return True, ""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_digest(db_path: Path, hours: int, now_bkk: dt.datetime) -> Tuple[str, Dict[str, Any]]:
    since = now_bkk - dt.timedelta(hours=hours)
    since_ts = int(since.timestamp())
    # mutation_log.ts_iso is stored as UTC ISO ('YYYY-MM-DDTHH:MM:SSZ' or similar);
    # use the UTC iso of `since` for the >= comparison.
    since_iso = since.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    conn = open_ro(db_path)
    try:
        slips = fetch_slip_aggregates(conn, since_ts)
        mutations = fetch_mutation_counts(conn, since_iso)
        pending = fetch_pending_counts(conn)
        chain = fetch_audit_chain_status(conn, db_path)
        queue = fetch_queue_depth(conn)
    finally:
        conn.close()
    data = {"slips": slips, "mutations": mutations, "pending": pending, "chain": chain, "queue": queue}
    text = render_digest(data, now_bkk, hours)
    return text, data


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Auditslip owner daily digest")
    p.add_argument("--dry-run", action="store_true", help="print to stdout, do not send Telegram")
    p.add_argument("--hours", type=int, default=24, help="lookback window in hours (default 24)")
    p.add_argument("--db", default=os.environ.get("AUDITSLIP_DB") or DEFAULT_DB, help="path to auditslip.db")
    p.add_argument("--chat-id", default=None, help="override target Telegram chat id")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"FAIL: db not found: {db_path}", file=sys.stderr)
        return 2

    now_bkk = dt.datetime.now(BKK)
    try:
        text, data = build_digest(db_path, args.hours, now_bkk)
    except sqlite3.OperationalError as exc:
        print(f"FAIL: db error: {exc}", file=sys.stderr)
        return 2

    chain_failed = data["chain"]["ok"] is False

    if args.dry_run:
        print(text)
        return 4 if chain_failed else 0

    token, chat_id = resolve_telegram_target(args.chat_id)
    if not token or not chat_id:
        print("FAIL: telegram token/chat_id missing (set BOT_TOKEN + AUDITSLIP_WATCHDOG_ALERT_CHAT_ID, or use --dry-run)", file=sys.stderr)
        return 1

    ok, err = send_telegram(token, chat_id, text)
    if not ok:
        print(f"FAIL: telegram send: {err}", file=sys.stderr)
        return 3

    print("ok: digest sent")
    return 4 if chain_failed else 0


if __name__ == "__main__":
    sys.exit(main())
