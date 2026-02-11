from app.assets import exchange_for_ticker
from app.constants import KIS_EXCHANGE_CODE
from app.kis_api import KoreaInvestmentAPI


def set_exchange_for_ticker(api: KoreaInvestmentAPI, ticker: str) -> None:
    api.exchange_code = exchange_for_ticker(ticker)


def set_exchange_default(api: KoreaInvestmentAPI) -> None:
    api.exchange_code = KIS_EXCHANGE_CODE


def set_exchange_for_order(api: KoreaInvestmentAPI, ticker: str, excg: str | None = None) -> None:
    if excg:
        api.exchange_code = excg
        return
    api.exchange_code = KIS_EXCHANGE_CODE
