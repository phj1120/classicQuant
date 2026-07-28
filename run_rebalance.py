import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# PYTHONPATH 없이도 app 모듈을 찾을 수 있도록 설정
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import (
    build_kis_config,
    build_nav_config,
    build_strategy_config,
    load_config,
    load_key,
    load_selection_config,
    load_strategy_entries,
)
from app.assets.assets import merge_assets, reload_assets
from app.analytics.csv_logger import (
    load_cash_flows,
    load_ohlc_prices,
    load_portfolio_nav_actual,
    load_portfolio_state,
    save_holdings,
    save_momentum,
    save_ohlc_history,
    save_portfolio,
    save_portfolio_nav_actual,
    save_portfolio_state,
    save_strategy_signal,
)
from app.execution.exchange import set_exchange_default
from app.execution.order_queue import (
    enqueue_failed_orders,
    pop_retryable_orders,
    write_failed_orders_report,
)
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from app.constants import (
    DEFAULT_CASH_BUFFER_PCT,
    DEFAULT_MIN_TRADE_VALUE_USD,
    DEFAULT_REBALANCE_THRESHOLD_PCT,
    KIS_EXCHANGE_CODE,
    US_MARKET_TZ,
)
from app.data.kis_api import KoreaInvestmentAPI
from app.execution.market import is_us_market_holiday
from app.data.data_utils import parse_history
from app.indicators.momentum import get_momentum_scores
from app.assets.assets import group_tickers
from app.execution.portfolio import build_group_orders, execute_orders, get_holdings_all_exchanges, get_prices
from app.analytics.report import write_report
from app.analytics.audit_log import (
    log_circuit_breaker,
    log_nav_rejected,
    log_order_execute,
    log_rebalance_skip,
    log_strategy_error,
)
from app.data.fred_api import get_usdkrw_rate
from app.strategy_selector import select_active_strategies
from app.strategies import get_strategy
from app.time_utils import trading_date_label


class CachedMarketDataAPI:
    """report-only 무키 환경에서 로컬 OHLC 캐시를 읽는 최소 API 어댑터."""

    def __init__(self, price_history):
        self.price_history = price_history
        self.exchange_code = KIS_EXCHANGE_CODE

    def get_historical_data(
        self,
        ticker: str,
        period: str = "D",
        min_records: int = 260,
        max_pages: int = 5,
    ):
        del period, min_records, max_pages
        series = self.price_history.get(ticker, {})
        if not series:
            return None
        return [
            {"xymd": date.replace("-", ""), "clos": price}
            for date, price in sorted(series.items())
        ]

    def get_current_price(self, ticker: str, silent: bool = False):
        del silent
        series = self.price_history.get(ticker, {})
        if not series:
            return None
        latest_date = max(series)
        return float(series[latest_date])


def _build_cached_report_api() -> CachedMarketDataAPI:
    price_history = load_ohlc_prices()
    if not price_history:
        raise RuntimeError(
            "report-only 무키 모드를 실행하려면 data/ohlc_history.csv가 필요합니다. "
            "먼저 run_backfill.py 또는 run_collect.py로 가격 데이터를 적재하세요."
        )
    print("ℹ️  API 키 없음: ohlc_history.csv 기반 offline report-only 모드로 실행합니다.")
    return CachedMarketDataAPI(price_history)


def _run_strategy(strategy_entry, api, prices, today):
    """단일 전략을 실행하여 (weighted_targets, scores, targets, strategy_instance)를 반환한다."""
    name = strategy_entry["name"]
    weight = strategy_entry["weight"]

    strategy = get_strategy(name)

    # 전략별 assets 로드
    reload_assets(strategy.assets)

    print(f"\n{'='*50}")
    print(f"📊 전략: {name} (비중: {weight * 100:.0f}%)")
    print(f"{'='*50}")

    universe = strategy.get_universe()
    _, all_returns, all_histories = get_momentum_scores(api, universe)
    scores = {group: strategy.score_from_returns(rets) for group, rets in all_returns.items()}
    parsed_histories = {t: parse_history(h) for t, h in all_histories.items()}
    targets = strategy.select_targets(scores, histories=parsed_histories)

    # CSV 로깅: 모멘텀 스코어 & OHLC 히스토리
    save_momentum(today, name, scores, all_returns)
    for ticker, history in all_histories.items():
        save_ohlc_history(ticker, history)

    print("\n✅ 목표 포트폴리오")
    for ticker, w in targets.items():
        score = scores.get(ticker)
        score_display = f"{score:.4f}" if score is not None else "N/A"
        print(f"- {ticker}: {w * 100:.1f}% (score {score_display})")

    # 전략 신호 기록
    mode = "offensive" if strategy.is_offensive(scores) else "defensive"
    top_score = max((s for s in scores.values() if s is not None), default=None)
    save_strategy_signal(today, name, mode, targets, top_score)

    # 전략 비중을 반영한 타겟
    weighted_targets = {group: w * weight for group, w in targets.items()}

    # 후보 티커 가격 조회
    candidate_tickers = []
    for group in targets.keys():
        candidate_tickers.extend(group_tickers(group))
    new_prices = get_prices(api, [t for t in set(candidate_tickers) if t not in prices])
    prices.update(new_prices)

    return weighted_targets, scores, targets, strategy


def _check_portfolio_mdd(selection_cfg: dict, today: str = "") -> tuple:
    """portfolio_nav_actual.csv 기반 포트폴리오 MDD 체크 (3-state 머신).

    Returns:
        (triggered: bool, current_dd: float, circuit_state: str)
        triggered=True이면 defensive 모드로 전환해야 한다.
    """
    from app.analytics.circuit_breaker import (
        STATE_DEFENSIVE, STATE_NORMAL, STATE_WARNING,
        update_circuit_state,
    )
    from app.analytics.risk import rolling_drawdown

    mdd_limit = selection_cfg.get("portfolio_mdd_limit")
    if mdd_limit is None:
        return False, 0.0, STATE_NORMAL

    history = load_portfolio_nav_actual()
    if not history:
        return False, 0.0, STATE_NORMAL

    navs = []
    for row in history:
        try:
            navs.append(float(row["nav"]))
        except (ValueError, TypeError):
            continue

    if not navs:
        return False, 0.0, STATE_NORMAL

    # rolling_peak_window 이내 최고점 대비 낙폭을 쓴다. 전체 기간 ATH를 쓰면
    # 오래전 스파이크(혹은 데이터 오염으로 생긴 일시적 고점)가 계속 peak로
    # 남아 실제로는 회복된 상태인데도 낙폭이 과대평가된다.
    rolling_peak_window = int(selection_cfg.get("rolling_peak_window", 252))
    current_dd = rolling_drawdown(navs, rolling_peak_window)

    # 3-state 서킷 브레이커: warning = mdd_limit/2, defensive = mdd_limit
    warning_threshold = mdd_limit / 2.0
    defensive_threshold = mdd_limit
    hysteresis = float(selection_cfg.get("circuit_hysteresis", 0.05))
    min_hold_days = int(selection_cfg.get("circuit_min_hold_days", 5))
    circuit_state = update_circuit_state(
        current_dd=current_dd,
        date=today,
        warning_threshold=warning_threshold,
        defensive_threshold=defensive_threshold,
        hysteresis=hysteresis,
        min_hold_days=min_hold_days,
        history=history,
    )
    triggered = circuit_state == STATE_DEFENSIVE
    return triggered, current_dd, circuit_state


def _update_portfolio_nav_actual(
    today: str,
    total_equity: float,
    cash: float,
    nav_cfg: Optional[dict] = None,
) -> bool:
    """실제 총자산 기준으로 portfolio_nav_actual.csv를 업데이트한다.

    과거 파일에 total_equity 컬럼이 없는 경우, 첫 actual snapshot은 기존 NAV를
    handoff 기준으로 이어받고 daily_return은 0으로 둔다.

    입출금(cash_flows.csv)만큼 total_equity에서 제외해 수익률을 계산하고,
    보정 후에도 |수익률|이 sanity_max_daily_return을 넘으면 기록을 거부한다
    (오염된 잔고 조회값이 그대로 NAV·서킷 브레이커 판단에 흘러들지 않도록 하는 게이트).

    Returns:
        NAV를 기록했으면 True, sanity gate에 걸려 거부했으면 False.
    """
    nav_cfg = nav_cfg or {}
    sanity_max = float(nav_cfg.get("sanity_max_daily_return", 0.10))

    history = load_portfolio_nav_actual()
    state_history = load_portfolio_state()
    if history:
        try:
            last_nav = float(history[-1]["nav"])
        except (ValueError, TypeError):
            last_nav = 1.0
    else:
        last_nav = 1.0

    prev_total_equity = None
    if state_history:
        prev_snapshot = None
        for row in state_history:
            if row.get("date", "") < today:
                prev_snapshot = row
            elif row.get("date", "") == today:
                break
        if prev_snapshot is None and len(state_history) > 1:
            prev_snapshot = state_history[-2]
        elif prev_snapshot is None and state_history and state_history[0].get("date", "") < today:
            prev_snapshot = state_history[0]

        if prev_snapshot is not None:
            try:
                prev_total_equity = float(prev_snapshot.get("total_equity", ""))
            except (ValueError, TypeError):
                prev_total_equity = None

    cash_flow_today = load_cash_flows().get(today, 0.0)
    adjusted_equity = total_equity - cash_flow_today

    if prev_total_equity and prev_total_equity > 1e-10:
        portfolio_dr = (adjusted_equity / prev_total_equity) - 1.0
        new_nav = last_nav * (1.0 + portfolio_dr)
    else:
        portfolio_dr = 0.0
        new_nav = last_nav

    if abs(portfolio_dr) > sanity_max:
        print(
            f"⛔ NAV sanity gate: 일간 수익률 {portfolio_dr:.2%}이 허용치 "
            f"±{sanity_max:.0%}를 초과해 NAV 기록을 거부합니다. "
            f"(total_equity=${total_equity:.2f}, prev=${prev_total_equity or 0:.2f}, "
            f"cash_flow=${cash_flow_today:.2f})"
        )
        log_nav_rejected(today, portfolio_dr, sanity_max, total_equity, prev_total_equity or 0.0)
        return False

    fx_rate = get_usdkrw_rate(today)
    krw_nav = new_nav * fx_rate if fx_rate is not None else None
    save_portfolio_nav_actual(today, new_nav, portfolio_dr, total_equity, fx_rate=fx_rate, krw_nav=krw_nav)
    save_portfolio_state(today, total_equity, cash)
    return True


_LAST_RUN_MARKER_PATH = Path(__file__).resolve().parent / "data" / "last_run_marker.json"


def _has_orders_submitted_marker(today: str) -> bool:
    if not _LAST_RUN_MARKER_PATH.exists():
        return False
    try:
        marker = json.loads(_LAST_RUN_MARKER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return marker.get("date") == today and marker.get("phase") == "orders_submitted"


def _save_orders_submitted_marker(today: str) -> None:
    _LAST_RUN_MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_MARKER_PATH.write_text(
        json.dumps({"date": today, "phase": "orders_submitted"}, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="퀀트 자동 리밸런싱")
    parser.add_argument("--report-only", action="store_true", help="리포트만 생성 (매매 실행 안 함)")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"
    key_path = base_dir / "key.json"

    raw = load_config(config_path)
    strategy_cfg = build_strategy_config(raw)
    strategy_entries = load_strategy_entries(raw)
    selection_cfg = load_selection_config(raw)
    offline_report_only = False

    try:
        key = load_key(key_path if key_path.exists() else None)
    except RuntimeError as exc:
        if not args.report_only:
            raise
        print(f"ℹ️  {exc}")
        offline_report_only = True
        api = _build_cached_report_api()
    else:
        kis_config = build_kis_config(key)
        # 토큰 캐싱은 key 파일에 저장 (로컬 실행 시)
        api = KoreaInvestmentAPI(kis_config, config_file=str(key_path) if key_path.exists() else None)

    if not args.report_only:
        if ZoneInfo is not None:
            now_et = datetime.now(ZoneInfo(US_MARKET_TZ))
            holiday = is_us_market_holiday(api, now_et)
            if holiday is True:
                print("⏸️  미국장 휴장: 실행 스킵")
                return

    # 오늘 날짜
    today = trading_date_label()

    # 공통 데이터 조회
    if offline_report_only:
        holdings_detail = {}
        cash = 0.0
    else:
        holdings_detail = get_holdings_all_exchanges(api)
        cash = api.get_account_cash() or 0.0
    balance_prices = {t: info.get("price") for t, info in holdings_detail.items() if info.get("price")}
    prices = dict(balance_prices)

    holding_value = sum((prices.get(t, 0.0) or 0.0) * info["qty"] for t, info in holdings_detail.items())
    total_equity = cash + holding_value

    print(f"\n💵 현금: ${cash:.2f}")
    print(f"📈 보유 평가액: ${holding_value:.2f}")
    print(f"🧮 총 자산(추정): ${total_equity:.2f}")

    # 포트폴리오 NAV 업데이트 — 주문 실행 "전" 스냅샷을 기준으로 기록한다.
    # 주문 직후에는 체결 전이라 현금·잔고가 일시적으로 어긋나 NAV가 오염되므로,
    # 매일 같은 측정점(주문 영향 없음)을 쓰는 편이 더 일관적이고 안전하다.
    if offline_report_only:
        print("ℹ️  offline report-only 모드에서는 actual NAV/portfolio snapshot을 갱신하지 않습니다.")
    else:
        nav_cfg = build_nav_config(raw)
        _update_portfolio_nav_actual(today, total_equity, cash, nav_cfg=nav_cfg)

    # 포트폴리오 MDD 서킷 브레이커 체크 (3-state) — 방금 기록한 오늘 NAV를 포함해 판정한다.
    circuit_triggered, portfolio_dd, circuit_state = _check_portfolio_mdd(selection_cfg, today)
    mdd_limit = selection_cfg.get("portfolio_mdd_limit")
    if mdd_limit is not None:
        state_icons = {"normal": "✅ 정상", "warning": "⚠️ 경고", "defensive": "⛔ 방어 모드"}
        status = state_icons.get(circuit_state, circuit_state)
        print(f"📉 포트폴리오 낙폭: {portfolio_dd:.1%} (한도: {mdd_limit:.1%}) {status}")

    # CSV 로깅: 보유 현황 (assets 캐시 초기화 후 호출)
    all_strategy_assets = [get_strategy(e["name"]).assets for e in strategy_entries]
    merge_assets(all_strategy_assets)
    from app.assets.assets import group_for_ticker
    if holdings_detail:
        save_holdings(today, holdings_detail, prices, group_for_ticker)

    # Phase 1: 전략별 신호 수집 (전체 전략)
    all_results: dict = {}   # name → (weighted_targets, scores, targets, strategy)
    asset_files = []

    for entry in strategy_entries:
        try:
            weighted_targets, scores, targets, strategy = _run_strategy(
                entry, api, prices, today,
            )
            all_results[entry["name"]] = (weighted_targets, scores, targets, strategy)
            asset_files.append(strategy.assets)
        except Exception as e:
            print(f"❌ {entry['name']} 전략 실패: {e}")
            log_strategy_error(entry["name"], today, str(e))

    failed_count = len(strategy_entries) - len(all_results)
    if strategy_entries and failed_count > len(strategy_entries) / 2:
        raise RuntimeError(
            f"⛔ 전략 {failed_count}/{len(strategy_entries)}개가 실패했습니다. "
            f"선택·리밸런싱을 절반 미만 데이터로 진행하는 대신 중단합니다."
        )

    # Phase 2: 전략 선택 (selection 기준 적용)
    print(f"\n{'='*50}")
    print(f"🎯 전략 선택 (criteria: {selection_cfg.get('criteria')})")
    print(f"{'='*50}")

    strategies_map = {
        name: res[3]
        for name, res in all_results.items()
    }
    scores_by_strategy = {
        name: res[1]
        for name, res in all_results.items()
    }

    active_entries = select_active_strategies(
        strategy_entries=[e for e in strategy_entries if e["name"] in all_results],
        strategies=strategies_map,
        scores_by_strategy=scores_by_strategy,
        selection_cfg=selection_cfg,
    )

    # 서킷 브레이커: 포트폴리오 MDD 한도 초과 시 fallback 강제 적용
    if circuit_triggered:
        fallback_name = selection_cfg.get("fallback_strategy", "permanent")
        if fallback_name not in all_results:
            raise RuntimeError(
                f"⛔ 서킷 브레이커 발동 중 fallback 전략 '{fallback_name}'이 실행되지 않았습니다. "
                f"config의 fallback_strategy가 strategies 목록에 포함되어 있는지 확인하세요."
            )
        print(f"\n⛔ 포트폴리오 MDD 서킷 브레이커 → {fallback_name} 단독 운용")
        mdd_limit = selection_cfg.get("portfolio_mdd_limit", -0.18)
        log_circuit_breaker(today, circuit_state, portfolio_dd, mdd_limit, fallback_name)
        active_entries = [{"name": fallback_name, "weight": 1.0}]

    # Phase 3: active 전략만 포트폴리오 합산
    merged_targets: dict = {}
    all_report_data = []

    for entry in active_entries:
        name = entry["name"]
        weight = entry["weight"]
        if name not in all_results:
            continue

        _, scores, targets, _ = all_results[name]

        for group, w in targets.items():
            merged_targets[group] = merged_targets.get(group, 0.0) + w * weight

        all_report_data.append({
            "name": name,
            "weight": weight,
            "scores": scores,
            "targets": targets,
            "selected_tickers": {},
        })

    if not all_report_data:
        print("⚠️  active 전략이 없습니다. 실행을 중단합니다.")
        return

    # Phase 4: 전체 전략의 assets를 병합 로드
    merge_assets(asset_files)

    # Phase 5: 통합 주문 생성
    print(f"\n{'='*50}")
    print("📊 통합 목표 포트폴리오")
    print(f"{'='*50}")
    for group, w in sorted(merged_targets.items(), key=lambda x: -x[1]):
        print(f"- {group}: {w * 100:.1f}%")

    all_orders, selected_tickers = build_group_orders(
        holdings_detail=holdings_detail,
        targets=merged_targets,
        prices=prices,
        total_equity=total_equity,
        cash_buffer_pct=float(strategy_cfg.get("cash_buffer_pct", DEFAULT_CASH_BUFFER_PCT)),
        min_trade_value_usd=float(strategy_cfg.get("min_trade_value_usd", DEFAULT_MIN_TRADE_VALUE_USD)),
        rebalance_threshold_pct=float(strategy_cfg.get("rebalance_threshold_pct", DEFAULT_REBALANCE_THRESHOLD_PCT)),
    )

    if selected_tickers:
        print("\n✅ 선택된 매수 종목")
        for group, ticker in selected_tickers.items():
            print(f"- {group} → {ticker}")

    # 리포트에 선택 종목 반영
    for data in all_report_data:
        for group in data["targets"]:
            if group in selected_tickers:
                data["selected_tickers"][group] = selected_tickers[group]

    # CSV 로깅: 포트폴리오 스냅샷
    if not offline_report_only:
        save_portfolio(today, total_equity, cash, all_report_data, merged_targets, selected_tickers)

    # 리포트 생성
    report_path = write_report(all_report_data, Path(__file__).resolve().parent / "reports")
    print(f"\n📝 리포트 저장: {report_path}")

    # 주문 실행
    if args.report_only:
        print("\n📋 리포트 전용 모드: 매매 실행 생략")
        log_rebalance_skip("portfolio", today, "report_only mode")
        execution_summary = {"sells": [], "buys": [], "failed": [], "succeeded": []}
    elif _has_orders_submitted_marker(today):
        # GitHub Actions가 실패 후 같은 날 최대 5회 재시도한다. 이전 시도에서 이미
        # 주문을 전송했다면, 재시도로 같은 주문을 또 전송해 중복 매매가 나지 않도록
        # 여기서 멈춘다. NAV/서킷 브레이커는 이미 주문 전 스냅샷으로 기록됐으므로 안전하다.
        print("\n⏭️  오늘 이미 주문을 전송한 기록이 있어 매매를 스킵합니다 (재시도 안전장치).")
        log_rebalance_skip("portfolio", today, "orders already submitted earlier today")
        execution_summary = {"sells": [], "buys": [], "failed": [], "succeeded": []}
    else:
        # 이전 실패 주문 재시도
        retryable, exhausted = pop_retryable_orders()
        if retryable:
            print(f"\n🔄 이전 실패 주문 재시도: {len(retryable)}건")
            retry_orders = [
                {"ticker": o["ticker"], "side": o["side"], "quantity": o["quantity"],
                 "est_value": o.get("est_value", 0), "exchange_code": o.get("exchange_code")}
                for o in retryable
            ]
            retry_summary = execute_orders(api, retry_orders, holdings_detail)
            if retry_summary["failed"]:
                enqueue_failed_orders(retry_summary["failed"], retry_orders)
        if exhausted:
            report_path_failed = write_failed_orders_report(
                exhausted, Path(__file__).resolve().parent / "reports"
            )
            print(f"⚠️  재시도 초과 주문 리포트: {report_path_failed}")

        _save_orders_submitted_marker(today)
        execution_summary = execute_orders(api, all_orders, holdings_detail)
        for order in execution_summary.get("succeeded", []):
            log_order_execute(
                strategy="portfolio",
                date=today,
                ticker=order.get("ticker", ""),
                side=order.get("side", ""),
                qty=float(order.get("quantity", 0)),
                price=float(order.get("price", 0)),
            )
        if execution_summary["failed"]:
            enqueue_failed_orders(execution_summary["failed"], all_orders)

        # 참고용 사후 스냅샷 — 체결 확인 없이 즉시 조회하므로 미체결 상태가 섞여
        # 있을 수 있다. NAV/portfolio_state 기록에는 쓰지 않고 출력에만 사용한다.
        refreshed_holdings = get_holdings_all_exchanges(api)
        refreshed_cash = api.get_account_cash() or 0.0
        refreshed_prices = {t: info.get("price") for t, info in refreshed_holdings.items() if info.get("price")}
        refreshed_holding_value = sum(
            (refreshed_prices.get(t, 0.0) or 0.0) * info["qty"]
            for t, info in refreshed_holdings.items()
        )
        refreshed_total_equity = refreshed_cash + refreshed_holding_value

        print("\n📌 주문 후 계정 스냅샷 (참고용 — 미체결 반영 전일 수 있음)")
        print(f"  현금: ${refreshed_cash:.2f}")
        print(f"  보유 평가액: ${refreshed_holding_value:.2f}")
        print(f"  총 자산(추정): ${refreshed_total_equity:.2f}")
        if execution_summary["failed"]:
            print("  ⚠️  일부 주문이 실패했습니다. 잔고와 체결 상태를 점검하세요.")
        set_exchange_default(api)


if __name__ == "__main__":
    main()
