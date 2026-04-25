from pathlib import Path
from typing import Dict, List, Optional

from app.time_utils import trading_date_label


def _build_risk_section(strategy_results: List[Dict], window: int = 252) -> List[str]:
    """선택된 전략들의 가중 평균 daily_return으로 리스크 지표를 계산한다.

    데이터가 없거나 오류 발생 시 빈 리스트를 반환한다.
    """
    try:
        from app.analytics.csv_logger import load_strategy_nav
        from app.analytics.risk import historical_var, cvar, max_drawdown, annualized_sharpe

        nav_data = load_strategy_nav()
        if not nav_data:
            return []

        # 각 전략의 날짜별 daily_return 수집
        strategy_returns: Dict[str, Dict[str, float]] = {}
        for result in strategy_results:
            name = result["name"]
            weight = result["weight"]
            rows = nav_data.get(name, [])
            if not rows:
                continue
            for row in rows:
                date = row.get("date", "")
                try:
                    dr = float(row.get("daily_return", 0) or 0)
                except (ValueError, TypeError):
                    continue
                strategy_returns.setdefault(date, {})[name] = (dr, weight)

        if not strategy_returns:
            return []

        # 모든 전략에 공통으로 존재하는 날짜만 사용
        strategy_names = [r["name"] for r in strategy_results]
        all_dates = sorted(
            date for date, by_name in strategy_returns.items()
            if all(name in by_name for name in strategy_names)
        )

        if not all_dates:
            return []

        # 최근 window 거래일
        recent_dates = all_dates[-window:]

        # 가중 평균 combined return 시계열
        combined: List[float] = []
        for date in recent_dates:
            by_name = strategy_returns[date]
            weighted_sum = sum(dr * w for dr, w in by_name.values())
            combined.append(weighted_sum)

        if not combined:
            return []

        var_val = historical_var(combined, 0.95)
        cvar_val = cvar(combined, 0.95)
        mdd_val = max_drawdown(combined)
        sharpe_val = annualized_sharpe(combined)

        actual_days = len(combined)
        lines = [
            "",
            f"## 리스크 지표 (최근 {actual_days}거래일)",
            f"- 1-day 95% VaR: {var_val * 100:.2f}%",
            f"- 1-day 95% CVaR: {cvar_val * 100:.2f}%",
            f"- MDD: {mdd_val * 100:.2f}%",
            f"- Sharpe: {sharpe_val:.2f}",
        ]
        return lines

    except Exception:
        return []


def write_report(
    strategy_results: List[Dict],
    out_dir: Path,
) -> Path:
    """멀티 전략 리포트를 생성한다.

    strategy_results: [{"name", "weight", "scores", "targets", "selected_tickers"}, ...]
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = trading_date_label()
    path = out_dir / f"{date_str}.md"

    names = " + ".join(
        f"{r['name'].upper()}({r['weight']*100:.0f}%)" for r in strategy_results
    )
    lines = [f"# {names} Daily Report ({date_str})"]

    for result in strategy_results:
        name = result["name"].upper()
        weight = result["weight"]
        scores = result["scores"]
        targets = result["targets"]
        selected_tickers = result["selected_tickers"]

        lines.extend(["", f"## {name} (비중 {weight*100:.0f}%)", ""])
        lines.append("### Momentum Scores")
        for ticker in sorted(scores.keys()):
            score = scores[ticker]
            score_display = f"{score:.4f}" if score is not None else "N/A"
            lines.append(f"- {ticker}: {score_display}")

        lines.extend(["", "### Portfolio"])
        for group, w in targets.items():
            actual = selected_tickers.get(group, group)
            if actual != group:
                lines.append(f"- {group} ({actual}): {w * 100:.1f}%")
            else:
                lines.append(f"- {group}: {w * 100:.1f}%")

    lines.extend(_build_risk_section(strategy_results))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
