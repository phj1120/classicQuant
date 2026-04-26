"""주문 실패 재시도 큐.

실패 주문을 data/pending_orders.json에 저장하고
다음 실행 시 재시도한다 (최대 MAX_RETRIES회).
"""
import json
from datetime import date as _date
from pathlib import Path
from typing import Dict, List

DATA_DIR = Path("data")
PENDING_ORDERS_FILE = DATA_DIR / "pending_orders.json"
MAX_RETRIES = 3


def load_pending_orders() -> List[Dict]:
    """저장된 미체결(실패) 주문 목록을 로드한다."""
    if not PENDING_ORDERS_FILE.exists():
        return []
    try:
        with open(PENDING_ORDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_pending_orders(orders: List[Dict]) -> None:
    """미체결 주문 목록을 저장한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PENDING_ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)


def enqueue_failed_orders(failed_results: List[Dict], original_orders: List[Dict]) -> None:
    """실행 실패 주문을 큐에 추가한다.

    failed_results: execute_orders() 반환의 results["failed"] 리스트
    original_orders: build_group_orders()의 원본 orders (est_value, exchange_code 등 포함)
    """
    if not failed_results:
        return

    # 원본 주문 딕셔너리를 ticker+side로 인덱싱
    orig_by_key = {(o["ticker"], o["side"]): o for o in original_orders}

    existing = load_pending_orders()
    existing_keys = {(o["ticker"], o["side"]) for o in existing}

    today = str(_date.today())
    for result in failed_results:
        key = (result["ticker"], result["side"])
        if key in existing_keys:
            # 이미 있으면 retry_count만 증가
            for order in existing:
                if order["ticker"] == result["ticker"] and order["side"] == result["side"]:
                    order["retry_count"] = order.get("retry_count", 0) + 1
                    order["last_failed"] = today
                    order["last_message"] = result.get("message", "")
        else:
            orig = orig_by_key.get(key, {})
            existing.append({
                "ticker": result["ticker"],
                "side": result["side"],
                "quantity": result["quantity"],
                "est_value": orig.get("est_value"),
                "exchange_code": orig.get("exchange_code"),
                "retry_count": 1,
                "first_failed": today,
                "last_failed": today,
                "last_message": result.get("message", ""),
            })

    save_pending_orders(existing)


def pop_retryable_orders(max_retries: int = MAX_RETRIES) -> tuple:
    """재시도 가능한 주문과 초과 주문을 분리해서 반환한다.

    Returns:
        (retryable: List[Dict], exhausted: List[Dict])
        - retryable: retry_count < max_retries인 주문 (큐에서 제거됨)
        - exhausted: retry_count >= max_retries인 주문 (큐에서 제거됨)
    """
    orders = load_pending_orders()
    retryable = [o for o in orders if o.get("retry_count", 0) < max_retries]
    exhausted = [o for o in orders if o.get("retry_count", 0) >= max_retries]
    # 재시도 후 제거 (성공/실패 여부는 호출자가 판단해서 다시 enqueue)
    remaining = []  # 재시도 후 실패하면 호출자가 다시 enqueue
    save_pending_orders(remaining)
    return retryable, exhausted


def write_failed_orders_report(exhausted: List[Dict], reports_dir: Path) -> Path:
    """재시도 횟수 초과 주문을 markdown 리포트로 저장한다."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    today = str(_date.today())
    path = reports_dir / f"{today}_failed_orders.md"
    lines = [
        f"# 주문 실패 리포트 ({today})",
        "",
        f"재시도 {MAX_RETRIES}회 초과로 포기된 주문 목록입니다.",
        "",
        "| 종목 | 방향 | 수량 | 추정 금액 | 최초 실패 | 마지막 실패 | 메시지 |",
        "|------|------|------|-----------|-----------|-------------|--------|",
    ]
    for o in exhausted:
        est = f"${o['est_value']:.2f}" if o.get("est_value") else "-"
        lines.append(
            f"| {o['ticker']} | {o['side']} | {o['quantity']} | {est} "
            f"| {o.get('first_failed','-')} | {o.get('last_failed','-')} "
            f"| {o.get('last_message','')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
