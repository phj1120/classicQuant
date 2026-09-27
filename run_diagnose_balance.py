"""잔고·예수금 raw 응답 덤프 (진단 전용, 매매 없음).

실행: python run_diagnose_balance.py

목적:
2026-07-30~31에 total_equity가 실제 자산의 1/3 수준으로 조회된 원인을 확인한다.
매도 다음날 매도대금이 get_account_cash()의 frcr_dncl_amt1에 잡히지 않는 것으로
추정되나, 어느 필드에 실제로 돈이 있는지는 raw 응답을 봐야 알 수 있다.

확인 항목:
1. inquire-psamount 전체 필드 — 미결제 대금이 담긴 필드 탐색
2. inquire-balance output2(총계) — 평가총액이 종목 합계와 일치하는지
3. 연속조회 키(ctx_area_nk200 / tr_cont) — 잔고가 페이지 단위로 잘리는지
4. 거래소 코드별 잔고 차이 — NASD 단일 조회로 충분한지

계좌번호는 마스킹해서 출력하므로 결과를 그대로 공유해도 된다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from app.config import build_kis_config, load_key
from app.constants import US_EXCHANGE_CODES
from app.data.kis_api import KoreaInvestmentAPI

KEY_PATH = Path(__file__).resolve().parent / "key.json"

# 돈이 어디에 잡히는지 판단할 때 먼저 봐야 하는 필드들.
# ovrs_ord_psbl_amt: 현재 NAV 계산에 쓰는 값(주문가능금액)
# frcr_dncl_amt1: 2026-07-29~ 사용했다가 0으로 조회돼 원복한 값(외화예수금)
# frcr_pchs_amt / ovrs_rlzt_pfls_amt: 미결제 매도대금이 섞여 나올 수 있는 후보
CASH_FIELDS_OF_INTEREST = (
    "frcr_dncl_amt1",
    "frcr_dncl_amt2",
    "ovrs_ord_psbl_amt",
    "frcr_ord_psbl_amt1",
    "nrcvb_buy_amt",
    "ovrs_rlzt_pfls_amt",
    "frcr_pchs_amt",
    "tot_dncl_amt",
    "psbl_amt",
)


def _mask(value: str) -> str:
    if not value or len(value) <= 4:
        return "****"
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _dump(label: str, payload) -> None:
    print(f"\n{'-' * 60}")
    print(f"▶ {label}")
    print(f"{'-' * 60}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def diagnose_cash(api: KoreaInvestmentAPI) -> None:
    """inquire-psamount 전체 응답을 덤프한다."""
    url = f"{api.base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
    params = {
        "CANO": api.account_number,
        "ACNT_PRDT_CD": api.account_code,
        "OVRS_EXCG_CD": "NASD",
        "OVRS_ORD_UNPR": "200",
        "ITEM_CD": "AAPL",
    }
    response = requests.get(url, headers=api._get_headers("TTTS3007R"), params=params, timeout=10)
    data = response.json()

    print(f"\n{'=' * 60}")
    print("1. 예수금 조회 (inquire-psamount / TTTS3007R)")
    print(f"{'=' * 60}")
    print(f"rt_cd={data.get('rt_cd')} msg={data.get('msg1', '')}")

    output = data.get("output", {}) or {}
    _dump("output 전체", output)

    print("\n📌 주요 필드:")
    for field in CASH_FIELDS_OF_INTEREST:
        if field in output:
            print(f"   {field:24s} = {output[field]}")
    unknown = sorted(set(output) - set(CASH_FIELDS_OF_INTEREST))
    if unknown:
        print(f"\n   (그 외 필드: {', '.join(unknown)})")


def diagnose_balance(api: KoreaInvestmentAPI, exchange: str) -> float:
    """inquire-balance 응답을 덤프하고 종목 평가액 합계를 반환한다."""
    url = f"{api.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
    params = {
        "CANO": api.account_number,
        "ACNT_PRDT_CD": api.account_code,
        "OVRS_EXCG_CD": exchange,
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }
    response = requests.get(url, headers=api._get_headers("TTTS3012R"), params=params, timeout=10)
    data = response.json()

    print(f"\n{'=' * 60}")
    print(f"2. 잔고 조회 (inquire-balance / TTTS3012R) — OVRS_EXCG_CD={exchange}")
    print(f"{'=' * 60}")
    print(f"rt_cd={data.get('rt_cd')} msg={data.get('msg1', '')}")

    # 연속조회 여부: tr_cont가 'M'/'F'면 다음 페이지가 남아 있다는 뜻
    tr_cont = response.headers.get("tr_cont", "")
    nk200 = data.get("ctx_area_nk200", "").strip()
    print(f"\n📌 연속조회 판정: tr_cont='{tr_cont}' ctx_area_nk200='{nk200}'")
    if tr_cont in ("M", "F") or nk200:
        print("   ⚠️  다음 페이지가 남아 있음 — 현재 get_balance()는 1페이지만 읽으므로 잔고 누락")
    else:
        print("   ✅ 단일 페이지로 전체 잔고 반환됨")

    stocks = data.get("output1", []) or []
    print(f"\n📌 보유 종목 {len(stocks)}건:")
    total = 0.0
    for row in stocks:
        ticker = row.get("ovrs_pdno", "")
        qty = float(row.get("ovrs_cblc_qty", "0") or "0")
        price = float(row.get("now_pric2", "0") or "0")
        value = qty * price
        total += value
        print(f"   {ticker:6s} qty={qty:>6.0f} price={price:>8.2f} value={value:>9.2f} excg={row.get('ovrs_excg_cd', '')}")
    print(f"   {'합계':6s} {'':>21s} value={total:>9.2f}")

    if stocks:
        _dump("output1[0] 전체 필드", stocks[0])
    _dump("output2 (총계)", data.get("output2", {}))

    return total


def main() -> None:
    if not KEY_PATH.exists():
        print("❌ key.json이 없습니다. key.json.example을 복사해 API 키를 입력하세요.")
        sys.exit(1)

    api = KoreaInvestmentAPI(build_kis_config(load_key(KEY_PATH)), config_file=str(KEY_PATH))
    print(f"계좌: {_mask(api.account_number)}-{api.account_code}")

    diagnose_cash(api)
    nasd_total = diagnose_balance(api, "NASD")

    # NASD 단일 조회로 충분한지 확인 — 거래소별 조회에서 추가 종목이 나오면 누락 증거
    print(f"\n{'=' * 60}")
    print("3. 거래소별 재조회 (NASD 조회 누락 여부 확인)")
    print(f"{'=' * 60}")
    per_exchange_total = 0.0
    for exchange in US_EXCHANGE_CODES:
        if exchange == "NASD":
            continue
        per_exchange_total += diagnose_balance(api, exchange)

    print(f"\n{'=' * 60}")
    print("4. 요약")
    print(f"{'=' * 60}")
    print(f"NASD 단일 조회 평가액      : ${nasd_total:,.2f}")
    print(f"그 외 거래소 합계          : ${per_exchange_total:,.2f}")
    if per_exchange_total > 0.01:
        print("⚠️  NASD 조회만으로는 잔고가 누락됩니다 (get_holdings_all_exchanges 조기 return 문제)")
    else:
        print("✅ NASD 단일 조회로 전체 잔고가 잡힙니다")
    print(
        "\n다음 판단 기준:\n"
        "  - output2 평가총액 > 종목 합계  → 잔고 응답 자체가 일부 누락\n"
        "  - frcr_dncl_amt1 == 0 인데 다른 현금 필드에 잔액 존재 → 미결제 대금 필드 확정\n"
        "  - 모든 현금 필드가 0 → 실제로 계좌에 현금이 없음 (다른 원인 재조사 필요)"
    )


if __name__ == "__main__":
    main()
