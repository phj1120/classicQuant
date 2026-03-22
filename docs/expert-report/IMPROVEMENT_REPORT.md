# classicQuant 개선 리포트

> 작성일: 2026-03-22
> 퀀트 운용 시스템 전문 코드 리뷰 관점

---

## 총평

코드 품질 자체는 개인 프로젝트 수준을 크게 상회하며, 전략 설계와 선택 로직은 학술적으로도 견고합니다.
다만 **실거래 운용 신뢰성** 측면에서 보완이 필요한 영역이 있습니다.
아래 이슈들은 심각도 기준으로 분류하였습니다.

---

## 심각도 분류 기준

| 등급 | 의미 |
|------|------|
| 🔴 Critical | 실거래 자금 손실 또는 NAV 왜곡 직결 |
| 🟠 High | 운용 중 오작동 가능성, 조기 수정 권장 |
| 🟡 Medium | 백테스트 신뢰성 또는 운용 가시성 저하 |
| 🟢 Low | 코드 품질 / 장기적 유지보수성 |

---

## 1. 🔴 Critical — 실거래 영향 이슈

### C-1. 당일 NAV 계산 시 데이터 순서 문제

**파일:** `run_collect.py`

**현상:** `_calc_strategy_daily_return()`가 오늘의 수익률을 계산하기 위해 `ohlc_history.csv`를 읽는데, 해당 파일은 **새 데이터 저장 이전**에 로드됩니다.

```python
# 현재 구조 (문제)
price_dict = load_ohlc_prices()          # ← 어제까지의 데이터로 로드
daily_return = _calc_daily_return(...)   # ← 오늘 수익률 계산 시도

for ticker, history in all_histories.items():
    save_ohlc_history(ticker, history)   # ← 오늘 데이터는 여기서 저장 (너무 늦음)
```

**영향:** 전략 NAV가 하루씩 지연된 가격으로 계산 → 전략 선택 점수 왜곡 → 잘못된 전략 선택

**수정 방향:** 새 가격 저장 이후 수익률 계산하거나, API에서 받은 가격을 직접 수익률 계산에 사용

---

### C-2. 가격 0 처리 부재로 인한 매수 수량 오류

**파일:** `execution/portfolio.py`

**현상:** `build_group_orders()` 내 매수 수량 계산 시 `price`가 0이거나 잘못된 값일 때 방어 로직 없음.

```python
buy_qty = int(deficit / price)  # price가 0이면 ZeroDivisionError 또는 무한대 수량
```

**영향:** API 오류 또는 가격 캐시 불량 시 비정상 주문 발생 가능

**수정 방향:**
```python
if not price or price <= 0:
    print(f"  ⚠️  {buy_ticker}: 유효하지 않은 가격 → 매수 스킵")
    continue
buy_qty = int(deficit / price)
```

---

### C-3. 서킷브레이커 Fallback 전략 검증 누락

**파일:** `run_rebalance.py`

**현상:** 포트폴리오 MDD -20% 도달 시 `fallback_strategy`로 단독 전환하지만, 해당 전략이 실제로 `strategies` 목록에 존재하는지 검증하지 않음.

```python
fallback_name = selection_cfg.get("fallback_strategy", "permanent")
active_entries = [{"name": fallback_name, "weight": 1.0}]
# ← fallback_name이 typo("permanet")이거나 없는 전략이면 이후 단계에서 KeyError 발생
```

**영향:** 가장 위험한 하락 구간에 시스템 크래시 → 무대응 상태 지속

**수정 방향:**
```python
all_strategy_names = {e["name"] for e in strategy_entries}
if fallback_name not in all_strategy_names:
    raise ValueError(f"fallback_strategy '{fallback_name}'이 전략 목록에 없음")
```

---

## 2. 🟠 High — 운용 중 오작동 위험

### H-1. 변동성/상관계수 계산 시 단일 데이터 포인트 처리 없음

**파일:** `app/indicators/factor.py`

**현상:** `compute_volatility()`에서 수익률 리스트 길이가 1일 때 `len(rets) - 1 = 0`으로 0 나누기 발생 가능.

```python
variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)  # len == 1이면 ZeroDivisionError
```

**영향:** FAA, EAA 전략에서 변동성/상관계수 계산 실패 시 크래시

**수정 방향:** `if len(rets) < 2: return None` 가드 추가

---

### H-2. LAA 전략: FRED API 실패 시 무조건 공격 모드

**파일:** `app/strategies/laa/__init__.py`

**현상:** FRED 실업률 조회 실패 시 예외를 잡고 `return False` (= 위험 없음으로 처리).

```python
except Exception as e:
    print(f"  ⚠️  LAA: FRED 실업률 조회 실패 ({e}), risk-on 유지")
    return False  # ← 네트워크 불안정 시 항상 공격 모드
```

**영향:** 경기 침체 구간에 FRED API가 불안정하면 정확히 그 시점에 방어 전환을 못함

**수정 방향:** 마지막 성공한 결과를 캐시에 저장하고, 실패 시 캐시 값 사용. 캐시도 없으면 보수적으로 `True`(방어) 반환 고려

---

### H-3. GitHub Actions API 재시도 로직 개선 필요

**파일:** `.github/workflows/classicQuant.yml`

**현상:** 실패 시 30초 간격으로 5회 재시도하지만, KIS API 레이트 리밋 도달 시 즉각 재시도가 상황을 악화.

```yaml
# 현재: 고정 30초 대기
sleep 30 && ...
```

**수정 방향:** 지수 백오프 적용 (30s → 60s → 120s → 240s → 480s)

```bash
RETRY_DELAY=30
for attempt in $(seq 1 5); do
    python run_collect.py && break
    sleep $RETRY_DELAY
    RETRY_DELAY=$((RETRY_DELAY * 2))
done
```

---

### H-4. CSV 데이터 중복 저장 시 무음 실패

**파일:** `app/analytics/csv_logger.py`

**현상:** 당일 데이터가 이미 존재하면 `return` 처리하지만, 호출 측에 알리지 않음. 재실행 시 두 번째 실행 데이터가 조용히 무시됨.

**영향:** 수동 재실행 후 데이터가 업데이트되지 않았는데 됐다고 착각

**수정 방향:** `bool` 반환으로 저장 성공 여부 전달, 또는 `dup_date` 로그 출력 추가

---

## 3. 🟡 Medium — 백테스트 신뢰성 / 운용 가시성

### M-1. 백테스트 생존자 편향 (Survivorship Bias)

**파일:** `app/analytics/backtest.py`, `run_backfill.py`

**현상:** 백테스트는 **현재 시점에 존재하는 티커**로 과거를 소급 계산. 일부 ETF는 최근에야 상장되었으나 백테스트상 전체 기간에 존재하는 것으로 간주됨.

| ETF | 상장일 | 영향 |
|-----|--------|------|
| GLDM | 2018-06 | 2018 이전 백테스트에서 GLDM 사용 불가 |
| QQQM | 2020-10 | 2020 이전 백테스트에서 QQQM 사용 불가 |
| SLYV | 2000-11 | 2000 이전 사용 불가 |

**영향:** 역사적 CAGR 0.5~2% 과대평가 가능성

**수정 방향:** 각 Ticker에 `inception_date` 필드 추가, 백테스트 시 해당 날짜 이전에는 상위 티커 사용

---

### M-2. 리밸런싱 지연 미반영 (Look-Ahead Bias)

**파일:** `app/analytics/backtest.py`

**현상:** 월말 가격으로 신호 계산 → 같은 날 즉시 리밸런싱 적용. 실제로는 주문 실행에 1거래일 필요.

**영향:** 백테스트 대비 실거래 수익률 연 0.3~0.8% 낮아질 가능성

**수정 방향:**
```python
# 현재: rebalance_date의 종가로 계산
# 수정: rebalance_date + 1 영업일부터 새 비중 적용
next_date = dates[dates.index(rebalance_date) + 1]  # 다음 영업일부터 적용
```

---

### M-3. 거래비용/세금 미반영

**현재 상태:** 백테스트와 NAV 계산 모두 수수료 0%, 슬리피지 0 가정

**실제 비용 추정:**

| 비용 항목 | 추정치 | 연간 영향 |
|-----------|--------|-----------|
| KIS 해외주식 수수료 | 0.25% / 거래 | 월 리밸런싱 시 연 약 0.5~1.5% |
| 환전 스프레드 | 0.1~0.5% | 환전 빈도에 따라 다름 |
| 매수/매도 스프레드 | ETF별 상이 (SHY ~1bp, DBC ~5bp) | 연 약 0.1~0.3% |
| 양도소득세 22% | 실현 이익의 22% | 운용 전략에 따라 크게 다름 |

**수정 방향:** `config.json`에 `commission_pct`, `tax_rate` 파라미터 추가 후 NAV 계산에 반영

---

### M-4. 과적합 위험 — 파라미터 조합 과다 탐색

**파일:** `run_selection_backtest.py`

**현상:** 8개 기준 × 여러 `top_n` × 여러 MDD 임계값 조합을 같은 데이터로 테스트 → 최적 파라미터가 과거에 과적합될 가능성.

**데이터 대비 자유도 계산:**
- 테스트 기간: 5~7년 (60~84개 월간 관측값)
- 탐색 파라미터 조합: 수십~수백 개
- 유효 자유도가 부족하여 overfitting 위험

**수정 방향:** Walk-Forward Analysis 도입
```
훈련 기간 (In-Sample): 3년
검증 기간 (Out-of-Sample): 1년
→ 윈도우를 앞으로 이동하며 반복
→ Out-of-Sample 성과만 비교
```

---

### M-5. 주문 실행 결과 기록 부재

**파일:** `execution/portfolio.py`

**현상:** 주문 실행 결과(체결가, 체결 수량, 거부 여부)가 CSV에 기록되지 않고 `print()`로만 출력됨.

**영향:**
- 실제 체결가 vs 목표가 검증 불가
- 오류 재현 불가
- 슬리피지 분석 불가

**수정 방향:** `orders_log.csv` 생성
```
date, strategy, ticker, action, target_qty, executed_qty, target_price, executed_price, status, error_msg
```

---

### M-6. 전략 신호 감사 추적(Audit Trail) 부족

**현상:** 왜 특정 전략이 선택/제외되었는지 이력이 reports 폴더의 markdown 파일에만 존재. 구조화된 데이터 없음.

**영향:** 전략 선택 로직 디버깅 시 과거 이력 추적 어려움

**수정 방향:** `selection_log.csv` 추가
```
date, strategy, score, drawdown, mdd_filtered, corr_filtered, selected, weight
```

---

## 4. 🟢 Low — 코드 품질 / 유지보수성

### L-1. API 호출에 타임아웃 없음

**파일:** `app/data/kis_api.py`, `app/data/fred_api.py`

모든 `requests.get/post()` 호출에 `timeout` 파라미터 없음 → 응답 없는 API에 무한 대기 가능

```python
# 수정
response = requests.get(url, headers=headers, timeout=30)
```

---

### L-2. 매직 넘버 분산

여러 파일에 수치가 하드코딩되어 불일치:

| 위치 | 값 | 의미 |
|------|----|------|
| `backtest.py` | `min_records=5040` | 약 20년치 데이터 |
| `momentum.py` | `min_records=260` | 약 1년치 데이터 |
| `strategy_selector.py` | `window: int = 63` | 3개월 상관계수 윈도우 |
| `factor.py` | `_LOOKBACK = 252` | 12개월 수익률 |

**수정 방향:** `app/constants.py`에 집중 관리
```python
TRADING_DAYS_1M  = 21
TRADING_DAYS_3M  = 63
TRADING_DAYS_6M  = 126
TRADING_DAYS_12M = 252
TRADING_DAYS_20Y = 5040
CORR_WINDOW      = 63
```

---

### L-3. config.json 스키마 검증 없음

**파일:** `config.json` 로드 부분

`top_n`, `mdd_filter_threshold` 등 잘못된 타입이나 범위의 값이 들어와도 감지 못함.

**수정 방향:** Pydantic 모델 또는 jsonschema 검증 추가
```python
from pydantic import BaseModel, validator

class SelectionConfig(BaseModel):
    criteria: str
    top_n: int
    mdd_filter_threshold: float

    @validator("top_n")
    def top_n_must_be_positive(cls, v):
        assert 1 <= v <= 15, "top_n은 1~15 범위여야 합니다"
        return v
```

---

### L-4. NAV CSV 컬럼 정의 문서 없음

`strategy_nav.csv`, `portfolio_nav.csv`, `strategy_signals.csv` 등의 컬럼 의미와 단위가 코드 내 주석으로만 파악 가능.

**수정 방향:** `data/SCHEMA.md` 작성
```markdown
## strategy_nav.csv
| 컬럼 | 타입 | 설명 |
|------|------|------|
| date | YYYY-MM-DD | 거래일 |
| strategy | str | 전략 이름 |
| daily_return | float | 당일 수익률 (소수, 수수료 미포함) |
| nav | float | 누적 NAV (시작=1.0) |
```

---

### L-5. 테스트 코드 없음

전략 로직, 모멘텀 계산, 상관계수 필터 등 핵심 로직에 대한 단위 테스트가 전무.

**영향:** 코드 수정 시 회귀 오류 감지 불가

**수정 방향 (최소):**
```python
# tests/test_momentum.py
def test_keller_score():
    r1m, r3m, r6m, r12m = 0.01, 0.03, 0.06, 0.10
    expected = r1m*12 + r3m*4 + r6m*2 + r12m
    assert keller_score(r1m, r3m, r6m, r12m) == expected

# tests/test_vaa_strategy.py
def test_vaa_defensive_when_any_negative():
    scores = {"SPY": 1.0, "EFA": -0.1, "EEM": 0.5, "AGG": 0.3}
    result = vaa.select_targets(scores)
    assert all(k in ["LQD", "IEF", "SHY"] for k in result.keys())
```

---

## 5. 개선 우선순위 로드맵

### Phase 1 — 즉시 수정 (1주 이내)

| 번호 | 이슈 | 예상 공수 |
|------|------|-----------|
| C-1 | 당일 NAV 가격 순서 버그 | 1~2시간 |
| C-2 | 가격 0 체크 추가 | 30분 |
| C-3 | Fallback 전략 검증 | 30분 |
| H-1 | factor.py 단일값 나누기 방어 | 30분 |
| L-1 | API 타임아웃 추가 | 1시간 |

---

### Phase 2 — 단기 보완 (1개월 이내)

| 번호 | 이슈 | 예상 공수 |
|------|------|-----------|
| H-2 | LAA FRED 실패 캐시 처리 | 2~3시간 |
| H-3 | GitHub Actions 지수 백오프 | 1시간 |
| M-5 | 주문 실행 결과 CSV 기록 | 3~4시간 |
| M-6 | 전략 선택 감사 추적 CSV | 2~3시간 |
| H-4 | CSV 중복 저장 반환값 처리 | 1시간 |

---

### Phase 3 — 중기 개선 (3개월 이내)

| 번호 | 이슈 | 예상 공수 |
|------|------|-----------|
| M-1 | ETF 상장일 기반 생존자 편향 제거 | 1~2일 |
| M-2 | 리밸런싱 1일 지연 백테스트 반영 | 4~6시간 |
| M-3 | 거래비용 모델 추가 | 1일 |
| M-4 | Walk-Forward Analysis 구현 | 2~3일 |
| L-3 | config 스키마 검증 | 4~6시간 |

---

### Phase 4 — 장기 고도화 (6개월+)

| 항목 | 설명 |
|------|------|
| 단위 테스트 | 핵심 전략/지표 로직 커버리지 80%+ 목표 |
| 세금 최적화 모듈 | 연간 실현손익 추적, Tax-Loss Harvesting 지원 |
| 성과 귀속 분석 | 전략별 기여도, 자산별 기여도 분리 리포트 |
| 레짐 감지 | 시장 국면(강세/약세/횡보) 자동 분류 후 전략 선택에 반영 |
| 웹 대시보드 | CSV 기반 → 실시간 웹 모니터링 (Streamlit 등) |

---

## 요약 테이블

| 등급 | 건수 | 핵심 내용 |
|------|------|-----------|
| 🔴 Critical | 3건 | NAV 계산 순서, 가격 0 처리, Fallback 검증 |
| 🟠 High | 4건 | factor 나누기, LAA 캐시, Actions 백오프, CSV 중복 |
| 🟡 Medium | 6건 | 생존자 편향, 리밸런싱 지연, 거래비용, 과적합, 주문 로그, 감사 추적 |
| 🟢 Low | 5건 | 타임아웃, 매직넘버, config 검증, 스키마 문서, 테스트 |

---

*이 리포트는 코드 개선 참고용입니다. 이슈 수정 전 충분한 검증(staging 환경) 후 실거래에 적용하시기 바랍니다.*
