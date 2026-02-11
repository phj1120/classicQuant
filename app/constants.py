KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_EXCHANGE_CODE = "NASD"
US_EXCHANGE_CODES = ["NASD", "NYSE", "AMEX", "NAS"]

US_MARKET_TZ = "America/New_York"
US_MARKET_OPEN_HOUR = 9
US_MARKET_OPEN_MINUTE = 30

DEFAULT_EXECUTION_OFFSET_MINUTES = 120
DEFAULT_EXECUTION_WINDOW_MINUTES = 5
DEFAULT_CHECK_HOLIDAY = True

DEFAULT_MIN_TRADE_VALUE_USD = 5.0
DEFAULT_CASH_BUFFER_PCT = 0.0

US_MARKET_COUNTRY_CODES = {"USA", "US"}
US_MARKET_EXCHANGE_CODES = {"NAS", "NYS", "NASD", "NYSE"}

LOOKBACK_DAYS = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

PRICE_KEYS = [
    "clos", "close", "last", "stck_clpr", "tdd_clpr",
    "ovrs_stck_clpr", "stck_prpr", "ccld_prc",
]
DATE_KEYS = ["xymd", "date", "stck_bsop_date", "bas_dt"]
TICKER_KEYS = ["ovrs_pdno", "pdno", "ovrs_item_cd", "item_cd", "symbol"]
QTY_KEYS = ["hldg_qty", "qty", "ovrs_qty", "quantity", "hold_qty", "ovrs_cblc_qty"]
