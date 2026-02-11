import math
from typing import Dict, List

from app.constants import (
    DEFAULT_CASH_BUFFER_PCT,
    DEFAULT_MIN_TRADE_VALUE_USD,
    US_EXCHANGE_CODES,
)
from app.assets import exchange_for_ticker as asset_exchange
from app.data_utils import extract_qty, extract_ticker
from app.exchange import set_exchange_for_order, set_exchange_for_ticker
from app.assets import all_groups as known_asset_groups
from app.groups import group_for_ticker, group_tier_index, group_tiers
from app.kis_api import KoreaInvestmentAPI


def parse_holdings(balance: Dict) -> Dict[str, int]:
    holdings: Dict[str, int] = {}
    for row in balance.get("stocks", []) if balance else []:
        ticker = extract_ticker(row)
        qty = extract_qty(row)
        if ticker and qty > 0:
            holdings[ticker] = qty
    return holdings


def parse_holdings_detail(balance: Dict) -> Dict[str, Dict]:
    holdings: Dict[str, Dict] = {}
    for row in balance.get("stocks", []) if balance else []:
        ticker = extract_ticker(row)
        qty = extract_qty(row)
        if not ticker or qty <= 0:
            continue
        price = None
        try:
            price = float(row.get("now_pric2")) if row.get("now_pric2") else None
        except (TypeError, ValueError):
            price = None
        excg = row.get("ovrs_excg_cd")
        holdings[ticker] = {
            "qty": qty,
            "price": price,
            "excg": excg,
        }
    return holdings


def get_holdings_all_exchanges(api: KoreaInvestmentAPI) -> Dict[str, Dict]:
    holdings: Dict[str, Dict] = {}
    # 실전 계좌는 NASD(미국전체)로 잔고가 반환되는 경우가 많음
    api.exchange_code = "NASD"
    balance = api.get_balance()
    for ticker, info in parse_holdings_detail(balance).items():
        current = holdings.get(ticker, {"qty": 0, "price": None, "excg": None})
        current["qty"] += info["qty"]
        current["price"] = info["price"] or current["price"]
        current["excg"] = info["excg"] or current["excg"]
        holdings[ticker] = current
    if holdings:
        return holdings

    # NASD에서 비어있으면 거래소별로 재조회 (모의계좌/특이 케이스 대응)
    for exc in US_EXCHANGE_CODES:
        api.exchange_code = exc
        balance = api.get_balance()
        for ticker, info in parse_holdings_detail(balance).items():
            current = holdings.get(ticker, {"qty": 0, "price": None, "excg": None})
            current["qty"] += info["qty"]
            current["price"] = info["price"] or current["price"]
            current["excg"] = info["excg"] or current["excg"]
            holdings[ticker] = current
    return holdings


def get_prices(api: KoreaInvestmentAPI, tickers: List[str]) -> Dict[str, float]:
    prices: Dict[str, float] = {}
    for ticker in tickers:
        set_exchange_for_ticker(api, ticker)
        price = api.get_current_price(ticker)
        if price is None:
            raise RuntimeError(f"현재가 조회 실패: {ticker}")
        prices[ticker] = price
    return prices


def choose_buy_ticker(group: str, prices: Dict[str, float], budget: float) -> str | None:
    for tier in group_tiers(group):
        tier_candidates = [t for t in tier if prices.get(t) is not None]
        tier_candidates.sort(key=lambda t: prices[t])
        for ticker in tier_candidates:
            price = prices[ticker]
            if budget >= price:
                return ticker
    return None


def build_group_orders(
    holdings_detail: Dict[str, Dict],
    targets: Dict[str, float],
    prices: Dict[str, float],
    total_equity: float,
    cash_buffer_pct: float = DEFAULT_CASH_BUFFER_PCT,
    min_trade_value_usd: float = DEFAULT_MIN_TRADE_VALUE_USD,
    rebalance_threshold_pct: float = 0.0,
) -> tuple[list[Dict], Dict[str, str]]:
    investable = total_equity * (1.0 - cash_buffer_pct)
    threshold_value = investable * rebalance_threshold_pct
    orders: List[Dict] = []
    planned_sells: Dict[str, int] = {}

    group_holdings: Dict[str, Dict[str, Dict]] = {}
    for ticker, info in holdings_detail.items():
        group = group_for_ticker(ticker)
        group_holdings.setdefault(group, {})[ticker] = info

    selected_tickers: Dict[str, str] = {}

    def remaining_qty(ticker: str, info: Dict) -> int:
        return max(0, info["qty"] - planned_sells.get(ticker, 0))

    def add_sell_order(ticker: str, qty: int, price: float) -> float:
        if qty <= 0:
            return 0.0
        trade_value = qty * price
        if trade_value < min_trade_value_usd:
            return 0.0
        orders.append({
            "ticker": ticker,
            "side": "sell",
            "quantity": qty,
            "est_value": trade_value,
            "price": price,
        })
        planned_sells[ticker] = planned_sells.get(ticker, 0) + qty
        return trade_value

    known = set(known_asset_groups())
    all_groups = (set(group_holdings.keys()) & known) | set(targets.keys())
    for group in sorted(all_groups):
        target_value = investable * targets.get(group, 0.0)

        tickers = group_holdings.get(group, {})
        current_value = 0.0
        for ticker, info in tickers.items():
            price = prices.get(ticker) or info.get("price")
            if price:
                current_value += price * info["qty"]

        diff = abs(current_value - target_value)
        if diff < threshold_value:
            continue

        if current_value > target_value + 1e-6:
            excess = current_value - target_value
            sorted_tickers = sorted(
                tickers.items(),
                key=lambda item: (
                    group_tier_index(item[0]),
                    (prices.get(item[0]) or item[1].get("price") or 0.0) * item[1]["qty"],
                ),
                reverse=True,
            )
            for ticker, info in sorted_tickers:
                price = prices.get(ticker) or info.get("price")
                if not price:
                    continue
                max_value = price * info["qty"]
                sell_value = min(excess, max_value)
                sell_qty = min(info["qty"], max(1, math.ceil(sell_value / price)))
                trade_value = sell_qty * price
                trade_value = add_sell_order(ticker, sell_qty, price)
                excess -= trade_value
                if excess <= 0:
                    break

        remaining_value = 0.0
        for ticker, info in tickers.items():
            price = prices.get(ticker) or info.get("price")
            if not price:
                continue
            remaining_value += price * remaining_qty(ticker, info)

        if remaining_value + min_trade_value_usd < target_value:
            deficit = target_value - remaining_value
            buy_ticker = choose_buy_ticker(group, prices, deficit)
            if buy_ticker:
                price = prices[buy_ticker]
                buy_qty = int(deficit / price)
                trade_value = buy_qty * price
                if buy_qty > 0 and trade_value >= min_trade_value_usd:
                    orders.append({
                        "ticker": buy_ticker,
                        "side": "buy",
                        "quantity": buy_qty,
                        "est_value": trade_value,
                        "price": price,
                        "exchange_code": asset_exchange(buy_ticker),
                    })
                    selected_tickers[group] = buy_ticker

        preferred = choose_buy_ticker(group, prices, target_value)
        if preferred:
            preferred_priority = group_tier_index(preferred)
            lower_holdings = []
            for ticker, info in tickers.items():
                if ticker == preferred:
                    continue
                if group_tier_index(ticker) <= preferred_priority:
                    continue
                qty = remaining_qty(ticker, info)
                if qty <= 0:
                    continue
                price = prices.get(ticker) or info.get("price")
                if not price:
                    continue
                lower_holdings.append((ticker, qty, price))

            if lower_holdings:
                lower_holdings.sort(
                    key=lambda item: (group_tier_index(item[0]), item[1] * item[2]),
                    reverse=True,
                )
                available_value = sum(qty * price for _, qty, price in lower_holdings)
                preferred_price = prices.get(preferred)
                if preferred_price and available_value >= preferred_price:
                    sell_value = 0.0
                    for ticker, qty, price in lower_holdings:
                        if sell_value >= available_value:
                            break
                        trade_value = add_sell_order(ticker, qty, price)
                        sell_value += trade_value
                    buy_qty = int(sell_value / preferred_price)
                    trade_value = buy_qty * preferred_price
                    if buy_qty > 0 and trade_value >= min_trade_value_usd:
                        orders.append({
                            "ticker": preferred,
                            "side": "buy",
                            "quantity": buy_qty,
                            "est_value": trade_value,
                            "price": preferred_price,
                            "exchange_code": asset_exchange(preferred),
                        })
                        selected_tickers[group] = preferred

    return orders, selected_tickers


def execute_orders(api: KoreaInvestmentAPI, orders: List[Dict], holdings_detail: Dict[str, Dict]) -> None:
    if not orders:
        print("✅ 리밸런싱 필요 없음")
        return

    sells = [o for o in orders if o["side"] == "sell"]
    buys = [o for o in orders if o["side"] == "buy"]

    print("\n📌 매도 주문")
    for order in sells:
        print(f"- {order['ticker']} {order['quantity']}주 (추정 ${order['est_value']:.2f})")
        info = holdings_detail.get(order["ticker"], {})
        set_exchange_for_order(api, order["ticker"], info.get("excg"))
        api.sell_stock(order["ticker"], order["quantity"], price=order.get("price"))

    print("\n📌 매수 주문")
    for order in buys:
        print(f"- {order['ticker']} {order['quantity']}주 (추정 ${order['est_value']:.2f})")
        set_exchange_for_order(api, order["ticker"], order.get("exchange_code"))
        api.buy_stock(order["ticker"], order["quantity"], price=order.get("price"))
