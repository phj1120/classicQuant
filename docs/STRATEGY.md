# 전략 상세 설명

## 모멘텀 스코어

전략마다 원논문에 맞는 공식을 사용합니다 (`score_from_returns()` 오버라이드).

| 전략 | 공식 | 근거 |
|------|------|------|
| VAA, DAA, PAA, BAA-G12, BAA-G4, HAA | `(r1m×12) + (r3m×4) + (r6m×2) + r12m` | Keller 복합 공식 |
| GEM | `r12m` (12개월 수익률만) | Antonacci 원논문 |
| FAA, EAA | `(r1m×12 + r3m×4 + r6m×2 + r12m) / 4` (평균) | 복합 랭킹 내 수익률 성분 |
| GTAA, Ivy | 10개월 SMA 시그널 (가격 히스토리 필요) | Faber 원논문 |
| LAA | SPY 200일 SMA + FRED 실업률 (이중 시그널) | Keller 원논문 |
| Permanent, All Weather, Golden Butterfly | 해당 없음 (정적 배분) | — |

룩백 기간: 1개월 = 21 거래일, 3개월 = 63일, 6개월 = 126일, 12개월 = 252일

---

## 메타 전략: 선택 기준 기반 포트폴리오

15개 전략을 매일 paper tracking하고, 선택 기준에 따라 top_n개 전략만 선택합니다.

`run_selection_backtest.py`로 NAV 백테스트를 통해 최적 기준과 top_n을 확인할 수 있습니다.

### 선택 기준 (criteria)

| 기준 | 설명 | 비고 |
|------|------|------|
| `corr_constrained` | sharpe_12m 랭킹 후 상관관계 0.7 이상 전략 제외 | **권장** |
| `sharpe_12m` | 최근 12개월 Sharpe ratio 상위 N개 | — |
| `calmar_12m` | 최근 12개월 CAGR / \|MDD\| 상위 N개 | — |
| `strategy_momentum` | NAV에 Keller 복합 공식 적용, score > 0만 선택 | — |
| `return_1m` | 최근 1개월 NAV 수익률 상위 N개 | — |
| `return_3m` | 최근 3개월 NAV 수익률 상위 N개 | — |
| `return_6m` | 최근 6개월 NAV 수익률 상위 N개 | — |
| `return_12m` | 최근 12개월 NAV 수익률 상위 N개 | — |
| `offensive_mode` | 공격자산 투자 여부 (NAV 데이터 없을 때) | — |

#### corr_constrained 동작 방식

1. 전체 전략을 `sharpe_12m`으로 랭킹
2. 상위부터 순서대로 검토
3. 이미 선택된 전략들과 63일 피어슨 상관관계가 0.7 미만인 경우에만 추가
4. `top_n`개 채워지거나 후보 소진 시 종료

동일 시장국면에 강한 전략끼리 중복 선택되는 집중 위험을 방지합니다.

#### 백테스트로 기준·top_n 확인

```bash
# 기준별 성과 비교 (top_n=4)
python run_selection_backtest.py --top-n 4

# 다기준 합의 기반 robust top_n 분석 (과적합 방지 권장)
python run_selection_backtest.py --robust-n

# top_n 1~15 Sharpe 히트맵
python run_selection_backtest.py --sweep

# 전체 조합 파레토 분석 (criteria × top_n × mdd_threshold)
python run_selection_backtest.py --full
```

`--robust-n`은 단일 기준 최적화의 과적합 위험을 경고하고, 여러 기준에서 일관되게 좋은 top_n을 추천합니다.

### MDD 필터 (전략 레벨)

```json
"mdd_filter_threshold": -0.05
```

고점 대비 -5% 이상 하락한 전략을 선택 대상에서 제외합니다. `null`로 설정하면 비활성화됩니다.

### 포트폴리오 MDD 서킷 브레이커 (포트폴리오 레벨)

```json
"portfolio_mdd_limit": -0.20
```

`data/portfolio_nav_actual.csv` 기준 포트폴리오 전체 낙폭이 이 값 이하로 내려가면:
- 모든 전략 선택 무시
- `fallback_strategy`(기본 permanent)로 강제 전환

**portfolio_nav_model.csv 백필 (최초 1회 권장):**

```bash
python run_selection_backtest.py --generate-portfolio-nav
```

`strategy_nav.csv` 전체 기간을 현재 config 기준으로 시뮬레이션하여 즉시 생성됩니다.
이 파일은 모델 포트폴리오 성과와 설정 검증에 사용됩니다.

실제 운용 NAV는 API 키가 설정된 `run_rebalance.py` 실행에서만
`data/portfolio_nav_actual.csv`와 `data/portfolio_state.csv`에 누적됩니다.

`--report-only`를 API 키 없이 실행하는 offline 모드는
전략 선택과 리포트 검증 전용이며 actual NAV를 갱신하지 않습니다.

### 폴백(Fallback)

서킷 브레이커 발동 또는 유효 전략이 없을 때 `fallback_strategy`(기본 permanent)를 단독 사용합니다.

---

## 구현된 전략 15개

### 모멘텀 기반 (Keller)

| # | 전략 | 저자 | 공격 universe | 수비 | active 조건 |
|---|------|------|---------------|------|-------------|
| 1 | VAA | Keller 2017 | SPY, EFA, EEM, AGG (4개) | LQD, IEF, SHY | 공격자산 4개 모두 ≥ 0 |
| 2 | DAA | Keller 2018 | SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD (12개) | SHY, IEF, LQD | 캐너리(VWO, BND) 모두 ≥ 0 |
| 3 | PAA | Keller 2016 | 12개 (DAA와 동일) | SHY, IEF | 양수 개수 ≥ 6 |
| 4 | BAA-G12 | Keller 2022 | 12개 (DAA와 동일) | SHY, IEF, LQD | 캐너리(SPY, EEM) 모두 ≥ 0 |
| 5 | BAA-G4 | Keller 2022 | SPY, EFA, EEM, AGG (4개) | SHY, IEF, LQD | 캐너리(SPY, EEM) 모두 ≥ 0 |
| 6 | HAA | Keller 2022 | SPY, EFA, EEM, AGG (4개) | LQD, IEF, SHY | 캐너리(SPY, EEM) 모두 ≥ 0 |
| 7 | FAA | Keller 2012 | SPY, EFA, EEM, AGG, DBC, VNQ, SHY (7개) | SHY | 복합 랭킹 상위 3개 |
| 8 | EAA | Keller 2014 | SPY, EFA, EEM, VNQ, DBC, GLD, IEF (7개) | SHY | 탄성 점수 상위 3개 |
| 9 | LAA | Keller 2020 | QQQ, IWD, GLD, IEF (고정) | SHY (조건부) | 항상 active |

### 추세 추종 (Faber)

| # | 전략 | 저자 | universe | 시그널 | active 조건 |
|---|------|------|----------|--------|-------------|
| 10 | GTAA-5 | Faber 2009 | SPY, EFA, VNQ, IEF, DBC | 10개월 SMA | 항상 active |
| 11 | Ivy-5 | Faber 2009 | VTI, EFA, VNQ, IEF, DBC | 10개월 SMA | 항상 active |

### 절대 모멘텀 (Antonacci)

| # | 전략 | 저자 | 공격 universe | 수비 | active 조건 |
|---|------|------|---------------|------|-------------|
| 12 | GEM | Antonacci 2014 | SPY, EFA (2개) | AGG | SPY 또는 EFA의 r12m ≥ 0 |

### 정적 배분

| # | 전략 | 저자 | 고정 배분 | 특징 |
|---|------|------|-----------|------|
| 13 | Permanent | Harry Browne | SPY 25%, TLT 25%, GLD 25%, BIL 25% | 경제 사이클 균형 |
| 14 | All Weather | Ray Dalio | SPY 30%, TLT 40%, IEF 15%, GLD 7.5%, DBC 7.5% | 리스크 패리티 |
| 15 | Golden Butterfly | Tyler | SPY 20%, VBR 20%, TLT 20%, SHY 20%, GLD 20% | Permanent + 소형가치 |

---

## 각 전략 상세

### DAA (Dynamic Asset Allocation) — Keller 2018

- 캐너리(VWO, BND) **모두** ≥ 0 → 공격자산 상위 2개에 50/50 투자
- 하나라도 < 0 → 수비자산 1위에 100% 투자

### VAA (Vigilant Asset Allocation) — Keller 2017

- 공격자산(SPY, EFA, EEM, AGG) **모두** ≥ 0 → 공격자산 1위에 100%
- 하나라도 < 0 → 수비자산 1위에 100%

### PAA (Protective Asset Allocation) — Keller 2016

```
n = 12개 공격자산 중 모멘텀 ≥ 0인 개수
보호 비율 = (12 - n) / 12
```

- 보호 비율만큼 → 수비자산 1위에 투자
- 나머지 → 공격자산 1위에 투자 (예: n=9 → 공격 75%, 수비 25%)

### BAA-G12 / BAA-G4 / HAA — Keller 2022

- 캐너리(SPY, EEM) **모두** ≥ 0 → 공격자산 1위에 100%
- 하나라도 < 0 → 수비자산 1위에 100%
- BAA-G12: 공격 12개, BAA-G4: 공격 4개, HAA: 공격 4개 (캐너리 분리)

### FAA (Flexible Asset Allocation) — Keller 2012

복합 랭킹으로 상위 3개 자산 균등 투자. 절대 모멘텀 음수이면 SHY(현금)로 대체.

```
복합 랭킹 = R_모멘텀×1.0 + R_변동성×0.5 + R_상관관계×0.5   (낮을수록 좋음)
```

### EAA (Elastic Asset Allocation) — Keller 2014

탄성 점수 비례로 상위 3개 자산에 가중 투자. 절대 모멘텀 음수이면 SHY로 대체.

```
탄성 점수 zi = (ri^1.0 × (1-ci)^0.5) / vi^1.0
  ri = 평균 연율화 수익률, vi = 변동성, ci = EWP 상관관계
```

### GTAA-5 (Global Tactical Asset Allocation) — Faber 2009

SPY, EFA, VNQ, IEF, DBC 중 10개월 SMA(210일) 위에 있는 자산에 균등 투자.
SMA 아래 자산 비중은 SHY(현금)로 대체합니다.

### Ivy-5 — Faber 2009

VTI, EFA, VNQ, IEF, DBC에 동일한 SMA 로직 적용. GTAA-5와 동일한 로직이며
자산 구성만 다릅니다 (SPY→VTI).

### GEM (Global Equity Momentum) — Antonacci 2014

1. SPY vs EFA 상대 모멘텀 비교 (12개월 수익률) → 승자 선택
2. 승자의 절대 모멘텀(r12m) > 0 → 승자에 투자
3. 절대 모멘텀 ≤ 0 → AGG(중기 채권)에 투자

### LAA (Lethargic Asset Allocation) — Keller 2020

기본: QQQ 25%, IWD 25%, GLD 25%, IEF 25%

리스크-오프 전환 (두 조건 **모두** 충족 시 QQQ → SHY):
1. SPY < 200일 SMA
2. 실업률(UNRATE) > 12개월 이동평균 (FRED API)

평균 ~3년에 1회 전환하는 낮은 회전율 전략.

---

## 예비자산 동작 방식

`portfolio.py`의 `choose_buy_ticker()` 함수가 담당합니다.

1. 그룹 내 priority 1 티커부터 탐색
2. 예산(budget) >= 해당 티커 현재가이면 선택
3. priority 1이 너무 비싸면 priority 2(예비자산)로 폴백

보유 중인 예비자산의 합산 가치가 주자산 1주 가격 이상이 되면, 예비자산을 매도하고 주자산으로 교체(승격)합니다.

---

## 새 전략 추가하기

1. `app/strategies/{name}/` 디렉터리 생성
2. `__init__.py`에 `BaseStrategy` 상속 + `@register("{name}")` 데코레이터
3. `ASSETS` 클래스 변수에 `Ticker` enum 값으로 자산 그룹 정의
4. `app/strategies/__init__.py` 하단에 import 추가
5. `config.json`의 `strategies` 배열에 추가 (없으면 자동 포함됨)

```python
# app/strategies/my_strategy/__init__.py
from typing import ClassVar, Dict, List, Optional
from app.assets.assets import asset_groups
from app.assets.ticker import Ticker
from app.strategy import BaseStrategy
from app.strategies import register


@register("my_strategy")
class MyStrategy(BaseStrategy):
    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.SPY, Ticker.EFA],
        "defensive": [Ticker.IEF, Ticker.SHY],
    }

    def score_from_returns(self, returns: Dict[str, Optional[float]]) -> Optional[float]:
        """기본은 Keller 복합 공식. 원논문 공식으로 오버라이드 가능."""
        r12 = returns.get("r12m")
        return r12  # 예: 12개월 수익률만 사용

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        # SMA 기반 시그널 → histories 사용
        # 모멘텀 기반 시그널 → scores 사용
        ...

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        ...
```

`Ticker` enum에 없는 티커가 필요하면 `app/assets/ticker.py`에 추가합니다.
각 티커는 `(심볼, 거래소, 설명, 대체티커심볼)` 형식이며, 대체 티커는 주자산이 너무 비쌀 때 자동 폴백됩니다.

```python
# app/assets/ticker.py 예시
MY_ETF = ("MYETF", "NASD", "My ETF Description", "CHEAPER_ALT")
```

### 시그널 유형별 구현 패턴

| 시그널 유형 | 사용 모듈 | 예시 전략 |
|------------|-----------|-----------|
| 모멘텀 점수 | `scores` 딕셔너리 | VAA, DAA, GEM |
| SMA 추세 | `app/indicators/sma.py` + `histories` | GTAA, Ivy, LAA |
| 변동성/상관관계 | `app/indicators/factor.py` + `histories` | FAA, EAA |
| 거시경제 지표 | `app/data/fred_api.py` | LAA |
| 정적 배분 | 고정 비중 딕셔너리 | Permanent, All Weather |

### ASSETS 딕셔너리 구조

```python
ASSETS: ClassVar[Dict] = {
    "offensive": [Ticker.SPY, Ticker.EFA],   # 주자산 (공격)
    "defensive": [Ticker.IEF, Ticker.SHY],   # 수비자산
    "canary":    [Ticker.VWO, Ticker.BND],   # 카나리아 (일부 전략)
    "fixed":     [Ticker.GLD],               # 고정 배분 자산
}
```

- 리스트의 각 원소는 `Ticker` enum 값 (그룹 대표 주자산)
- 그룹 이름은 주자산 심볼과 동일 (`"SPY"`, `"EFA"`, …)
- 대체자산(예비자산)은 `Ticker` enum에서 체인으로 정의됨. `ASSETS`에 별도 기재 불필요
  - 예: `Ticker.TLT` → `.alternative` → `Ticker.EDV` → `.alternative` → `Ticker.SPTL`
- asset type: `offensive` / `defensive` / `canary` / `fixed` / `universe` / `risk_on` / `risk_off` / `trend`

---

## 데이터 파일 구조

| 파일 | 내용 |
|------|------|
| `data/strategy_signals.csv` | date, strategy, mode, selected_assets, top_score |
| `data/strategy_nav.csv` | date, strategy, daily_return, nav |
| `data/portfolio_nav_model.csv` | date, nav, daily_return (모델 포트폴리오 NAV, 연구/설정 검증용) |
| `data/portfolio_nav_actual.csv` | date, nav, daily_return, total_equity (실제 포트폴리오 NAV, 서킷 브레이커용) |
| `data/portfolio_state.csv` | date, total_equity, cash (실제 총자산 스냅샷) |
| `data/momentum.csv` | date, strategy, group, score, r1m, r3m, r6m, r12m |
| `data/holdings.csv` | date, ticker, group, qty, price, value, exchange |
| `data/portfolio.csv` | date, total_equity, cash, strategy, group, target_weight, selected_ticker |
| `data/ohlc_history.csv` | ticker, date, close |
