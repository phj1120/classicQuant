from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from app.constants import US_MARKET_TZ


def _today_label() -> str:
    if ZoneInfo is None:
        return datetime.now().strftime("%Y-%m-%d")
    return datetime.now(ZoneInfo(US_MARKET_TZ)).strftime("%Y-%m-%d")


def write_report(
    strategy_results: List[Dict],
    out_dir: Path,
) -> Path:
    """멀티 전략 리포트를 생성한다.

    strategy_results: [{"name", "weight", "scores", "targets", "selected_tickers"}, ...]
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = _today_label()
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

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
