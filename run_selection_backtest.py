"""전략 선택 기준 비교 백테스트.

data/strategy_nav.csv의 NAV 시계열을 이용해 선택 기준 × top_n × MDD 임계값
조합을 비교하여 최적 설정을 찾습니다.

실행:
    python run_selection_backtest.py                  # top_n=3, 기본 비교
    python run_selection_backtest.py --top-n 5        # top_n 지정
    python run_selection_backtest.py --sweep          # top_n 1~15 Sharpe 히트맵
    python run_selection_backtest.py --full           # 전체 조합 파레토 분석
"""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

DATA_DIR = Path(__file__).resolve().parent / "data"
NAV_CSV = DATA_DIR / "strategy_nav.csv"

LOOKBACK = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}

CRITERIA = [
    "nav_momentum",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_12m",
    "sharpe_12m",
    "calmar_12m",
    "corr_constrained",
    "equal_weight",
]

MDD_THRESHOLDS = [None, -0.05, -0.10, -0.15, -0.20, -0.25]
CORR_THRESHOLD = 0.7  # 상관관계 필터 임계값 (corr_constrained 기준)


# ── 데이터 로딩 ────────────────────────────────────────────────────────────────

def load_nav_data() -> Dict[str, List[Tuple[str, float, float]]]:
    """strategy_nav.csv → {strategy: [(date, daily_return, nav), ...]} 오름차순."""
    if not NAV_CSV.exists():
        return {}
    data: Dict[str, List] = defaultdict(list)
    with open(NAV_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                data[row["strategy"]].append((
                    row["date"].strip(),
                    float(row["daily_return"]),
                    float(row["nav"]),
                ))
            except (KeyError, ValueError):
                continue
    return {k: sorted(v, key=lambda x: x[0]) for k, v in data.items()}


# ── 날짜 유틸 ──────────────────────────────────────────────────────────────────

def get_month_ends(dates: List[str]) -> List[str]:
    month_last: Dict[str, str] = {}
    for d in sorted(dates):
        month_last[d[:7]] = d
    return sorted(month_last.values())


def nav_at(series: List[Tuple[str, float, float]], date: str) -> Optional[float]:
    for d, _, nav in reversed(series):
        if d <= date:
            return nav
    return None


def nav_lookback(
    series: List[Tuple[str, float, float]], date: str, days: int
) -> Optional[float]:
    past = [(d, nav) for d, _, nav in series if d <= date]
    if len(past) <= days:
        return None
    return past[-1 - days][1]


# ── 점수 함수들 ────────────────────────────────────────────────────────────────

def score_nav_momentum(series, date: str) -> Optional[float]:
    now = nav_at(series, date)
    if now is None:
        return None
    results = {}
    for key, days in LOOKBACK.items():
        past = nav_lookback(series, date, days)
        if past is None or past <= 0:
            return None
        results[key] = now / past - 1.0
    r1, r3, r6, r12 = results["1m"], results["3m"], results["6m"], results["12m"]
    return (r1 * 12) + (r3 * 4) + (r6 * 2) + r12


def score_return(series, date: str, days: int) -> Optional[float]:
    now = nav_at(series, date)
    past = nav_lookback(series, date, days)
    if now is None or past is None or past <= 0:
        return None
    return now / past - 1.0


def score_sharpe_12m(series, date: str) -> Optional[float]:
    past = [(d, r) for d, r, _ in series if d <= date]
    if len(past) < LOOKBACK["12m"]:
        return None
    rets = [r for _, r in past[-LOOKBACK["12m"]:]]
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    std = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    if std < 1e-10:
        return None
    return (mean / std) * math.sqrt(252)


def score_calmar_12m(series, date: str) -> Optional[float]:
    r12 = score_return(series, date, LOOKBACK["12m"])
    if r12 is None:
        return None
    past = [(d, nav) for d, _, nav in series if d <= date]
    if len(past) < LOOKBACK["12m"]:
        return None
    navs = [nav for _, nav in past[-LOOKBACK["12m"]:]]
    peak = navs[0]
    mdd = 0.0
    for nav in navs:
        peak = max(peak, nav)
        mdd = min(mdd, (nav - peak) / peak)
    if abs(mdd) < 1e-10:
        return r12
    cagr = (1 + r12) ** (252 / LOOKBACK["12m"]) - 1
    return cagr / abs(mdd)


def get_score(series, date: str, criterion: str) -> Optional[float]:
    if criterion == "nav_momentum":
        return score_nav_momentum(series, date)
    if criterion == "return_1m":
        return score_return(series, date, LOOKBACK["1m"])
    if criterion == "return_3m":
        return score_return(series, date, LOOKBACK["3m"])
    if criterion == "return_6m":
        return score_return(series, date, LOOKBACK["6m"])
    if criterion == "return_12m":
        return score_return(series, date, LOOKBACK["12m"])
    if criterion == "sharpe_12m":
        return score_sharpe_12m(series, date)
    if criterion == "calmar_12m":
        return score_calmar_12m(series, date)
    if criterion == "equal_weight":
        return 1.0
    if criterion == "corr_constrained":
        return score_sharpe_12m(series, date)
    return None


def current_drawdown(series, date: str) -> float:
    """date 기준 현재 낙폭."""
    past_navs = [nav for d, _, nav in series if d <= date]
    if not past_navs:
        return 0.0
    peak = max(past_navs)
    return (past_navs[-1] / peak - 1.0) if peak > 0 else 0.0


def _compute_corr(ret_a: List[float], ret_b: List[float], window: int = 63) -> Optional[float]:
    """두 수익률 시계열의 피어슨 상관관계 (최근 window일)."""
    if len(ret_a) < window or len(ret_b) < window:
        return None
    a = ret_a[-window:]
    b = ret_b[-window:]
    mean_a = sum(a) / window
    mean_b = sum(b) / window
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(window)) / (window - 1)
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a) / (window - 1))
    std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b) / (window - 1))
    if std_a < 1e-10 or std_b < 1e-10:
        return None
    return cov / (std_a * std_b)


# ── 시뮬레이션 ─────────────────────────────────────────────────────────────────

def simulate(
    nav_data: Dict[str, List[Tuple[str, float, float]]],
    criterion: str,
    top_n: int,
    years: int,
    mdd_threshold: Optional[float] = None,
) -> Tuple[List[Tuple[str, float]], List[str], Dict[str, int]]:
    """선택 기준별 포트폴리오 시뮬레이션.

    Returns:
        ([(date, portfolio_nav), ...], 마지막 선택 전략 목록, 전략별 선택 횟수)
    """
    all_dates = sorted(set(d for s in nav_data.values() for d, _, _ in s))
    if not all_dates:
        return [], [], {}

    cutoff = all_dates[-1]
    start_year = int(cutoff[:4]) - years
    start = f"{start_year}{cutoff[4:]}"
    dates = [d for d in all_dates if d >= start]
    if len(dates) < 60:
        return [], [], {}

    month_ends_set = set(get_month_ends(dates))
    daily_ret_map: Dict[str, Dict[str, float]] = {
        name: {d: r for d, r, _ in series}
        for name, series in nav_data.items()
    }

    portfolio_nav = 1.0
    results: List[Tuple[str, float]] = []
    weights: Dict[str, float] = {}
    last_selection: List[str] = []
    selection_count: Dict[str, int] = defaultdict(int)

    for i, date in enumerate(dates):
        if i == 0:
            results.append((date, portfolio_nav))
            continue

        if date in month_ends_set:
            scores: Dict[str, float] = {}
            for name, series in nav_data.items():
                # MDD 필터
                if mdd_threshold is not None:
                    dd = current_drawdown(series, date)
                    if dd < mdd_threshold:
                        continue
                sc = get_score(series, date, criterion)
                if sc is not None:
                    scores[name] = sc

            if scores:
                ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

                if criterion == "equal_weight":
                    selected = [n for n, _ in ranked]
                elif criterion == "nav_momentum":
                    selected = [n for n, sc in ranked if sc > 0][:top_n]
                    if not selected and ranked:
                        selected = [ranked[0][0]]
                else:
                    selected = [n for n, _ in ranked[:top_n]]

                if criterion == "corr_constrained":
                    # sharpe_12m 점수 기반 랭킹 + 상관관계 필터로 재선택
                    ret_map = {
                        name: [r for d, r, _ in nav_data[name] if d <= date]
                        for name in scores
                    }
                    selected = []
                    for name, _ in ranked:
                        if not selected:
                            selected.append(name)
                            continue
                        max_corr = max(
                            (_compute_corr(ret_map[name], ret_map[s]) or 0.0)
                            for s in selected
                        )
                        if max_corr < CORR_THRESHOLD:
                            selected.append(name)
                        if len(selected) >= top_n:
                            break
                    if not selected and ranked:
                        selected = [ranked[0][0]]

                if selected:
                    last_selection = selected
                    weights = {s: 1.0 / len(selected) for s in selected}
                    for s in selected:
                        selection_count[s] += 1

        if weights:
            total_w = 0.0
            daily_portfolio_ret = 0.0
            for name, w in weights.items():
                r = daily_ret_map.get(name, {}).get(date)
                if r is not None:
                    daily_portfolio_ret += w * r
                    total_w += w
            if total_w > 1e-10:
                daily_portfolio_ret /= total_w

            portfolio_nav *= (1.0 + daily_portfolio_ret)

        results.append((date, portfolio_nav))

    return results, last_selection, dict(selection_count)


# ── 성과 지표 ──────────────────────────────────────────────────────────────────

def compute_metrics(results: List[Tuple[str, float]]) -> Dict:
    if len(results) < 2:
        return {}
    navs = [n for _, n in results]
    n_days = len(navs)

    cagr = (navs[-1] / navs[0]) ** (252 / n_days) - 1
    rets = [navs[i] / navs[i - 1] - 1 for i in range(1, n_days)]
    mean_r = sum(rets) / len(rets)
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / max(len(rets) - 1, 1))
    sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 1e-10 else 0.0

    peak = navs[0]
    mdd = 0.0
    for nav in navs:
        peak = max(peak, nav)
        mdd = min(mdd, (nav - peak) / peak)

    calmar = cagr / abs(mdd) if abs(mdd) > 1e-10 else 0.0
    return {"cagr": cagr, "sharpe": sharpe, "mdd": mdd, "calmar": calmar, "final_nav": navs[-1]}


# ── 출력 ───────────────────────────────────────────────────────────────────────

def _mdd_label(mdd_threshold: Optional[float]) -> str:
    return "없음" if mdd_threshold is None else f"{mdd_threshold:.0%}"


def print_results(
    all_metrics: Dict,
    top_n: int,
    years: int,
    selection_counts: Dict,
) -> str:
    """결과 테이블 출력. 권장 기준(Sharpe 기준)을 반환."""
    print(f"\n{'═'*72}")
    print(f"  선택 기준 백테스트 결과 | top_n={top_n} | 기간={years}년")
    print(f"{'═'*72}")
    print(f"  {'기준':<18} {'CAGR':>7} {'Sharpe':>7} {'MDD':>7} {'Calmar':>7}  {'최종NAV':>8}")
    print(f"  {'─'*68}")

    dynamic = [(k, v) for k, v in all_metrics.items() if k != "equal_weight"]
    dynamic.sort(key=lambda x: x[1].get("sharpe", 0), reverse=True)
    benchmark = [("equal_weight", all_metrics["equal_weight"])] if "equal_weight" in all_metrics else []
    sorted_items = dynamic + benchmark
    best = dynamic[0][0] if dynamic else "nav_momentum"

    for i, (criterion, m) in enumerate(sorted_items):
        if criterion == "equal_weight" and i > 0:
            print(f"  {'─'*68}")
        marker = " ◀" if criterion == best else ""
        print(
            f"  {criterion:<18} {m.get('cagr',0):>6.1%} {m.get('sharpe',0):>7.2f}"
            f" {m.get('mdd',0):>6.1%} {m.get('calmar',0):>7.2f}"
            f"  {m.get('final_nav',1):>8.4f}{marker}"
        )

    print(f"\n  {'─'*68}")
    print("  📌 현재 선택 (마지막 리밸런싱):")
    for criterion, m in sorted_items:
        sel_str = ", ".join(m.get("last_selection", [])) or "(없음)"
        print(f"    {criterion:<18}: {sel_str}")

    print(f"\n  📊 전략별 누적 선택 횟수 (best: {best}):")
    cnt = selection_counts.get(best, {})
    for name, count in sorted(cnt.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        print(f"    {name:<20}: {count:>3}회  {bar}")

    print(f"\n  ✅ 권장 선택 기준: {best}")
    print(f"{'═'*72}\n")
    return best


def print_sweep(nav_data: Dict, years: int) -> None:
    """기준 × top_n 1~15 Sharpe 히트맵."""
    n_strategies = len(nav_data)
    max_n = min(15, n_strategies)
    col_w = 6

    print(f"\n{'═'*80}")
    print(f"  top_n 스윕 | 기간={years}년 | 지표=Sharpe  (■=best in row)")
    print(f"{'═'*80}")
    header = f"  {'기준':<18}" + "".join(f"  N={n:<2}" for n in range(1, max_n + 1))
    print(header)
    print(f"  {'─'*76}")

    for criterion in CRITERIA:
        sharpes = []
        for n in range(1, max_n + 1):
            sim, _, _ = simulate(nav_data, criterion, n, years)
            m = compute_metrics(sim)
            sharpes.append(m.get("sharpe", float("nan")))

        best_val = max((s for s in sharpes if not math.isnan(s)), default=0)
        row = f"  {criterion:<18}"
        for s in sharpes:
            if math.isnan(s):
                row += f"{'N/A':>{col_w}}"
            elif abs(s - best_val) < 0.01:
                row += f"\033[1m{s:>{col_w}.2f}\033[0m"  # 굵게
            else:
                row += f"{s:>{col_w}.2f}"
        print(row)
    print(f"{'═'*80}\n")


def print_robust_n(nav_data: Dict, years: int, max_n: int = 10) -> int:
    """다수 기준의 합의 기반 robust top_n 분석 + 전문 퀀트 코멘터리.

    Returns:
        consensus_n: 합의된 권장 top_n
    """
    criteria_to_test = [c for c in CRITERIA if c not in ("equal_weight",)]
    n_strategies = len(nav_data)
    max_n = min(max_n, n_strategies)

    print(f"\n{'═'*72}")
    print(f"  robust top_n 합의 분석 | 기간={years}년 | {len(criteria_to_test)}가지 기준")
    print(f"{'═'*72}")

    # {criterion: {top_n: sharpe}}
    sharpe_table: Dict[str, Dict[int, float]] = {}
    for c in criteria_to_test:
        sharpe_table[c] = {}
        for n in range(1, max_n + 1):
            sim, _, _ = simulate(nav_data, c, n, years)
            m = compute_metrics(sim)
            sharpe_table[c][n] = m.get("sharpe", float("nan"))

    # 각 기준에서 top_n별 순위 계산 (1=최고)
    rank_table: Dict[int, List[int]] = {n: [] for n in range(1, max_n + 1)}
    for c in criteria_to_test:
        sorted_n = sorted(
            range(1, max_n + 1),
            key=lambda n: sharpe_table[c].get(n, float("-inf")),
            reverse=True,
        )
        for rank, n in enumerate(sorted_n, 1):
            rank_table[n].append(rank)

    consensus: Dict[int, float] = {
        n: sum(ranks) / len(ranks) for n, ranks in rank_table.items()
    }
    best_n = min(consensus, key=consensus.get)

    # Sharpe 히트맵 출력
    col_w = 6
    print(f"\n  {'기준':<18}" + "".join(f"  N={n:<2}" for n in range(1, max_n + 1)))
    print(f"  {'─'*70}")
    for c in criteria_to_test:
        best_val = max((v for v in sharpe_table[c].values() if not math.isnan(v)), default=0)
        row = f"  {c:<18}"
        for n in range(1, max_n + 1):
            s = sharpe_table[c].get(n, float("nan"))
            if math.isnan(s):
                row += f"{'N/A':>{col_w}}"
            elif abs(s - best_val) < 0.01:
                row += f"\033[1m{s:>{col_w}.2f}\033[0m"
            else:
                row += f"{s:>{col_w}.2f}"
        print(row)

    # 합의 분석 행
    print(f"  {'─'*70}")
    row = f"  {'[평균순위]':<18}"
    for n in range(1, max_n + 1):
        marker = "★" if n == best_n else " "
        row += f" {consensus[n]:>4.1f}{marker}"
    print(row)

    # top-3 포함 횟수
    row = f"  {'[top3포함횟수]':<18}"
    for n in range(1, max_n + 1):
        cnt = sum(1 for ranks in rank_table[n] if ranks <= 3)
        row += f"{cnt:>{col_w}}"
    print(row)

    print(f"\n  ★ 합의 권장 top_n = {best_n}  (평균순위 {consensus[best_n]:.1f} / {len(criteria_to_test)}개 기준)")

    # 전문 퀀트 코멘터리
    print(f"""
  ─────────────────────────────────────────────────────────────────
  [전문 퀀트 관점 주의사항]

  1. 과적합 경고
     단일 기준 Sharpe 최대화로 선택한 top_n은 샘플 내 과적합.
     5년 백테스트의 Sharpe 차이 ±0.10 이내는 통계적 노이즈로 봐야 함.

  2. 합의 기반 선택의 의미
     평균순위가 낮은 N = 어떤 기준을 써도 '나쁘지 않은' N.
     단일 최적이 아닌 '최악을 피하는' 선택이 실운용에 적합.

  3. 직관적 의미 검증 (필수)
     N=1~2  : 집중 위험 (50~100% 단일 전략)
     N=3~5  : 적당한 분산, 신호 유지
     N=7+   : 신호 희석 → equal_weight와 차별성 없어짐

  4. 100억 운용 권장
     최소 N=3 이상. N=4~5가 집중도와 신호 희석의 균형점.
     상관관계 제약(corr_constrained)과 함께 쓸 때 N은 +1 여유 권장.
  ─────────────────────────────────────────────────────────────────""")
    print(f"{'═'*72}\n")

    return best_n


def print_full_sweep(nav_data: Dict, years: int, top_k: int = 20) -> Tuple[str, int, Optional[float]]:
    """기준 × top_n 1~10 × MDD 임계값 전체 조합 파레토 분석.

    Returns:
        (best_criterion, best_top_n, best_mdd_threshold)
    """
    n_strategies = len(nav_data)
    max_n = min(10, n_strategies)

    print(f"\n{'═'*80}")
    print(f"  전체 조합 분석 | 기간={years}년 | criteria×top_n×mdd_threshold")
    print(f"  기준: {len(CRITERIA)-1}가지 × N=1~{max_n} × MDD={len(MDD_THRESHOLDS)}단계")
    print(f"{'═'*80}")

    all_results = []

    for criterion in CRITERIA:
        if criterion == "equal_weight":
            sim, last_sel, _ = simulate(nav_data, criterion, max_n, years, None)
            m = compute_metrics(sim)
            if m:
                m["last_selection"] = last_sel
                all_results.append({
                    "criterion": criterion,
                    "top_n": "all",
                    "mdd_thr": None,
                    **m,
                })
            continue

        for n in range(1, max_n + 1):
            for mdd_thr in MDD_THRESHOLDS:
                sim, last_sel, _ = simulate(nav_data, criterion, n, years, mdd_thr)
                m = compute_metrics(sim)
                if m:
                    m["last_selection"] = last_sel
                    all_results.append({
                        "criterion": criterion,
                        "top_n": n,
                        "mdd_thr": mdd_thr,
                        **m,
                    })

    if not all_results:
        print("  ❌ 결과 없음")
        return "nav_momentum", 3, None

    # ── Sharpe 기준 상위 K개 ────────────────────────────────────────────────────
    sorted_by_sharpe = sorted(all_results, key=lambda x: x.get("sharpe", 0), reverse=True)

    print(f"\n  📈 Sharpe 상위 {top_k}개 조합")
    print(f"  {'순위':>4}  {'기준':<18} {'N':>3} {'MDD필터':>8}  "
          f"{'CAGR':>7} {'Sharpe':>7} {'MDD':>7} {'Calmar':>7}  마지막선택")
    print(f"  {'─'*100}")

    for rank, row in enumerate(sorted_by_sharpe[:top_k], 1):
        sel_str = ", ".join(row.get("last_selection", [])[:4])
        mdd_str = _mdd_label(row["mdd_thr"])
        n_str = str(row["top_n"])
        print(
            f"  {rank:>4}  {row['criterion']:<18} {n_str:>3} {mdd_str:>8}  "
            f"{row['cagr']:>6.1%} {row['sharpe']:>7.2f} {row['mdd']:>6.1%} "
            f"{row['calmar']:>7.2f}  {sel_str}"
        )

    # ── Calmar 기준 상위 K개 ────────────────────────────────────────────────────
    sorted_by_calmar = sorted(all_results, key=lambda x: x.get("calmar", 0), reverse=True)

    print(f"\n  📉 Calmar 상위 {top_k}개 조합 (MDD 대비 수익)")
    print(f"  {'순위':>4}  {'기준':<18} {'N':>3} {'MDD필터':>8}  "
          f"{'CAGR':>7} {'Sharpe':>7} {'MDD':>7} {'Calmar':>7}  마지막선택")
    print(f"  {'─'*100}")

    for rank, row in enumerate(sorted_by_calmar[:top_k], 1):
        sel_str = ", ".join(row.get("last_selection", [])[:4])
        mdd_str = _mdd_label(row["mdd_thr"])
        n_str = str(row["top_n"])
        print(
            f"  {rank:>4}  {row['criterion']:<18} {n_str:>3} {mdd_str:>8}  "
            f"{row['cagr']:>6.1%} {row['sharpe']:>7.2f} {row['mdd']:>6.1%} "
            f"{row['calmar']:>7.2f}  {sel_str}"
        )

    # ── 파레토 최적 (Sharpe vs CAGR vs MDD 트레이드오프) ─────────────────────
    pareto = _find_pareto_front(all_results)
    print(f"\n  ⭐ 파레토 최적 조합 ({len(pareto)}개, Sharpe↑ & Calmar↑ & MDD↑)")
    print(f"  {'기준':<18} {'N':>3} {'MDD필터':>8}  "
          f"{'CAGR':>7} {'Sharpe':>7} {'MDD':>7} {'Calmar':>7}  마지막선택")
    print(f"  {'─'*100}")

    pareto_sorted = sorted(pareto, key=lambda x: x.get("sharpe", 0), reverse=True)
    for row in pareto_sorted:
        sel_str = ", ".join(row.get("last_selection", [])[:4])
        mdd_str = _mdd_label(row["mdd_thr"])
        n_str = str(row["top_n"])
        print(
            f"  {row['criterion']:<18} {n_str:>3} {mdd_str:>8}  "
            f"{row['cagr']:>6.1%} {row['sharpe']:>7.2f} {row['mdd']:>6.1%} "
            f"{row['calmar']:>7.2f}  {sel_str}"
        )

    print(f"{'═'*80}\n")

    # 최종 권장: Sharpe 1위
    best_row = sorted_by_sharpe[0]
    return best_row["criterion"], best_row["top_n"], best_row["mdd_thr"]


def _find_pareto_front(results: List[Dict]) -> List[Dict]:
    """Sharpe, Calmar, MDD(절댓값 작을수록) 3축 파레토 최적 집합."""
    pareto = []
    for r in results:
        dominated = False
        for other in results:
            if other is r:
                continue
            if (
                other.get("sharpe", 0) >= r.get("sharpe", 0)
                and other.get("calmar", 0) >= r.get("calmar", 0)
                and other.get("mdd", -999) >= r.get("mdd", -999)
                and (
                    other.get("sharpe", 0) > r.get("sharpe", 0)
                    or other.get("calmar", 0) > r.get("calmar", 0)
                    or other.get("mdd", -999) > r.get("mdd", -999)
                )
            ):
                dominated = True
                break
        if not dominated:
            pareto.append(r)
    return pareto


# ── 메인 ──────────────────────────────────────────────────────────────────────

def _generate_portfolio_nav(nav_data: Dict) -> None:
    """현재 config 기준 포트폴리오 NAV를 시뮬레이션 후 data/portfolio_nav.csv에 저장.

    strategy_nav.csv의 전체 기간을 사용하므로 즉시 동작 가능.
    """
    import json as _json

    config_path = Path(__file__).resolve().parent / "config.json"
    criterion = "sharpe_12m"
    top_n = 3
    mdd_threshold = None

    if config_path.exists():
        raw = _json.loads(config_path.read_text(encoding="utf-8"))
        sel = raw.get("selection", {})
        criterion = sel.get("criteria", criterion)
        top_n = int(sel.get("top_n") or top_n)
        mdd_threshold = sel.get("mdd_filter_threshold")

    print(f"포트폴리오 NAV 백필 중: criteria={criterion}, top_n={top_n}, mdd={mdd_threshold}")

    results, last_sel, _ = simulate(nav_data, criterion, top_n, 99, mdd_threshold)
    if not results:
        print("❌ 시뮬레이션 결과 없음")
        return

    portfolio_nav_path = DATA_DIR / "portfolio_nav.csv"
    with open(portfolio_nav_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "nav", "daily_return"])
        prev_nav = results[0][1]
        for i, (date, nav) in enumerate(results):
            dr = (nav / prev_nav - 1.0) if i > 0 and prev_nav > 1e-10 else 0.0
            writer.writerow([date, f"{nav:.6f}", f"{dr:.6f}"])
            prev_nav = nav

    m = compute_metrics(results)
    print(f"✅ portfolio_nav.csv 저장: {len(results)}행, {results[0][0]} ~ {results[-1][0]}")
    print(f"   CAGR={m.get('cagr', 0):.1%}  Sharpe={m.get('sharpe', 0):.2f}  MDD={m.get('mdd', 0):.1%}")
    print(f"   마지막 선택: {', '.join(last_sel)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="전략 선택 기준 백테스트")
    parser.add_argument("--top-n", type=int, default=3, help="선택할 전략 수 (기본 3)")
    parser.add_argument("--years", type=int, default=10, help="백테스트 기간 년수 (기본 10)")
    parser.add_argument("--sweep", action="store_true", help="top_n 1~15 Sharpe 히트맵")
    parser.add_argument("--full", action="store_true",
                        help="전체 조합 파레토 분석 (criteria×top_n×mdd_threshold)")
    parser.add_argument("--auto-apply", action="store_true",
                        help="결과를 확인 없이 자동으로 config.json에 반영")
    parser.add_argument("--robust-n", action="store_true",
                        help="다기준 합의 기반 robust top_n 분석 (과적합 방지)")
    parser.add_argument("--generate-portfolio-nav", action="store_true",
                        help="현재 config 기준으로 portfolio_nav.csv 백필 생성")
    args = parser.parse_args()

    nav_data = load_nav_data()
    if not nav_data:
        print("❌ data/strategy_nav.csv 없음. run_backfill.py를 먼저 실행하세요.")
        return

    print(f"\n전략 수: {len(nav_data)}개  |  전략: {', '.join(sorted(nav_data.keys()))}")
    all_dates = sorted(set(d for s in nav_data.values() for d, _, _ in s))
    if all_dates:
        n_years = (int(all_dates[-1][:4]) - int(all_dates[0][:4])) + 1
        print(f"NAV 기간: {all_dates[0]} ~ {all_dates[-1]}  ({len(all_dates)}거래일, 약 {n_years}년)")

    if args.sweep:
        print_sweep(nav_data, args.years)
        return

    if args.full:
        best_criterion, best_n, best_mdd = print_full_sweep(nav_data, args.years)
        _update_config(best_criterion, best_n, best_mdd, auto_apply=args.auto_apply)
        return

    if args.robust_n:
        print_robust_n(nav_data, args.years)
        return

    if args.generate_portfolio_nav:
        _generate_portfolio_nav(nav_data)
        return

    # 기본 모드: 단일 top_n 비교
    all_metrics: Dict[str, Dict] = {}
    all_counts: Dict[str, Dict] = {}

    for criterion in CRITERIA:
        sim, last_sel, counts = simulate(nav_data, criterion, args.top_n, args.years)
        if not sim:
            continue
        m = compute_metrics(sim)
        m["last_selection"] = last_sel
        all_metrics[criterion] = m
        all_counts[criterion] = counts

    if not all_metrics:
        print("❌ 시뮬레이션 결과 없음.")
        return

    best = print_results(all_metrics, args.top_n, args.years, all_counts)
    _update_config_interactive(best, args.top_n)


def _update_config(criterion: str, top_n, mdd_thr: Optional[float], auto_apply: bool = False) -> None:
    """파레토 최적 설정으로 config.json 업데이트 여부 확인."""
    config_path = Path(__file__).resolve().parent / "config.json"
    if not config_path.exists():
        return

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    current_c = raw.get("selection", {}).get("criteria", "")
    current_n = raw.get("selection", {}).get("top_n", 3)
    current_mdd = raw.get("selection", {}).get("mdd_filter_threshold")

    n_str = str(top_n)
    mdd_str = _mdd_label(mdd_thr)
    print(f"\n  현재 config: criteria='{current_c}', top_n={current_n}, mdd={current_mdd}")
    print(f"  권장 config: criteria='{criterion}', top_n={n_str}, mdd={mdd_str}")

    if current_c == criterion and current_n == top_n and current_mdd == mdd_thr:
        print("  ✅ 이미 최적 설정입니다.")
        return

    if auto_apply:
        apply = True
    else:
        ans = input(f"  config.json을 권장 설정으로 업데이트할까요? [y/N] ").strip().lower()
        apply = (ans == "y")

    if apply:
        raw.setdefault("selection", {})["criteria"] = criterion
        if isinstance(top_n, int):
            raw["selection"]["top_n"] = top_n
        raw["selection"]["mdd_filter_threshold"] = mdd_thr
        config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  ✅ config.json 업데이트 완료")


def _update_config_interactive(best: str, top_n: int) -> None:
    config_path = Path(__file__).resolve().parent / "config.json"
    if not config_path.exists():
        return
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    current = raw.get("selection", {}).get("criteria", "")
    if current == best:
        return
    print(f"  현재 config.json criteria: '{current}'")
    ans = input(f"  config.json을 '{best}'로 업데이트할까요? [y/N] ").strip().lower()
    if ans == "y":
        raw.setdefault("selection", {})["criteria"] = best
        raw["selection"]["top_n"] = top_n
        config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  ✅ config.json 업데이트 완료")


if __name__ == "__main__":
    main()
