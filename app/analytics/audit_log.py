"""감사 추적 로그 — 모든 주문·NAV 산출·설정 변경을 불변 append-only로 기록한다.

data/audit_log.csv 에 이벤트를 추가 기록하며, 덮어쓰기 없이 항상 append만 수행한다.
각 행은 (timestamp, event_type, strategy, detail, git_rev, config_hash) 형식이다.
"""
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
AUDIT_LOG_CSV = DATA_DIR / "audit_log.csv"

AUDIT_HEADER = ["timestamp", "event_type", "strategy", "detail", "git_rev", "config_hash"]

# 이벤트 유형
EVENT_NAV_UPDATE = "NAV_UPDATE"
EVENT_ORDER_EXECUTE = "ORDER_EXECUTE"
EVENT_REBALANCE_SKIP = "REBALANCE_SKIP"
EVENT_CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
EVENT_CONFIG_CHANGE = "CONFIG_CHANGE"
EVENT_SIGNAL_COLLECT = "SIGNAL_COLLECT"


def _git_rev() -> str:
    """현재 git HEAD의 짧은 커밋 해시를 반환한다. git 없으면 빈 문자열."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
            cwd=str(DATA_DIR.parent),
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _config_hash() -> str:
    """config.json의 MD5 해시 앞 8자리를 반환한다. 파일 없으면 빈 문자열."""
    config_path = DATA_DIR.parent / "config.json"
    try:
        content = config_path.read_bytes()
        return hashlib.md5(content).hexdigest()[:8]
    except Exception:
        return ""


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_event(
    event_type: str,
    strategy: str,
    detail: str,
    git_rev: Optional[str] = None,
    config_hash: Optional[str] = None,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not AUDIT_LOG_CSV.exists() or AUDIT_LOG_CSV.stat().st_size == 0
    row = [
        _now_utc(),
        event_type,
        strategy,
        detail,
        git_rev if git_rev is not None else _git_rev(),
        config_hash if config_hash is not None else _config_hash(),
    ]
    with open(AUDIT_LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(AUDIT_HEADER)
        writer.writerow(row)


def log_nav_update(
    strategy: str,
    date: str,
    gross_nav: float,
    net_nav: Optional[float] = None,
    daily_return: Optional[float] = None,
) -> None:
    """전략 NAV 업데이트를 기록한다."""
    parts = [f"date={date}", f"gross_nav={gross_nav:.6f}"]
    if net_nav is not None:
        parts.append(f"net_nav={net_nav:.6f}")
    if daily_return is not None:
        parts.append(f"daily_return={daily_return:.6f}")
    _append_event(EVENT_NAV_UPDATE, strategy, " | ".join(parts))


def log_order_execute(
    strategy: str,
    date: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    commission: float = 0.0,
) -> None:
    """주문 실행을 기록한다."""
    detail = (
        f"date={date} | ticker={ticker} | side={side} | "
        f"qty={qty} | price={price:.2f} | commission={commission:.4f}"
    )
    _append_event(EVENT_ORDER_EXECUTE, strategy, detail)


def log_rebalance_skip(strategy: str, date: str, reason: str) -> None:
    """리밸런싱 스킵 사유를 기록한다."""
    _append_event(EVENT_REBALANCE_SKIP, strategy, f"date={date} | reason={reason}")


def log_circuit_breaker(
    date: str,
    state: str,
    current_dd: float,
    threshold: float,
    fallback: str,
) -> None:
    """서킷 브레이커 발동/해제를 기록한다."""
    detail = (
        f"date={date} | state={state} | "
        f"current_dd={current_dd:.4f} | threshold={threshold:.4f} | fallback={fallback}"
    )
    _append_event(EVENT_CIRCUIT_BREAKER, "portfolio", detail)


def log_signal_collect(strategy: str, date: str, mode: str, targets: dict) -> None:
    """신호 수집 결과를 기록한다."""
    targets_str = "|".join(f"{k}:{v:.2f}" for k, v in targets.items())
    detail = f"date={date} | mode={mode} | targets={targets_str}"
    _append_event(EVENT_SIGNAL_COLLECT, strategy, detail)


def log_config_change(changed_keys: list, old_values: dict, new_values: dict) -> None:
    """config.json 변경을 기록한다."""
    changes = []
    for k in changed_keys:
        changes.append(f"{k}: {old_values.get(k)} -> {new_values.get(k)}")
    _append_event(EVENT_CONFIG_CHANGE, "system", " | ".join(changes))
