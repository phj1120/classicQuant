import argparse
import sys
from pathlib import Path

# PYTHONPATH 없이도 app 모듈을 찾을 수 있도록 설정
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import (
    build_kis_config,
    build_strategy_config,
    load_config,
    load_key,
    load_selection_config,
    load_strategy_entries,
)
from app.assets import merge_assets_files, reload_assets
from app.csv_logger import save_holdings, save_momentum, save_ohlc_history, save_portfolio, save_strategy_signal
from app.csv_logger import load_portfolio_nav, save_portfolio_nav
from app.exchange import set_exchange_default
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from app.constants import US_MARKET_TZ
from app.kis_api import KoreaInvestmentAPI
from app.market import is_us_market_holiday
from app.data_utils import parse_history
from app.momentum import get_momentum_scores
from app.groups import group_tickers
from app.portfolio import build_group_orders, execute_orders, get_holdings_all_exchanges, get_prices
from app.report import write_report
from app.strategy_selector import select_active_strategies
from app.strategies import get_strategy


def _run_strategy(strategy_entry, api, prices, today):
    """단일 전략을 실행하여 (weighted_targets, scores, targets, strategy_instance)를 반환한다."""
    name = strategy_entry["name"]
    weight = strategy_entry["weight"]

    strategy = get_strategy(name)

    # 전략별 assets 로드
    reload_assets(strategy.assets_file)

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


def _check_portfolio_mdd(selection_cfg: dict) -> tuple:
    """portfolio_nav.csv 기반 포트폴리오 MDD 체크.

    Returns:
        (triggered: bool, current_dd: float)
    """
    mdd_limit = selection_cfg.get("portfolio_mdd_limit")
    if mdd_limit is None:
        return False, 0.0

    history = load_portfolio_nav()
    if not history:
        return False, 0.0

    navs = []
    for row in history:
        try:
            navs.append(float(row["nav"]))
        except (ValueError, TypeError):
            continue

    if not navs:
        return False, 0.0

    peak = max(navs)
    current_dd = (navs[-1] / peak - 1.0) if peak > 1e-10 else 0.0
    triggered = current_dd < mdd_limit
    return triggered, current_dd


def _update_portfolio_nav(today: str, active_entries: list) -> None:
    """active 전략의 최근 daily_return 가중 평균으로 portfolio_nav.csv를 업데이트."""
    from app.csv_logger import load_strategy_nav

    if not active_entries:
        return

    all_nav = load_strategy_nav()
    total_weight = 0.0
    weighted_return = 0.0

    for entry in active_entries:
        name = entry["name"]
        weight = entry.get("weight", 0.0)
        nav_series = all_nav.get(name, [])
        if not nav_series:
            continue
        # 가장 최근 daily_return 사용
        last_row = nav_series[-1]
        try:
            dr = float(last_row.get("daily_return", 0))
        except (ValueError, TypeError):
            continue
        weighted_return += weight * dr
        total_weight += weight

    if total_weight > 1e-10:
        portfolio_dr = weighted_return / total_weight
    else:
        portfolio_dr = 0.0

    # 기존 portfolio_nav 마지막 값 기준으로 NAV 계산
    history = load_portfolio_nav()
    if history:
        try:
            last_nav = float(history[-1]["nav"])
        except (ValueError, TypeError):
            last_nav = 1.0
        # 오늘 날짜가 이미 있으면 스킵 (save_portfolio_nav 내부에서도 체크)
    else:
        last_nav = 1.0

    new_nav = last_nav * (1.0 + portfolio_dr)
    save_portfolio_nav(today, new_nav, portfolio_dr)


def main() -> None:
    parser = argparse.ArgumentParser(description="퀀트 자동 리밸런싱")
    parser.add_argument("--report-only", action="store_true", help="리포트만 생성 (매매 실행 안 함)")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"
    key_path = base_dir / "key.json"

    raw = load_config(config_path)
    key = load_key(key_path if key_path.exists() else None)

    kis_config = build_kis_config(key)
    strategy_cfg = build_strategy_config(raw)
    strategy_entries = load_strategy_entries(raw)
    selection_cfg = load_selection_config(raw)

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
    today = datetime.now().strftime("%Y-%m-%d")

    # 공통 데이터 조회
    holdings_detail = get_holdings_all_exchanges(api)
    cash = api.get_account_cash() or 0.0
    balance_prices = {t: info.get("price") for t, info in holdings_detail.items() if info.get("price")}
    prices = dict(balance_prices)

    holding_value = sum((prices.get(t, 0.0) or 0.0) * info["qty"] for t, info in holdings_detail.items())
    total_equity = cash + holding_value

    print(f"\n💵 현금: ${cash:.2f}")
    print(f"📈 보유 평가액: ${holding_value:.2f}")
    print(f"🧮 총 자산(추정): ${total_equity:.2f}")

    # 포트폴리오 MDD 서킷 브레이커 체크
    circuit_triggered, portfolio_dd = _check_portfolio_mdd(selection_cfg)
    mdd_limit = selection_cfg.get("portfolio_mdd_limit")
    if mdd_limit is not None:
        status = "⛔ 서킷 브레이커 발동" if circuit_triggered else "✅ 정상"
        print(f"📉 포트폴리오 낙폭: {portfolio_dd:.1%} (한도: {mdd_limit:.1%}) {status}")

    # CSV 로깅: 보유 현황
    from app.groups import group_for_ticker
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
            asset_files.append(strategy.assets_file)
        except Exception as e:
            print(f"❌ {entry['name']} 전략 실패: {e}")

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
        print(f"\n⛔ 포트폴리오 MDD 서킷 브레이커 → {fallback_name} 단독 운용")
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
    merge_assets_files(asset_files)

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
        cash_buffer_pct=float(strategy_cfg.get("cash_buffer_pct", 0.0)),
        min_trade_value_usd=float(strategy_cfg.get("min_trade_value_usd", 5.0)),
        rebalance_threshold_pct=float(strategy_cfg.get("rebalance_threshold_pct", 0.0)),
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
    save_portfolio(today, total_equity, cash, all_report_data, merged_targets, selected_tickers)

    # 리포트 생성
    report_path = write_report(all_report_data, Path(__file__).resolve().parent / "reports")
    print(f"\n📝 리포트 저장: {report_path}")

    # 주문 실행
    if args.report_only:
        print("\n📋 리포트 전용 모드: 매매 실행 생략")
    else:
        execute_orders(api, all_orders, holdings_detail)

    # 포트폴리오 NAV 업데이트 (report_only 여부 무관)
    _update_portfolio_nav(today, active_entries)


if __name__ == "__main__":
    main()
