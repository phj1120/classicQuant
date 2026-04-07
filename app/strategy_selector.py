"""전략 선택 로직.

config의 selection 설정에 따라 active 전략 목록을 결정한다.

criteria 종류:
  - strategy_momentum: strategy_nav.csv 기반 NAV 모멘텀으로 선택
  - offensive_mode:    현재 신호 기반 (데이터 없을 때 사용)

공통 옵션:
  - mdd_filter_threshold: 현재 낙폭이 이 값 이하인 전략 제외
  - top_n:                상위 N개만 선택 (None이면 양수 전략 모두); 미충족 시 fallback으로 보완
  - fallback_strategy:     top_n 미충족 또는 선택 결과가 없을 때 추가 보유
"""

import math
from typing import Dict, List, Optional, Tuple

from app.constants import LOOKBACK_DAYS
from app.strategy import BaseStrategy


def _compute_nav_momentum(nav_series: List[Dict]) -> Tuple[Optional[float], float]:
    """NAV 시계열에서 모멘텀 점수와 현재 낙폭(drawdown)을 계산한다.

    nav_series: [{"date": ..., "nav": "1.234"}, ...] 날짜 오름차순
    반환: (momentum_score, current_drawdown)
    """
    if not nav_series:
        return None, 0.0

    prices = []
    for row in nav_series:
        try:
            prices.append(float(row["nav"]))
        except (KeyError, ValueError, TypeError):
            continue

    if len(prices) < 2:
        return None, 0.0

    def _ret(lookback: int) -> Optional[float]:
        if len(prices) <= lookback:
            return None
        past = prices[-1 - lookback]
        if past <= 0:
            return None
        return (prices[-1] / past) - 1.0

    r1 = _ret(LOOKBACK_DAYS["1m"])
    r3 = _ret(LOOKBACK_DAYS["3m"])
    r6 = _ret(LOOKBACK_DAYS["6m"])
    r12 = _ret(LOOKBACK_DAYS["12m"])

    if None in (r1, r3, r6, r12):
        score = None
    else:
        score = (r1 * 12) + (r3 * 4) + (r6 * 2) + (r12 * 1)

    # 현재 낙폭 (drawdown)
    peak = max(prices)
    current = prices[-1]
    drawdown = (current / peak) - 1.0 if peak > 0 else 0.0

    return score, drawdown


def select_active_strategies(
    strategy_entries: List[Dict],
    strategies: Dict[str, BaseStrategy],
    scores_by_strategy: Dict[str, Dict[str, Optional[float]]],
    selection_cfg: Dict,
) -> List[Dict]:
    """active 전략 목록을 반환한다.

    Args:
        strategy_entries: config의 전략 목록 [{"name": ..., "weight": ...}]
        strategies: {name: BaseStrategy 인스턴스}
        scores_by_strategy: {name: {group: score}} - 전략별 현재 모멘텀 점수
        selection_cfg: load_selection_config()에서 로드한 선택 설정

    Returns:
        active 전략 목록 (균등 비중 재계산됨)
    """
    criteria = selection_cfg.get("criteria", "strategy_momentum")
    top_n = selection_cfg.get("top_n")
    mdd_threshold = selection_cfg.get("mdd_filter_threshold")
    fallback_name = selection_cfg.get("fallback_strategy", "permanent")

    candidates: List[Tuple[str, float]] = []  # (name, score)

    _NAV_CRITERIA = {
        "strategy_momentum", "return_1m", "return_3m",
        "return_6m", "return_12m", "sharpe_12m", "calmar_12m",
        "corr_constrained",
    }
    rolling_peak_window = selection_cfg.get("rolling_peak_window", 252)
    mdd_threshold_ratio = selection_cfg.get("mdd_threshold_ratio")

    if criteria in _NAV_CRITERIA:
        candidates = _select_by_nav_score(
            strategy_entries, criteria, top_n, mdd_threshold,
            rolling_peak_window, mdd_threshold_ratio,
        )
    elif criteria == "offensive_mode":
        candidates = _select_by_offensive_mode(
            strategy_entries, strategies, scores_by_strategy,
            mdd_threshold, mdd_threshold_ratio,
        )
    else:
        raise ValueError(f"알 수 없는 선택 기준: '{criteria}'")

    # 유효 전략 0개면 fallback 단독 사용
    if not candidates:
        print(f"⚠️  유효 전략 없음, fallback 사용: {fallback_name}")
        candidates = [(fallback_name, 0.0)]
    # 실제 선택된 전략 수 기준으로 재정규화한다.
    # corr_constrained 등으로 후보 수가 top_n보다 적어질 수 있으므로,
    # 고정 슬롯 비중을 유지하면 의도치 않은 현금 비중이 생긴다.
    slot_weight = 1.0 / len(candidates)

    print("\n📊 선택된 active 전략:")
    for name, score in candidates:
        score_str = f"{score:.4f}" if score is not None else "N/A"
        print(f"  ✅ {name} (score: {score_str}, weight: {slot_weight:.1%})")

    return [
        {"name": name, "weight": slot_weight}
        for name, _ in candidates
    ]


def _rolling_drawdown(prices: List[float], window: int = 252) -> float:
    """롤링 윈도우 피크 대비 현재 낙폭을 반환한다.

    window일 내 최고가 기준으로 현재 NAV의 낙폭을 계산한다.
    전체 기간 ATH 대신 최근 추세 이탈 여부를 측정하기 위해 사용한다.
    """
    if not prices:
        return 0.0
    recent = prices[-window:] if len(prices) > window else prices
    peak = max(recent)
    return (prices[-1] / peak - 1.0) if peak > 0 else 0.0


def _historical_mdd(prices: List[float]) -> float:
    """전체 NAV 히스토리에서 최대 낙폭(MDD)을 계산한다."""
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    mdd = 0.0
    for p in prices:
        peak = max(peak, p)
        mdd = min(mdd, (p - peak) / peak)
    return mdd


def _effective_mdd_threshold(
    prices: List[float],
    mdd_threshold: Optional[float],
    mdd_threshold_ratio: Optional[float],
) -> Optional[float]:
    """전략별 유효 MDD 임계값 반환.

    mdd_threshold_ratio가 있으면 역대 MDD × ratio를 사용한다.
    ratio를 쓰면 전략마다 다른 변동성을 자동으로 반영하므로 하드코딩 불필요.
    fallback: mdd_threshold (전역 고정값).
    """
    if mdd_threshold_ratio is not None:
        hist_mdd = _historical_mdd(prices)
        if hist_mdd < 0:
            return hist_mdd * mdd_threshold_ratio
    return mdd_threshold


def _select_by_nav_score(
    strategy_entries: List[Dict],
    criteria: str,
    top_n: Optional[int],
    mdd_threshold: Optional[float],
    rolling_peak_window: int = 252,
    mdd_threshold_ratio: Optional[float] = None,
) -> List[Tuple[str, float]]:
    """strategy_nav.csv NAV 데이터 기반 다양한 기준으로 전략 선택."""
    from app.analytics.csv_logger import load_strategy_nav

    all_nav = load_strategy_nav()
    scored: List[Tuple[str, float, float]] = []  # (name, score, drawdown)

    for entry in strategy_entries:
        name = entry["name"]
        nav_series = all_nav.get(name, [])
        if not nav_series:
            print(f"  ⚠️  {name}: NAV 데이터 없음")
            continue

        prices = [float(row["nav"]) for row in nav_series if row.get("nav")]
        rets = [float(row["daily_return"]) for row in nav_series if row.get("daily_return")]

        if criteria == "strategy_momentum":
            score, _ = _compute_nav_momentum(nav_series)  # score만 사용, drawdown은 롤링으로 재계산
        else:
            if criteria == "corr_constrained":
                score = _compute_nav_score(prices, rets, "sharpe_12m")
            else:
                score = _compute_nav_score(prices, rets, criteria)

        # 롤링 피크 기반 현재 낙폭
        drawdown = _rolling_drawdown(prices, rolling_peak_window)
        effective_threshold = _effective_mdd_threshold(prices, mdd_threshold, mdd_threshold_ratio)

        if score is None:
            print(f"  ⚠️  {name}: NAV 데이터 부족 (워밍업 필요)")
            continue

        # MDD 필터
        if effective_threshold is not None and drawdown < effective_threshold:
            label = f"역대MDD×{mdd_threshold_ratio}" if mdd_threshold_ratio else "고정"
            print(f"  ❌ {name}: 낙폭 {drawdown:.1%} < 임계값 {effective_threshold:.1%} ({label}) → 제외")
            continue

        scored.append((name, score, drawdown))
        print(f"  📈 {name}: score={score:.4f}, drawdown={drawdown:.1%}")

    if not scored:
        return []

    # strategy_momentum만 score > 0 필터 적용
    if criteria == "strategy_momentum":
        candidates = [(n, s) for n, s, _ in scored if s > 0]
    else:
        candidates = [(n, s) for n, s, _ in scored]

    if not candidates:
        return []

    candidates.sort(key=lambda x: x[1], reverse=True)

    if criteria == "corr_constrained":
        candidates = _apply_corr_filter(candidates, all_nav, top_n)
    elif top_n is not None:
        candidates = candidates[:top_n]

    return candidates


def _apply_corr_filter(
    ranked: List[Tuple[str, float]],
    all_nav: Dict,
    top_n: Optional[int],
    corr_threshold: float = 0.7,
    window: int = 63,
) -> List[Tuple[str, float]]:
    """상관관계 필터: 이미 선택된 전략과 corr_threshold 이상인 전략 제외."""
    rets_map = {
        name: [float(row["daily_return"]) for row in series if row.get("daily_return")]
        for name, series in all_nav.items()
    }
    selected: List[Tuple[str, float]] = []
    for name, score in ranked:
        if not selected:
            selected.append((name, score))
            continue
        max_corr = max(
            _corr(rets_map.get(name, []), rets_map.get(s, []), window) or 0.0
            for s, _ in selected
        )
        if max_corr < corr_threshold:
            selected.append((name, score))
        if top_n is not None and len(selected) >= top_n:
            break
    if not selected and ranked:
        selected = [ranked[0]]
    return selected


def _corr(a: List[float], b: List[float], window: int = 63) -> Optional[float]:
    if len(a) < window or len(b) < window:
        return None
    a, b = a[-window:], b[-window:]
    mean_a = sum(a) / window
    mean_b = sum(b) / window
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(window)) / (window - 1)
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a) / (window - 1))
    std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b) / (window - 1))
    if std_a < 1e-10 or std_b < 1e-10:
        return None
    return cov / (std_a * std_b)


def _compute_nav_score(
    prices: List[float],
    rets: List[float],
    criteria: str,
) -> Optional[float]:
    """기준별 NAV 점수 계산."""
    lookback = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}

    if criteria in ("return_1m", "return_3m", "return_6m", "return_12m"):
        days = lookback[criteria.replace("return_", "")]
        if len(prices) <= days:
            return None
        past = prices[-1 - days]
        return (prices[-1] / past - 1.0) if past > 0 else None

    if criteria == "sharpe_12m":
        if len(rets) < lookback["12m"]:
            return None
        window = rets[-lookback["12m"]:]
        mean = sum(window) / len(window)
        std = math.sqrt(sum((r - mean) ** 2 for r in window) / max(len(window) - 1, 1))
        return (mean / std) * math.sqrt(252) if std > 1e-10 else None

    if criteria == "calmar_12m":
        days = lookback["12m"]
        if len(prices) <= days:
            return None
        r12 = prices[-1] / prices[-1 - days] - 1.0
        window = prices[-days:]
        peak = window[0]
        mdd = 0.0
        for p in window:
            peak = max(peak, p)
            mdd = min(mdd, (p - peak) / peak)
        if abs(mdd) < 1e-10:
            return r12
        cagr = (1 + r12) ** (252 / days) - 1
        return cagr / abs(mdd)

    return None


def _select_by_offensive_mode(
    strategy_entries: List[Dict],
    strategies: Dict[str, BaseStrategy],
    scores_by_strategy: Dict[str, Dict[str, Optional[float]]],
    mdd_threshold: Optional[float],
    mdd_threshold_ratio: Optional[float] = None,
) -> List[Tuple[str, float]]:
    """현재 전략 신호(offensive/defensive)로 active 전략 선택."""
    from app.analytics.csv_logger import load_strategy_nav

    all_nav = load_strategy_nav() if mdd_threshold is not None else {}

    result: List[Tuple[str, float]] = []

    for entry in strategy_entries:
        name = entry["name"]
        strategy = strategies.get(name)
        if strategy is None:
            continue

        scores = scores_by_strategy.get(name, {})
        # 전략별 assets 캐시를 복원 후 판단
        from app.assets.assets import reload_assets
        reload_assets(strategy.assets)
        offensive = strategy.is_offensive(scores)

        if not offensive:
            print(f"  ❌ {name}: 수비 모드 → 제외")
            continue

        # MDD 필터 (데이터 있을 때만)
        if mdd_threshold is not None:
            nav_series = all_nav.get(name, [])
            prices_dd = [float(row["nav"]) for row in nav_series if row.get("nav")]
            drawdown = _rolling_drawdown(prices_dd)
            effective_threshold = _effective_mdd_threshold(prices_dd, mdd_threshold, mdd_threshold_ratio)
            if drawdown < effective_threshold:
                print(f"  ❌ {name}: 낙폭 {drawdown:.1%} < 임계값 {effective_threshold:.1%} → 제외")
                continue

        result.append((name, 1.0))
        print(f"  ✅ {name}: 공격 모드")

    return result
