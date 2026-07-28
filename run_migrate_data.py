"""1회성 데이터 수술 스크립트.

배경: 2026-04-09 이후 실계좌 NAV(data/portfolio_nav_actual.csv)가 주문
체결 전 잔고 재조회 버그로 오염되어(일간 수익률 ±40~160%), 서킷 브레이커가
가짜 낙폭을 근거로 defensive에 고착되고 전략 조합이 반복 교체돼 왔다.
이 스크립트는 그 손상을 복구한다:

  1. CSV 헤더 승격 — portfolio_nav_actual.csv / strategy_nav.csv가
     4열 헤더에 6열 데이터가 섞여 있던 것을 6열 헤더로 통일
  2. 날짜 정규화 + 중복 제거 — YYYYMMDD/YYYY-MM-DD 혼재 정리
  3. NAV 재구성 — 손상 구간을 holdings.csv(주문 전 스냅샷) × ohlc_history.csv
     종가 + portfolio_state.csv 현금으로 재계산
  4. 잔존 이상치 탐지 — 재구성 후에도 |일간수익률| > 임계값인 행을 보고
  5. circuit_state.json 리셋 — 재구성된 NAV로 rolling drawdown 재산출

기본은 --dry-run이 아니면 실제로 파일을 덮어쓴다. 실행 전 반드시
--dry-run으로 먼저 결과를 확인할 것. data/backup_<오늘날짜>/ 에 원본을
백업한 뒤에만 실제 파일을 수정한다.

실행 (권장 순서):
    python run_migrate_data.py --dry-run
    python run_migrate_data.py
"""
import argparse
import csv
import json
import shutil
import sys
from datetime import date as date_cls
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.analytics.csv_logger import (
    DATA_DIR,
    PORTFOLIO_NAV_ACTUAL_CSV,
    PORTFOLIO_NAV_ACTUAL_HEADER,
    PORTFOLIO_NAV_LEGACY_CSV,
    STRATEGY_NAV_CSV,
    STRATEGY_NAV_HEADER,
    _normalize_date,
    load_holdings,
    load_ohlc_prices,
    load_portfolio_state,
)

CIRCUIT_STATE_FILE = DATA_DIR / "circuit_state.json"
DEFAULT_START_DATE = "2026-04-09"
DEFAULT_OUTLIER_THRESHOLD = 0.10


# ── 1. 헤더 승격 + 날짜 정규화 + 중복 제거 (공용) ─────────────────────────────

def read_raw_csv(path: Path) -> Tuple[List[str], List[List[str]]]:
    if not path.exists() or path.stat().st_size == 0:
        return [], []
    with open(path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def promote_header(rows: List[List[str]], target_header: List[str]) -> List[List[str]]:
    """짧은(구버전) 행을 target_header 길이로 빈 값 패딩한다."""
    n = len(target_header)
    out = []
    for row in rows:
        if len(row) < n:
            row = row + [""] * (n - len(row))
        elif len(row) > n:
            row = row[:n]
        out.append(row)
    return out


def normalize_and_dedupe(
    rows: List[List[str]],
    date_idx: int = 0,
    extra_key_idx: Optional[int] = None,
) -> List[List[str]]:
    """날짜 컬럼을 정규화하고, (날짜[,추가키]) 중복은 마지막 행을 우선해 제거한 뒤
    날짜 오름차순으로 정렬한다.
    """
    deduped: Dict[Tuple, List[str]] = {}
    for row in rows:
        row = list(row)
        row[date_idx] = _normalize_date(row[date_idx])
        key = (row[date_idx], row[extra_key_idx]) if extra_key_idx is not None else (row[date_idx],)
        deduped[key] = row
    return sorted(deduped.values(), key=lambda r: (r[date_idx], r[extra_key_idx] if extra_key_idx is not None else ""))


# ── 2. NAV 재구성 ────────────────────────────────────────────────────────────

def _nearest_price(ohlc_prices: Dict[str, Dict[str, float]], ticker: str, date: str) -> Optional[float]:
    """해당 날짜의 종가가 없으면 그 이전 가장 가까운 종가로 대체한다."""
    series = ohlc_prices.get(ticker, {})
    if date in series:
        return series[date]
    prior_dates = [d for d in series if d < date]
    if not prior_dates:
        return None
    return series[max(prior_dates)]


def compute_holding_value(
    holdings_by_date: Dict[str, List[Dict]],
    ohlc_prices: Dict[str, Dict[str, float]],
    date: str,
) -> Optional[float]:
    rows = holdings_by_date.get(date)
    if not rows:
        return None
    total = 0.0
    for row in rows:
        ticker = row.get("ticker", "")
        try:
            qty = float(row.get("qty", 0) or 0)
        except (ValueError, TypeError):
            qty = 0.0
        price = _nearest_price(ohlc_prices, ticker, date)
        if price is None:
            try:
                price = float(row.get("price", 0) or 0)
            except (ValueError, TypeError):
                price = 0.0
        total += qty * price
    return total


def reconstruct_portfolio_nav_actual(
    nav_rows: List[List[str]],
    start_date: str,
    holdings_by_date: Dict[str, List[Dict]],
    ohlc_prices: Dict[str, Dict[str, float]],
    state_by_date: Dict[str, Dict],
) -> Tuple[List[List[str]], List[List[str]]]:
    """start_date 이후 구간을 holdings×ohlc+state 기반으로 재계산한다.

    Returns:
        (재구성된 전체 행 목록, 재구성에 실패해 원본 그대로 남긴 행 목록)
    """
    if not nav_rows:
        return nav_rows, []

    idx_date, idx_nav, idx_dr, idx_equity, idx_fx, idx_krw = range(6)

    # start_date 직전의 마지막 정상 NAV를 재구성의 출발점으로 삼는다.
    last_good_idx = -1
    for i, row in enumerate(nav_rows):
        if row[idx_date] < start_date:
            last_good_idx = i
        else:
            break

    if last_good_idx == -1:
        # start_date 이전 데이터가 없으면 첫 행을 기준점으로 사용
        prev_nav = float(nav_rows[0][idx_nav]) if nav_rows[0][idx_nav] else 1.0
        cursor = 0
    else:
        prev_nav = float(nav_rows[last_good_idx][idx_nav])
        cursor = last_good_idx + 1

    prev_equity: Optional[float] = None
    if last_good_idx >= 0 and nav_rows[last_good_idx][idx_equity]:
        try:
            prev_equity = float(nav_rows[last_good_idx][idx_equity])
        except ValueError:
            prev_equity = None

    unresolved: List[List[str]] = []
    out_rows = list(nav_rows)

    for i in range(cursor, len(out_rows)):
        row = out_rows[i]
        d = row[idx_date]
        if d < start_date:
            continue

        holding_value = compute_holding_value(holdings_by_date, ohlc_prices, d)
        cash = None
        if d in state_by_date:
            try:
                cash = float(state_by_date[d].get("cash", "") or 0.0)
            except (ValueError, TypeError):
                cash = None

        if holding_value is None or cash is None:
            # 재구성에 필요한 원천 데이터(보유 스냅샷 또는 현금 기록)가 없는 날 —
            # 손대지 않고 원본을 남긴 채 수동 확인 목록에 올린다.
            unresolved.append(row)
            prev_equity = None  # 체인이 끊겼으므로 다음 정상 지점부터 다시 시작
            continue

        new_equity = holding_value + cash
        if prev_equity is not None and prev_equity > 1e-10:
            dr = (new_equity / prev_equity) - 1.0
            new_nav = prev_nav * (1.0 + dr)
        else:
            dr = 0.0
            new_nav = prev_nav

        row[idx_nav] = f"{new_nav:.6f}"
        row[idx_dr] = f"{dr:.6f}"
        row[idx_equity] = f"{new_equity:.2f}"

        prev_nav = new_nav
        prev_equity = new_equity

    return out_rows, unresolved


def find_outliers(nav_rows: List[List[str]], threshold: float = DEFAULT_OUTLIER_THRESHOLD) -> List[List[str]]:
    flagged = []
    for row in nav_rows:
        try:
            dr = float(row[2])
        except (ValueError, IndexError):
            continue
        if abs(dr) > threshold:
            flagged.append(row)
    return flagged


def interpolate_isolated_outliers(nav_rows: List[List[str]], threshold: float = DEFAULT_OUTLIER_THRESHOLD) -> int:
    """앞뒤로 되돌아온(reverted) 단일 행 스파이크만 선형 보간으로 완화한다
    (holdings 데이터가 없어 재구성이 불가능한 2024~2025 백필 구간용 최후 수단).

    판정 기준: row[i-1]→row[i+1]의 2일 누적 변화율이 threshold 이내면, 그
    사이의 row[i]는 일시적 노이즈로 보고 두 앵커의 기하평균으로 대체한다.
    dr[i]와 dr[i+1]을 새 nav[i] 기준으로 다시 체인 계산해 일관성을 유지한다.
    반대로 2일 누적 변화율 자체가 크면(추세 지속) 연속 이상치로 보고 손대지
    않는다 — 신뢰할 수 없는 앵커로 보간하면 새로운 오류를 만들 뿐이다.

    Returns: 보간 처리한 행 개수
    """
    idx_nav, idx_dr, idx_equity = 1, 2, 3
    fixed = 0
    for i in range(1, len(nav_rows) - 1):
        row = nav_rows[i]
        try:
            dr = float(row[idx_dr])
        except (ValueError, IndexError):
            continue
        if abs(dr) <= threshold:
            continue

        prev_row, next_row = nav_rows[i - 1], nav_rows[i + 1]
        try:
            prev_nav = float(prev_row[idx_nav])
            next_nav = float(next_row[idx_nav])
        except (ValueError, IndexError):
            continue
        if prev_nav <= 0 or next_nav <= 0:
            continue

        two_day_return = (next_nav / prev_nav) - 1.0
        if abs(two_day_return) > threshold:
            continue  # 반등이 아니라 지속적 추세로 보임 → 신뢰할 앵커가 없어 skip

        interpolated_nav = (prev_nav * next_nav) ** 0.5  # 기하평균
        row[idx_nav] = f"{interpolated_nav:.6f}"
        row[idx_dr] = f"{(interpolated_nav / prev_nav) - 1.0:.6f}"
        row[idx_equity] = ""  # 보간값이므로 total_equity는 근거가 없어 비워둔다
        next_row[idx_dr] = f"{(next_nav / interpolated_nav) - 1.0:.6f}"
        fixed += 1
    return fixed


# ── 3. circuit_state.json 리셋 ───────────────────────────────────────────────

def reset_circuit_state(nav_rows: List[List[str]], selection_cfg: Dict) -> Dict:
    from app.analytics.risk import rolling_drawdown

    navs = [float(row[1]) for row in nav_rows if row[1]]
    rolling_peak_window = int(selection_cfg.get("rolling_peak_window", 252))
    current_dd = rolling_drawdown(navs, rolling_peak_window) if navs else 0.0

    mdd_limit = selection_cfg.get("portfolio_mdd_limit", -0.18)
    warning_threshold = mdd_limit / 2.0
    defensive_threshold = mdd_limit
    hysteresis = float(selection_cfg.get("circuit_hysteresis", 0.05))
    min_hold_days = int(selection_cfg.get("circuit_min_hold_days", 5))

    if current_dd <= defensive_threshold:
        state = "defensive"
    elif current_dd <= warning_threshold:
        state = "warning"
    else:
        state = "normal"

    today = nav_rows[-1][0] if nav_rows else date_cls.today().isoformat()
    return {
        "state": state,
        "current_dd": round(current_dd, 6),
        "date": today,
        "nav_date": today,
        "entered_date": today,
        "warning_threshold": warning_threshold,
        "defensive_threshold": defensive_threshold,
        "hysteresis": hysteresis,
        "min_hold_days": min_hold_days,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="손상된 실계좌 NAV 데이터 수술")
    parser.add_argument("--dry-run", action="store_true", help="파일을 수정하지 않고 결과만 출력")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="재구성 시작일 (기본: 2026-04-09)")
    parser.add_argument("--outlier-threshold", type=float, default=DEFAULT_OUTLIER_THRESHOLD)
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    config = json.loads((base_dir / "config.json").read_text(encoding="utf-8"))
    selection_cfg = config.get("selection", {})

    print("=" * 60)
    print(f"데이터 수술 {'(dry-run)' if args.dry_run else '(실제 적용)'}")
    print("=" * 60)

    # 1. 원본 로드 + 헤더 승격 + 날짜 정규화
    pf_header, pf_rows = read_raw_csv(PORTFOLIO_NAV_ACTUAL_CSV)
    pf_rows = promote_header(pf_rows, PORTFOLIO_NAV_ACTUAL_HEADER)
    pf_rows = normalize_and_dedupe(pf_rows, date_idx=0)
    print(f"portfolio_nav_actual.csv: {len(pf_rows)}행 (헤더 승격 + 날짜 정규화 완료)")

    sn_header, sn_rows = read_raw_csv(STRATEGY_NAV_CSV)
    sn_rows = promote_header(sn_rows, STRATEGY_NAV_HEADER)
    sn_rows = normalize_and_dedupe(sn_rows, date_idx=0, extra_key_idx=1)
    print(f"strategy_nav.csv: {len(sn_rows)}행 (헤더 승격 + 날짜 정규화 완료)")

    # 2. NAV 재구성
    holdings_rows = load_holdings()
    holdings_by_date: Dict[str, List[Dict]] = {}
    for row in holdings_rows:
        holdings_by_date.setdefault(row["date"], []).append(row)

    ohlc_prices = load_ohlc_prices()

    state_rows = load_portfolio_state()
    state_by_date = {row["date"]: row for row in state_rows}

    reconstructed, unresolved = reconstruct_portfolio_nav_actual(
        pf_rows, args.start_date, holdings_by_date, ohlc_prices, state_by_date,
    )
    print(f"\n재구성 대상 구간: {args.start_date} 이후")
    print(f"  재구성 실패(원본 유지, 수동 확인 필요): {len(unresolved)}행")
    for row in unresolved[:20]:
        print(f"    - {row[0]}: holdings 또는 portfolio_state 기록 없음")
    if len(unresolved) > 20:
        print(f"    ... 외 {len(unresolved) - 20}건")

    # 3. 잔존 이상치 탐지 (재구성 구간 밖 — 2024~2025 백필 포함)
    remaining_outliers = find_outliers(reconstructed, args.outlier_threshold)
    print(f"\n재구성 후 |일간수익률| > {args.outlier_threshold:.0%} 잔존 행: {len(remaining_outliers)}건")
    for row in remaining_outliers[:20]:
        print(f"    - {row[0]}: daily_return={row[2]}")
    if len(remaining_outliers) > 20:
        print(f"    ... 외 {len(remaining_outliers) - 20}건")

    fixed = interpolate_isolated_outliers(reconstructed, args.outlier_threshold)
    print(f"고립 스파이크 보간 처리: {fixed}건")

    final_outliers = find_outliers(reconstructed, args.outlier_threshold)
    print(f"보간 후에도 남은 이상치: {len(final_outliers)}건 (수동 검토 필요)")
    for row in final_outliers[:20]:
        print(f"    - {row[0]}: daily_return={row[2]}")

    # 4. circuit_state.json 리셋
    new_circuit_state = reset_circuit_state(reconstructed, selection_cfg)
    print(f"\ncircuit_state.json 재계산: state={new_circuit_state['state']}, "
          f"current_dd={new_circuit_state['current_dd']:.2%}")

    if args.dry_run:
        print("\n[dry-run] 파일을 수정하지 않았습니다. 결과를 확인한 뒤 --dry-run 없이 재실행하세요.")
        return

    # 5. 백업 후 실제 적용
    backup_dir = DATA_DIR / f"backup_{date_cls.today().isoformat()}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for src in (PORTFOLIO_NAV_ACTUAL_CSV, STRATEGY_NAV_CSV, CIRCUIT_STATE_FILE, PORTFOLIO_NAV_LEGACY_CSV):
        if src.exists():
            shutil.copy2(src, backup_dir / src.name)
    print(f"\n원본 백업: {backup_dir}")

    with open(PORTFOLIO_NAV_ACTUAL_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(PORTFOLIO_NAV_ACTUAL_HEADER)
        writer.writerows(reconstructed)

    with open(STRATEGY_NAV_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(STRATEGY_NAV_HEADER)
        writer.writerows(sn_rows)

    with open(CIRCUIT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(new_circuit_state, f, ensure_ascii=False, indent=2)

    if PORTFOLIO_NAV_LEGACY_CSV.exists():
        PORTFOLIO_NAV_LEGACY_CSV.unlink()
        print("레거시 portfolio_nav.csv 제거")

    print("\n✅ 데이터 수술 완료. python run_rebalance.py --report-only 로 검증하세요.")


if __name__ == "__main__":
    main()
