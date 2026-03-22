"""전략에서 사용하는 ETF 티커 정의.

각 티커는 (거래소, 설명, 대체 티커) 속성을 가진다.
대체 티커는 더 저렴한 후순위 ETF로, 단계적 체인을 형성한다.
  예) TLT → EDV → SPTL
"""
from enum import Enum


class Ticker(str, Enum):
    """ETF 티커 열거형.

    str을 상속하므로 Ticker.SPY == "SPY" 가 True이고,
    문자열이 기대되는 모든 곳에서 그대로 사용할 수 있다.
    """

    def __new__(cls, symbol: str, exchange: str, description: str, alternative: str | None = None):
        obj = str.__new__(cls, symbol)
        obj._value_ = symbol
        obj.exchange = exchange
        obj.description = description
        obj._alt = alternative
        return obj

    @property
    def alternative(self) -> "Ticker | None":
        """더 저렴한 대체 티커. 없으면 None."""
        return Ticker(self._alt) if self._alt else None

    # ── 미국 주식 ──────────────────────────────────────────────────────────────
    SPY  = ("SPY",  "AMEX", "S&P 500 ETF (SPDR)",               "SPLG")
    SPLG = ("SPLG", "AMEX", "S&P 500 ETF (SPDR Portfolio)",      None)
    IWM  = ("IWM",  "AMEX", "Russell 2000 소형주 ETF (iShares)", "IJR")
    IJR  = ("IJR",  "AMEX", "S&P 600 소형주 ETF (iShares)",      "SPSM")
    SPSM = ("SPSM", "AMEX", "S&P 600 소형주 ETF (SPDR Portfolio)", None)
    VTI  = ("VTI",  "AMEX", "미국 전체 주식 ETF (Vanguard)",     "SCHB")
    SCHB = ("SCHB", "AMEX", "미국 전체 주식 ETF (Schwab)",       None)
    VBR  = ("VBR",  "AMEX", "미국 소형 가치주 ETF (Vanguard)",   "SLYV")
    SLYV = ("SLYV", "AMEX", "S&P 600 소형 가치주 ETF (SPDR)",   None)
    IWD  = ("IWD",  "AMEX", "Russell 1000 가치주 ETF (iShares)", "VTV")
    VTV  = ("VTV",  "AMEX", "미국 대형 가치주 ETF (Vanguard)",   None)

    # ── 나스닥 ─────────────────────────────────────────────────────────────────
    QQQ  = ("QQQ",  "NASD", "나스닥100 ETF (Invesco)",           "QQQM")
    QQQM = ("QQQM", "NASD", "나스닥100 ETF (Invesco, 소액)",     None)

    # ── 선진국 해외 주식 ───────────────────────────────────────────────────────
    EFA  = ("EFA",  "AMEX", "선진국 주식 ETF (iShares)",         "VEA")
    VEA  = ("VEA",  "AMEX", "선진국 주식 ETF (Vanguard)",        None)
    VGK  = ("VGK",  "AMEX", "유럽 주식 ETF (Vanguard)",          "IEV")
    IEV  = ("IEV",  "AMEX", "유럽 주식 ETF (iShares)",           None)
    EWJ  = ("EWJ",  "AMEX", "일본 주식 ETF (iShares)",           "HEWJ")
    HEWJ = ("HEWJ", "AMEX", "환헤지 일본 주식 ETF (iShares)",    None)

    # ── 이머징마켓 ─────────────────────────────────────────────────────────────
    EEM  = ("EEM",  "AMEX", "이머징마켓 ETF (iShares)",          "IEMG")
    IEMG = ("IEMG", "AMEX", "이머징마켓 ETF (iShares Core)",     None)
    VWO  = ("VWO",  "AMEX", "이머징마켓 ETF (Vanguard)",         None)

    # ── 부동산 ─────────────────────────────────────────────────────────────────
    VNQ  = ("VNQ",  "AMEX", "부동산 ETF (Vanguard)",             "SCHH")
    SCHH = ("SCHH", "AMEX", "부동산 ETF (Schwab)",               None)

    # ── 원자재 ─────────────────────────────────────────────────────────────────
    DBC  = ("DBC",  "AMEX", "원자재 ETF (Invesco)",              "PDBC")
    PDBC = ("PDBC", "NASD", "원자재 ETF (Invesco Optimum Yield)", None)

    # ── 금 ─────────────────────────────────────────────────────────────────────
    GLD  = ("GLD",  "AMEX", "금 ETF (SPDR)",                     "GLDM")
    GLDM = ("GLDM", "AMEX", "금 ETF (SPDR, 소액)",               None)

    # ── 미국 장기채 ────────────────────────────────────────────────────────────
    TLT  = ("TLT",  "NASD", "미국 장기채 ETF (iShares 20+년)",   "EDV")
    EDV  = ("EDV",  "AMEX", "미국 장기채 ETF (Vanguard 확장)",   "SPTL")
    SPTL = ("SPTL", "AMEX", "미국 장기채 ETF (SPDR Portfolio)",  None)

    # ── 미국 중기채 ────────────────────────────────────────────────────────────
    IEF  = ("IEF",  "NASD", "미국 중기채 ETF (iShares 7-10년)",  "SCHR")
    SCHR = ("SCHR", "AMEX", "미국 중기채 ETF (Schwab)",          None)

    # ── 미국 단기채 ────────────────────────────────────────────────────────────
    SHY  = ("SHY",  "NASD", "미국 단기채 ETF (iShares 1-3년)",   "CLTL")
    CLTL = ("CLTL", "AMEX", "미국 단기채 ETF (Invesco)",         None)

    # ── 미국 초단기 국채 ───────────────────────────────────────────────────────
    BIL  = ("BIL",  "AMEX", "미국 초단기 국채 ETF (SPDR 1-3개월)", "SHV")
    SHV  = ("SHV",  "NASD", "미국 초단기 국채 ETF (iShares)",    "SGOV")
    SGOV = ("SGOV", "AMEX", "미국 초단기 국채 ETF (iShares 0-3개월)", None)

    # ── 하이일드 채권 ──────────────────────────────────────────────────────────
    HYG  = ("HYG",  "AMEX", "하이일드 채권 ETF (iShares)",       "JNK")
    JNK  = ("JNK",  "AMEX", "하이일드 채권 ETF (SPDR)",          None)

    # ── 투자등급 회사채 ────────────────────────────────────────────────────────
    LQD  = ("LQD",  "AMEX", "투자등급 회사채 ETF (iShares)",     "VCIT")
    VCIT = ("VCIT", "NASD", "투자등급 회사채 ETF (Vanguard)",    None)

    # ── 미국 채권 종합 ─────────────────────────────────────────────────────────
    AGG  = ("AGG",  "AMEX", "미국 채권 종합 ETF (iShares)",      "BND")
    BND  = ("BND",  "NASD", "미국 채권 종합 ETF (Vanguard)",     None)
