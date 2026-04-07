from typing import Dict


def compute_weighted_return(
    targets: Dict[str, float],
    price_dict: Dict[str, Dict[str, float]],
    prev_date: str,
    curr_date: str,
) -> float:
    """그룹별 목표 비중으로 전일 대비 수익률을 계산한다.

    가격이 없는 그룹은 비중을 유지한 채 0% 수익률로 처리한다.
    이 정책은 백테스트와 일별 NAV 수집 양쪽에서 동일하게 사용한다.
    """
    from app.assets.assets import group_tickers

    total_return = 0.0

    for group, weight in targets.items():
        group_return = 0.0
        for ticker in group_tickers(group):
            prev_price = price_dict.get(ticker, {}).get(prev_date)
            curr_price = price_dict.get(ticker, {}).get(curr_date)
            if prev_price and curr_price and prev_price > 0:
                group_return = (curr_price / prev_price) - 1.0
                break
        total_return += weight * group_return

    return total_return
