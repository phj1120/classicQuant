"""거래 비용 모델.

미국 ETF 거래 기준:
- 스프레드 비용: 0.02% (bid-ask 스프레드 절반, 왕복)
- 리밸런싱 회전율 기반 비용 적용
- 세금/수수료는 별도 (KIS 증권사 수수료는 미반영, 표준 0.25% 미만)
"""
from typing import Dict, List


# 왕복 거래 비용률 (스프레드 + 암묵적 시장충격)
ROUNDTRIP_COST_RATE = 0.0005  # 0.05% 왕복


def estimate_turnover(prev_weights: Dict[str, float], new_weights: Dict[str, float]) -> float:
    """리밸런싱 회전율 추정.

    Returns: 0~1 범위의 회전율 (1 = 포트폴리오 전체 교체)
    """
    all_keys = set(prev_weights) | set(new_weights)
    turnover = 0.0
    for k in all_keys:
        turnover += abs(new_weights.get(k, 0.0) - prev_weights.get(k, 0.0))
    return turnover / 2.0  # 매도측 또는 매수측 기준


def apply_cost(nav: float, turnover: float, cost_rate: float = ROUNDTRIP_COST_RATE) -> float:
    """비용 적용 후 NAV 반환.

    nav: 비용 적용 전 NAV
    turnover: 0~1 회전율
    cost_rate: 왕복 비용률 (기본 0.05%)
    """
    cost = nav * turnover * cost_rate
    return nav - cost


def compute_net_nav_series(
    gross_nav_rows: List[Dict],
    weights_history: List[Dict],
) -> List[Dict]:
    """gross NAV 시계열에 비용을 반영해 net NAV를 계산한다.

    gross_nav_rows: [{"date": ..., "strategy": ..., "nav": ..., "daily_return": ...}, ...]
                   (strategy_nav.csv 형식)
    weights_history: [{"date": ..., "strategy": ..., "weights": {group: weight, ...}}, ...]
                    (리밸런싱 시 각 전략의 목표 비중 기록)

    Returns: gross_nav_rows에 "net_nav", "net_daily_return", "cost" 컬럼 추가한 리스트
    """
    # weights를 (date, strategy) 키로 인덱싱
    weights_by_key: Dict[tuple, Dict] = {}
    for w in weights_history:
        weights_by_key[(w["date"], w["strategy"])] = w.get("weights", {})

    result = []
    strategies = list({r["strategy"] for r in gross_nav_rows})
    rows_by_strategy: Dict[str, List] = {s: [] for s in strategies}
    for row in gross_nav_rows:
        rows_by_strategy[row["strategy"]].append(row)

    for strategy in strategies:
        rows = sorted(rows_by_strategy[strategy], key=lambda r: r["date"])
        prev_weights: Dict[str, float] = {}
        net_nav = 1.0

        for row in rows:
            date = row["date"]
            gross_return = float(row.get("daily_return", 0.0))

            # 이 날짜에 리밸런싱이 있었는지 확인
            new_weights = weights_by_key.get((date, strategy), {})

            if new_weights and prev_weights:
                turnover = estimate_turnover(prev_weights, new_weights)
            else:
                turnover = 0.0

            # net NAV = 전일 net NAV × (1 + gross_return) - 비용
            net_nav *= (1 + gross_return)
            cost_amount = net_nav * turnover * ROUNDTRIP_COST_RATE
            net_nav -= cost_amount
            net_return = (
                gross_return - (cost_amount / (net_nav + cost_amount))
                if (net_nav + cost_amount) > 0
                else gross_return
            )

            result.append({
                **row,
                "net_nav": f"{net_nav:.6f}",
                "net_daily_return": f"{net_return:.6f}",
                "cost": f"{cost_amount:.8f}",
                "turnover": f"{turnover:.4f}",
            })

            if new_weights:
                prev_weights = new_weights

    return sorted(result, key=lambda r: (r["date"], r["strategy"]))


def annualized_cost_drag(gross_cagr: float, net_cagr: float) -> float:
    """연간 비용 드래그 (gross CAGR - net CAGR)."""
    return gross_cagr - net_cagr
