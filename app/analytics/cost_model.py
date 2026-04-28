"""거래 비용 모델 — 한국투자증권(KIS) 해외주식 기준.

비용 구성:
- KIS 해외주식 온라인 수수료: 0.25% (편도)
- bid-ask 스프레드: 0.02% (편도)
- 왕복 거래 비용: 0.54% (수수료 × 2 + 스프레드 × 2)
- 환전 스프레드: 0.50% (KRW→USD, 온라인 우대환율 기준)
- 해외주식 양도소득세: 22% (국세 20% + 지방세 2%, 연간 250만원 공제)
"""
from typing import Dict, List, Optional, Tuple


# ── 거래 비용 ─────────────────────────────────────────────────────────
KIS_COMMISSION_RATE = 0.0025          # KIS 해외주식 수수료 편도 (0.25%)
SPREAD_COST_RATE    = 0.0002          # bid-ask 스프레드 편도 (0.02%)
ROUNDTRIP_COST_RATE = (KIS_COMMISSION_RATE + SPREAD_COST_RATE) * 2  # 0.0054 왕복

# ── 환전 비용 ─────────────────────────────────────────────────────────
FX_SPREAD_RATE = 0.005                # KRW→USD 환전 스프레드 (0.5%, 온라인 우대 기준)

# ── 양도소득세 ────────────────────────────────────────────────────────
OVERSEAS_CGT_RATE = 0.22              # 해외주식 양도소득세 (국세 20% + 지방세 2%)
CGT_EXEMPTION_KRW = 2_500_000        # 연간 기본공제 250만원

# 실 weight 내역 없을 때 적용하는 월별 회전율 기본 추정치
# TAA 전략 특성상 월 1회 리밸런싱, 평균 40% 교체 가정
DEFAULT_MONTHLY_TURNOVER = 0.40


def estimate_turnover(prev_weights: Dict[str, float], new_weights: Dict[str, float]) -> float:
    """리밸런싱 회전율 추정.

    Returns: 0~1 범위의 회전율 (1 = 포트폴리오 전체 교체)
    """
    all_keys = set(prev_weights) | set(new_weights)
    turnover = 0.0
    for k in all_keys:
        turnover += abs(new_weights.get(k, 0.0) - prev_weights.get(k, 0.0))
    return turnover / 2.0


def apply_cost(nav: float, turnover: float, cost_rate: float = ROUNDTRIP_COST_RATE) -> float:
    """거래 비용 적용 후 NAV 반환."""
    return nav - nav * turnover * cost_rate


def apply_annual_cgt(
    year_start_nav: float,
    year_end_nav: float,
    portfolio_value_krw: float,
    cgt_rate: float = OVERSEAS_CGT_RATE,
    exemption_krw: float = CGT_EXEMPTION_KRW,
) -> Tuple[float, float]:
    """연간 양도소득세 적용.

    연말 실현 손익을 KRW로 환산하여 250만원 공제 후 22% 과세.
    손실 연도에는 세금 없음.

    Returns:
        (세후 NAV, NAV 대비 세금 비율)
    """
    gain_ratio = year_end_nav / year_start_nav - 1.0
    if gain_ratio <= 0.0 or portfolio_value_krw <= 0.0:
        return year_end_nav, 0.0

    gain_krw = portfolio_value_krw * gain_ratio
    taxable_krw = max(0.0, gain_krw - exemption_krw)
    tax_krw = taxable_krw * cgt_rate

    tax_nav_drag = tax_krw / portfolio_value_krw
    return year_end_nav - tax_nav_drag, tax_nav_drag


def compute_net_nav_series(
    gross_nav_rows: List[Dict],
    weights_history: List[Dict],
    cost_rate: float = ROUNDTRIP_COST_RATE,
) -> List[Dict]:
    """gross NAV 시계열에 거래 비용을 반영해 net NAV를 계산한다.

    gross_nav_rows: [{"date": ..., "strategy": ..., "nav": ..., "daily_return": ...}, ...]
    weights_history: [{"date": ..., "strategy": ..., "weights": {group: weight, ...}}, ...]
                     비어 있으면 DEFAULT_MONTHLY_TURNOVER 기반 월말 회전율 적용

    Returns: gross_nav_rows에 "net_nav", "net_daily_return", "cost" 컬럼 추가한 리스트
    """
    weights_by_key: Dict[tuple, Dict] = {}
    for w in weights_history:
        weights_by_key[(w["date"], w["strategy"])] = w.get("weights", {})

    use_estimated_turnover = not weights_history

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
            net_nav *= (1.0 + gross_return)

            new_weights = weights_by_key.get((date, strategy), {})
            if use_estimated_turnover:
                # 월말(마지막 2자리 >= 28이거나 다음 행 월이 바뀌는 날) 추정 회전율 적용
                is_month_end = date[8:] in ("28", "29", "30", "31")
                turnover = DEFAULT_MONTHLY_TURNOVER if is_month_end else 0.0
            elif new_weights and prev_weights:
                turnover = estimate_turnover(prev_weights, new_weights)
            else:
                turnover = 0.0

            cost_amount = net_nav * turnover * cost_rate
            net_nav -= cost_amount
            net_return = (
                gross_return - cost_amount / (net_nav + cost_amount)
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


def compute_kis_net_nav(
    gross_nav_rows: List[Dict],
    portfolio_value_krw: float,
    apply_fx: bool = True,
    apply_cgt: bool = True,
    commission_rate: float = KIS_COMMISSION_RATE,
    spread_rate: float = SPREAD_COST_RATE,
    fx_rate: float = FX_SPREAD_RATE,
    cgt_rate: float = OVERSEAS_CGT_RATE,
    exemption_krw: float = CGT_EXEMPTION_KRW,
    monthly_turnover: float = DEFAULT_MONTHLY_TURNOVER,
) -> List[Dict]:
    """KIS 해외주식 기준 수수료 + 환전 + 양도소득세 통합 비용 적용.

    gross_nav_rows: strategy_nav.csv 형식 행 목록
    portfolio_value_krw: 포트폴리오 총액 (KRW, 양도소득세 공제 계산용)
    apply_fx: 환전 스프레드 적용 여부 (KRW 계좌로 USD ETF 매매 시)
    apply_cgt: 양도소득세 적용 여부

    Returns: "kis_net_nav", "cost_commission", "cost_fx", "cost_cgt" 컬럼 추가한 리스트
    """
    roundtrip_rate = (commission_rate + spread_rate) * 2.0

    strategies = list({r["strategy"] for r in gross_nav_rows})
    rows_by_strategy: Dict[str, List] = {s: [] for s in strategies}
    for row in gross_nav_rows:
        rows_by_strategy[row["strategy"]].append(row)

    result = []

    for strategy in strategies:
        rows = sorted(rows_by_strategy[strategy], key=lambda r: r["date"])
        nav = 1.0
        year_start_nav = 1.0
        nav_after_tax = 1.0
        current_year: Optional[str] = None
        cum_commission = 0.0
        cum_fx = 0.0
        cum_cgt = 0.0

        # 최초 환전 비용 (첫 투자 시 KRW→USD)
        if apply_fx:
            fx_cost = nav * fx_rate
            nav -= fx_cost
            cum_fx += fx_cost

        for i, row in enumerate(rows):
            date = row["date"]
            year = date[:4]
            gross_return = float(row.get("daily_return", 0.0))

            # 연도가 바뀌면 이전 연도 양도소득세 적용
            if apply_cgt and current_year and year != current_year:
                nav_after_tax, tax_drag = apply_annual_cgt(
                    year_start_nav, nav, portfolio_value_krw, cgt_rate, exemption_krw
                )
                cum_cgt += nav - nav_after_tax
                nav = nav_after_tax
                year_start_nav = nav

            if current_year != year:
                current_year = year

            nav *= (1.0 + gross_return)

            # 월말 거래 비용 (수수료 + 스프레드, 왕복)
            is_month_end = date[8:] in ("28", "29", "30", "31")
            if is_month_end:
                commission_cost = nav * monthly_turnover * roundtrip_rate
                nav -= commission_cost
                cum_commission += commission_cost
            else:
                commission_cost = 0.0

            result.append({
                **row,
                "kis_net_nav": f"{nav:.6f}",
                "cost_commission": f"{commission_cost:.8f}",
                "cost_fx": "0.0",
                "cost_cgt": "0.0",
            })

        # 마지막 연도 양도소득세 (시계열 종료 시)
        nav_after_tax = nav
        if apply_cgt and current_year:
            nav_after_tax, tax_drag = apply_annual_cgt(
                year_start_nav, nav, portfolio_value_krw, cgt_rate, exemption_krw
            )
            cum_cgt += nav - nav_after_tax

        # 마지막 행에 누적 비용 기록
        if result:
            last = result[-1]
            last["cum_cost_commission"] = f"{cum_commission:.6f}"
            last["cum_cost_fx"] = f"{cum_fx:.6f}"
            last["cum_cost_cgt"] = f"{cum_cgt:.6f}"
            last["kis_net_nav_final"] = f"{nav_after_tax if apply_cgt else nav:.6f}"

    return sorted(result, key=lambda r: (r["date"], r["strategy"]))


def annualized_cost_drag(gross_cagr: float, net_cagr: float) -> float:
    """연간 비용 드래그 (gross CAGR - net CAGR)."""
    return gross_cagr - net_cagr
