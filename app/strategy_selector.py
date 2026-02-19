"""전략 선택 로직.

config의 selection 설정에 따라 active 전략 목록을 결정한다.

criteria 종류:
  - strategy_momentum: strategy_nav.csv 기반 NAV 모멘텀으로 선택
  - offensive_mode:    현재 신호 기반 (데이터 없을 때 사용)

공통 옵션:
  - mdd_filter_threshold: 현재 낙폭이 이 값 이하인 전략 제외
  - top_n:                상위 N개만 선택 (None이면 양수 전략 모두)
  - min_active_strategies: 최소 보장 개수 (없으면 fallback 사용)
  - fallback_strategy:     하나도 선택 안 될 때 사용
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
    min_active = int(selection_cfg.get("min_active_strategies", 1))
    fallback_name = selection_cfg.get("fallback_strategy", "permanent")

    candidates: List[Tuple[str, float]] = []  # (name, score)

    if criteria == "strategy_momentum":
        candidates = _select_by_nav_momentum(strategy_entries, top_n, mdd_threshold)
    elif criteria == "offensive_mode":
        candidates = _select_by_offensive_mode(
            strategy_entries, strategies, scores_by_strategy, mdd_threshold
        )
    else:
        raise ValueError(f"알 수 없는 선택 기준: '{criteria}'")

    # min_active 보장
    if len(candidates) < min_active:
        print(f"⚠️  active 전략 수({len(candidates)}) < min_active({min_active}), fallback 사용: {fallback_name}")
        # fallback이 이미 포함돼 있으면 그냥 반환
        names = [n for n, _ in candidates]
        if fallback_name not in names:
            candidates = [(fallback_name, 0.0)]
        elif not candidates:
            candidates = [(fallback_name, 0.0)]

    print("\n📊 선택된 active 전략:")
    for name, score in candidates:
        score_str = f"{score:.4f}" if score is not None else "N/A"
        print(f"  ✅ {name} (score: {score_str})")

    # 균등 비중 배분
    n = len(candidates)
    return [
        {"name": name, "weight": 1.0 / n}
        for name, _ in candidates
    ]


def _select_by_nav_momentum(
    strategy_entries: List[Dict],
    top_n: Optional[int],
    mdd_threshold: Optional[float],
) -> List[Tuple[str, float]]:
    """strategy_nav.csv의 NAV 데이터 기반으로 active 전략 선택."""
    from app.csv_logger import load_strategy_nav

    all_nav = load_strategy_nav()

    scored: List[Tuple[str, float, float]] = []  # (name, score, drawdown)

    for entry in strategy_entries:
        name = entry["name"]
        nav_series = all_nav.get(name, [])
        score, drawdown = _compute_nav_momentum(nav_series)

        if score is None:
            print(f"  ⚠️  {name}: NAV 데이터 부족 (워밍업 필요)")
            continue

        # MDD 필터
        if mdd_threshold is not None and drawdown < mdd_threshold:
            print(f"  ❌ {name}: 낙폭 {drawdown:.1%} < 임계값 {mdd_threshold:.1%} → 제외")
            continue

        scored.append((name, score, drawdown))
        print(f"  📈 {name}: score={score:.4f}, drawdown={drawdown:.1%}")

    # 점수 > 0 필터
    positive = [(n, s) for n, s, _ in scored if s > 0]

    if not positive:
        return []

    # 내림차순 정렬
    positive.sort(key=lambda x: x[1], reverse=True)

    if top_n is not None:
        positive = positive[:top_n]

    return positive


def _select_by_offensive_mode(
    strategy_entries: List[Dict],
    strategies: Dict[str, BaseStrategy],
    scores_by_strategy: Dict[str, Dict[str, Optional[float]]],
    mdd_threshold: Optional[float],
) -> List[Tuple[str, float]]:
    """현재 전략 신호(offensive/defensive)로 active 전략 선택."""
    from app.csv_logger import load_strategy_nav

    all_nav = load_strategy_nav() if mdd_threshold is not None else {}

    result: List[Tuple[str, float]] = []

    for entry in strategy_entries:
        name = entry["name"]
        strategy = strategies.get(name)
        if strategy is None:
            continue

        scores = scores_by_strategy.get(name, {})
        # 전략별 assets 캐시를 복원 후 판단
        from app.assets import reload_assets
        reload_assets(strategy.assets_file)
        offensive = strategy.is_offensive(scores)

        if not offensive:
            print(f"  ❌ {name}: 수비 모드 → 제외")
            continue

        # MDD 필터 (데이터 있을 때만)
        if mdd_threshold is not None:
            nav_series = all_nav.get(name, [])
            _, drawdown = _compute_nav_momentum(nav_series)
            if drawdown < mdd_threshold:
                print(f"  ❌ {name}: 낙폭 {drawdown:.1%} < 임계값 {mdd_threshold:.1%} → 제외")
                continue

        result.append((name, 1.0))
        print(f"  ✅ {name}: 공격 모드")

    return result
