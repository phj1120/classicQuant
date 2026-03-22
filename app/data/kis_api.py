import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests


class KoreaInvestmentAPI:
    """Minimal KIS API client for DAA."""

    def __init__(self, config: Dict, config_file: Optional[str] = None):
        self.app_key = config["app_key"]
        self.app_secret = config["app_secret"]
        self.account_number = config["account_number"]
        self.account_code = config["account_code"]
        self.base_url = config["base_url"]
        self.exchange_code = config["exchange_code"]

        self.config_file = Path(config_file) if config_file else None
        self.config = config

        self.access_token = None
        self.token_expires_at = 0
        self._load_token_from_config()

    @staticmethod
    def is_daylight_saving_time(dt: datetime) -> bool:
        year = dt.year
        march = datetime(year, 3, 1)
        days_until_sunday = (6 - march.weekday()) % 7
        second_sunday_march = march + timedelta(days=days_until_sunday + 7)

        november = datetime(year, 11, 1)
        days_until_sunday = (6 - november.weekday()) % 7
        first_sunday_november = november + timedelta(days=days_until_sunday)

        return second_sunday_march <= dt < first_sunday_november

    def _load_token_from_config(self) -> None:
        if not self.config_file or not self.config_file.exists():
            return
        try:
            with self.config_file.open("r", encoding="utf-8") as f:
                full_config = json.load(f)
            token_info = full_config.get("token_info", {})
            if token_info:
                self.access_token = token_info.get("access_token")
                self.token_expires_at = token_info.get("expires_at", 0)
                if self.access_token and time.time() < self.token_expires_at:
                    expires_str = datetime.fromtimestamp(self.token_expires_at).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"✅ 저장된 토큰 로드 (만료: {expires_str})")
                else:
                    self.access_token = None
        except Exception as e:
            print(f"⚠️  토큰 로드 실패: {e}")

    def _save_token_to_config(self) -> None:
        if not self.config_file:
            return
        try:
            if self.config_file.exists():
                with self.config_file.open("r", encoding="utf-8") as f:
                    full_config = json.load(f)
            else:
                full_config = {}
            full_config["token_info"] = {
                "access_token": self.access_token,
                "expires_at": self.token_expires_at,
                "issued_at": datetime.now().isoformat(),
            }
            with self.config_file.open("w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2, ensure_ascii=False)
            print("✅ 토큰 저장 완료 (key.json)")
        except Exception as e:
            print(f"⚠️  토큰 저장 실패: {e}")

    def _get_access_token(self) -> str:
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        print("🔑 새로운 접근 토큰 발급 중...")
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        response = requests.post(url, headers=headers, data=json.dumps(body))
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.token_expires_at = time.time() + int(data["expires_in"]) - 300
        print(f"✅ 새 토큰 발급 완료 (유효 기간: {int(data['expires_in'])/3600:.1f}시간)")
        self._save_token_to_config()
        return self.access_token

    def _get_headers(self, tr_id: str, custtype: str = "P") -> Dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": custtype,
        }

    @staticmethod
    def _map_price_exchange(exchange_code: str) -> str:
        excd_map = {
            "NASD": "NAS",
            "NYSE": "NYS",
            "AMEX": "AMS",
            "NAS": "NAS",
            "NYS": "NYS",
            "AMS": "AMS",
        }
        return excd_map.get(exchange_code, exchange_code)

    @staticmethod
    def _map_order_exchange(exchange_code: str) -> str:
        excd_map = {
            "NAS": "NASD",
            "NYS": "NYSE",
            "AMS": "AMEX",
            "NASD": "NASD",
            "NYSE": "NYSE",
            "AMEX": "AMEX",
        }
        return excd_map.get(exchange_code, exchange_code)

    def get_current_price(self, ticker: str) -> Optional[float]:
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/price"
        excd = self._map_price_exchange(self.exchange_code)

        headers = self._get_headers("HHDFS00000300")
        params = {"AUTH": "", "EXCD": excd, "SYMB": ticker}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data["rt_cd"] == "0":
                last_price = data["output"].get("last", "")
                if last_price:
                    return float(last_price)
                print("❌ 현재가 조회 실패: 'last' 필드가 비어있음")
                return None
            print(f"❌ 현재가 조회 실패: {data.get('msg1', 'Unknown error')}")
            return None
        except Exception as e:
            print(f"❌ 현재가 조회 오류: {e}")
            return None

    def buy_stock(self, ticker: str, quantity: int, price: Optional[float] = None) -> bool:
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        headers = self._get_headers("TTTT1002U")

        if price is None:
            current_price = self.get_current_price(ticker)
            if not current_price:
                print("❌ 현재가 조회 실패")
                return False
            ord_unpr = f"{current_price:.2f}"
        else:
            ord_unpr = f"{price:.2f}"

        order_exchange_code = self._map_order_exchange(self.exchange_code)
        body = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "OVRS_EXCG_CD": order_exchange_code,
            "PDNO": ticker,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": ord_unpr,
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response.raise_for_status()
            data = response.json()
            if data.get("rt_cd") == "0":
                print(f"✅ 매수 주문 성공: {ticker} {quantity}주")
                return True
            print(f"❌ 매수 주문 실패: {data.get('msg1', 'Unknown error')}")
            return False
        except Exception as e:
            print(f"❌ 매수 주문 오류: {e}")
            return False

    def sell_stock(self, ticker: str, quantity: int, price: Optional[float] = None) -> bool:
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        headers = self._get_headers("TTTT1006U")

        if price is None:
            current_price = self.get_current_price(ticker)
            if not current_price:
                print("❌ 현재가 조회 실패")
                return False
            ord_unpr = f"{current_price:.2f}"
        else:
            ord_unpr = f"{price:.2f}"

        order_exchange_code = self._map_order_exchange(self.exchange_code)
        body = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "OVRS_EXCG_CD": order_exchange_code,
            "PDNO": ticker,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": ord_unpr,
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "00",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response.raise_for_status()
            data = response.json()
            if data.get("rt_cd") == "0":
                print(f"✅ 매도 주문 성공: {ticker} {quantity}주")
                return True
            print(f"❌ 매도 주문 실패: {data.get('msg1', 'Unknown error')}")
            return False
        except Exception as e:
            print(f"❌ 매도 주문 오류: {e}")
            return False

    def get_balance(self) -> Optional[Dict]:
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = self._get_headers("TTTS3012R")
        params = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "OVRS_EXCG_CD": self.exchange_code,
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data["rt_cd"] == "0":
                stocks = data.get("output1", [])
                if not stocks:
                    print(f"⚠️  잔고 없음 (exchg {self.exchange_code})")
                return {"stocks": stocks, "total": data.get("output2", {})}
            print(f"❌ 잔고 조회 실패: {data.get('msg1', 'Unknown error')}")
            return None
        except Exception as e:
            print(f"❌ 잔고 조회 오류: {e}")
            return None

    def get_account_cash(self) -> Optional[float]:
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
        headers = self._get_headers("TTTS3007R")
        params = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "OVRS_EXCG_CD": "NASD",
            "OVRS_ORD_UNPR": "200",
            "ITEM_CD": "AAPL",
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data["rt_cd"] == "0":
                output = data.get("output", {})
                return float(output.get("ovrs_ord_psbl_amt", "0"))
            print(f"❌ 예수금 조회 실패: {data.get('msg1', 'Unknown error')}")
            return None
        except Exception as e:
            print(f"❌ 예수금 조회 오류: {e}")
            return None

    def get_historical_data(
        self,
        ticker: str,
        period: str = "D",
        min_records: int = 260,
        max_pages: int = 5,
    ) -> Optional[List[Dict]]:
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/dailyprice"
        headers = self._get_headers("HHDFS76240000")
        excd = self._map_price_exchange(self.exchange_code)
        all_rows: List[Dict] = []
        bymd = ""
        pages = 0

        try:
            while len(all_rows) < min_records and pages < max_pages:
                params = {
                    "AUTH": "",
                    "EXCD": excd,
                    "SYMB": ticker,
                    "GUBN": "0",
                    "BYMD": bymd,
                    "MODP": "1",
                }
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                if data.get("rt_cd") != "0":
                    print(f"❌ 과거 데이터 조회 실패: {data.get('msg1', 'Unknown error')}")
                    return None

                output = data.get("output2", [])
                if not isinstance(output, list) or not output:
                    break
                all_rows.extend(output)
                last_date = output[-1].get("xymd")
                if not last_date:
                    break
                bymd_dt = datetime.strptime(last_date, "%Y%m%d") - timedelta(days=1)
                bymd = bymd_dt.strftime("%Y%m%d")
                pages += 1

            return all_rows
        except Exception as e:
            print(f"❌ 과거 데이터 조회 오류: {e}")
            return None

    def get_countries_holiday(self, trad_dt: str) -> Optional[List[Dict]]:
        url = f"{self.base_url}/uapi/overseas-stock/v1/quotations/countries-holiday"
        headers = self._get_headers("CTOS5011R")
        params = {"TRAD_DT": trad_dt, "CTX_AREA_NK": "", "CTX_AREA_FK": ""}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("rt_cd") == "0":
                output = data.get("output", [])
                if isinstance(output, list):
                    return output
                return [output]
            print(f"❌ 해외결제일자조회 실패: {data.get('msg1', 'Unknown error')}")
            return None
        except Exception as e:
            print(f"❌ 해외결제일자조회 오류: {e}")
            return None
