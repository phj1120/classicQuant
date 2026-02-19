# 전략 상세 설명

## 모멘텀 스코어

모든 전략이 동일한 모멘텀 계산 공식을 사용합니다.

```
모멘텀 스코어 = (1개월 수익률 × 12) + (3개월 수익률 × 4) + (6개월 수익률 × 2) + (12개월 수익률 × 1)
```

룩백 기간: 1개월 = 21 거래일, 3개월 = 63일, 6개월 = 126일, 12개월 = 252일

---

## 메타 전략: 조건 기반 전략 선택

9개 전략을 매일 paper tracking하고, 현재 시장 상황을 기준으로 조건을 만족하는 전략만 선택해 리밸런싱에 사용합니다.
과거 성과 랭킹이 아닌 **현재 신호의 조건 충족 여부**로 판단합니다.

### 선택 기준 (criteria)

#### `strategy_momentum` (기본, 권장)

각 전략의 paper NAV에 동일한 모멘텀 공식 적용:

```
NAV_score = (r1m × 12) + (r3m × 4) + (r6m × 2) + (r12m × 1)
```

- score > 0인 전략만 선택 (또는 `top_n` 설정 시 상위 N개)
- 강세장: 대부분 양수 → 대부분 전략 선택
- 약세장: 음수 전략 탈락 → 자연스러운 리스크 축소
- 초기 워밍업 필요: `run_backfill.py`로 과거 NAV 생성 후 즉시 사용 가능

#### `offensive_mode` (데이터 없을 때)

- 전략이 현재 공격자산에 투자 중이면 active
- NAV 데이터 없이 즉시 사용 가능
- Permanent, All Weather는 항상 active

### mdd_filter (보조 제외 필터)

```json
"mdd_filter_threshold": -0.15
```

고점 대비 -15% 이상 하락한 전략을 제외합니다 (손상 전략 배제).
`null`로 설정하면 비활성화됩니다.

### 폴백(Fallback)

active 전략이 `min_active_strategies`(기본 1개) 미만이면 `fallback_strategy`(기본 permanent)를 사용합니다.

---

## 구현된 전략 9개

| # | 전략 | 저자 | 공격 universe | 수비 | active 조건 |
|---|------|------|---------------|------|-------------|
| 1 | VAA | Keller | SPY, EFA, EEM, AGG (4개) | LQD, IEF, SHY | 공격자산 4개 모두 ≥ 0 |
| 2 | DAA | Keller | SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD (12개) | SHY, IEF, LQD | 캐너리(VWO, BND) 모두 ≥ 0 |
| 3 | PAA | Keller | 12개 (DAA와 동일) | SHY, IEF | 양수 개수 ≥ 6 |
| 4 | BAA-G12 | Keller | 12개 (DAA와 동일) | SHY, IEF, LQD | 캐너리(SPY, EEM) 모두 ≥ 0 |
| 5 | BAA-G4 | Keller | SPY, EFA, EEM, AGG (4개) | SHY, IEF, LQD | 캐너리(SPY, EEM) 모두 ≥ 0 |
| 6 | GEM | Antonacci | SPY, EFA (2개) | AGG | SPY 또는 EFA의 score ≥ 0 |
| 7 | HAA | Keller | SPY, EFA, EEM, AGG (4개) | LQD, IEF, SHY | 캐너리(SPY, EEM) 모두 ≥ 0 |
| 8 | Permanent | Harry Browne | — | — | 항상 active (정적) |
| 9 | All Weather | Ray Dalio | — | — | 항상 active (정적) |

---

## DAA (Dynamic Asset Allocation)

카나리아 자산의 모멘텀 시그널에 따라 공격/수비 모드를 전환하는 전략입니다.

### 룰

- 카나리아 자산(VWO, BND)의 모멘텀 스코어가 **모두 0 이상** → 공격자산 상위 **2개**에 50/50 투자
- 하나라도 0 미만 → 수비자산 상위 **1개**에 100% 투자

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 공격자산 | SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD |
| 수비자산 | SHY, IEF, LQD |
| 카나리아 | VWO, BND |

### 예비자산 매핑

| 그룹 | 주자산 | 예비자산 |
|------|--------|----------|
| SPY  | SPY    | SPYM     |
| IWM  | IWM    | IJR      |
| QQQ  | QQQ    | QQQM     |
| VGK  | VGK    | IEV      |
| EWJ  | EWJ    | HEWJ     |
| EEM  | EEM    | IEMG     |
| VNQ  | VNQ    | SCHH     |
| DBC  | DBC    | PDBC     |
| GLD  | GLD    | GLDM     |
| TLT  | TLT    | EDV      |
| HYG  | HYG    | JNK      |
| LQD  | LQD    | VCIT     |

---

## VAA (Vigilant Asset Allocation)

공격자산 전체의 모멘텀 상태에 따라 투자 모드를 결정합니다. 공격자산이 캐너리 역할을 겸합니다.

### 룰

- 공격자산(SPY, EFA, EEM, AGG) **모두** 0 이상 → 공격자산 1위에 100%
- 하나라도 0 미만 → 수비자산 1위에 100%

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 공격자산 | SPY, EFA, EEM, AGG |
| 수비자산 | LQD, IEF, SHY |

---

## PAA (Protective Asset Allocation)

공격자산 중 모멘텀 양수인 비율에 따라 방어 비중을 동적으로 조정합니다.

### 룰

```
n = 12개 공격자산 중 모멘텀 ≥ 0인 개수
보호 비율 = (12 - n) / 12
```

- 보호 비율만큼 → 수비자산 1위에 투자
- 나머지 → 공격자산 1위에 투자
- 예: n=9 → 공격 75%, 수비 25%

### active 조건

n ≥ 6 (12개 중 절반 이상이 양수)

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 공격자산 | SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD |
| 수비자산 | SHY, IEF |

---

## BAA-G12 (Balanced Asset Allocation, Aggressive 12)

캐너리 2개(SPY, EEM) 기준으로 12개 자산 중 1위에 집중 투자합니다.

### 룰

- 캐너리(SPY, EEM) **모두** ≥ 0 → 12개 공격자산 1위에 100%
- 하나라도 < 0 → 수비자산(SHY/IEF/LQD) 1위에 100%

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 공격자산 | SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD |
| 수비자산 | SHY, IEF, LQD |
| 캐너리 | SPY, EEM (공격 universe 내) |

---

## BAA-G4 (Balanced Asset Allocation, Aggressive 4)

BAA-G12와 동일한 로직이지만 공격 universe가 4개로 더 집중적입니다.

### 룰

- 캐너리(SPY, EEM) **모두** ≥ 0 → 4개 공격자산(SPY/EFA/EEM/AGG) 1위에 100%
- 하나라도 < 0 → 수비자산(SHY/IEF/LQD) 1위에 100%

---

## GEM (Global Equity Momentum)

Gary Antonacci의 상대+절대 모멘텀 결합 전략입니다.

### 룰

1. SPY vs EFA 상대 모멘텀 비교 → 승자 선택
2. 승자의 절대 모멘텀(score) > 0 → 승자에 투자
3. 절대 모멘텀 ≤ 0 → AGG(중기 채권)에 투자

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 비교 대상 | SPY (미국 주식), EFA (선진국 주식) |
| 수비자산 | AGG (중기 채권) |

---

## HAA (Hybrid Asset Allocation)

캐너리 기반 전환에 VAA와 동일한 공격 universe를 사용합니다.

### 룰

- 캐너리(SPY, EEM) **모두** ≥ 0 → 공격자산(SPY/EFA/EEM/AGG) 1위에 100%
- 하나라도 < 0 → 수비자산(LQD/IEF/SHY) 1위에 100%

VAA와 달리 캐너리가 명시적으로 분리되어 있어, 공격자산 자체가 약해도 캐너리가 양수이면 공격 모드를 유지합니다.

---

## Permanent Portfolio (Harry Browne)

경제 사이클 어느 국면에서도 균등 성과를 내도록 설계된 정적 전략입니다.

### 고정 배분

| 자산 | 비중 | 역할 |
|------|------|------|
| SPY  | 25%  | 성장기 |
| TLT  | 25%  | 침체기 (장기채) |
| GLD  | 25%  | 인플레이션기 |
| BIL  | 25%  | 디플레이션기 (단기채) |

항상 active. 선택 기준의 fallback으로 사용됩니다.

---

## All Weather Portfolio (Ray Dalio)

리스크 패리티 개념으로 설계된 정적 전략입니다.

### 고정 배분

| 자산 | 비중 | 역할 |
|------|------|------|
| SPY  | 30%  | 주식 |
| TLT  | 40%  | 장기채 |
| IEF  | 15%  | 중기채 |
| GLD  | 7.5% | 금 |
| DBC  | 7.5% | 원자재 |

항상 active.

---

## 예비자산 동작 방식

`portfolio.py`의 `choose_buy_ticker()` 함수가 담당합니다.

1. 그룹 내 priority 1 티커부터 순서대로 탐색
2. 예산(budget) >= 해당 티커 현재가이면 해당 티커 선택
3. priority 1이 너무 비싸면 priority 2(예비자산)로 폴백
4. 같은 priority 내에서는 가격이 낮은 티커 우선

### 승격 로직

보유 중인 예비자산의 합산 가치가 주자산 1주 가격 이상이 되면, 예비자산을 매도하고 주자산으로 교체(승격)합니다.

---

## 새 전략 추가하기

1. `app/strategies/{name}/` 디렉터리 생성
2. `__init__.py`에 `BaseStrategy`를 상속한 전략 클래스 구현 + `@register("{name}")` 데코레이터 적용
3. `assets.json`에 자산 그룹/티커 정의
4. `app/strategies/__init__.py` 하단에 import 추가
5. `config.json`의 `strategies` 배열에 전략 항목 추가

```python
# app/strategies/my_strategy/__init__.py
from pathlib import Path
from typing import Dict, List, Optional
from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"

@register("my_strategy")
class MyStrategy(BaseStrategy):
    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        return sorted(set(asset_groups("offensive") + asset_groups("defensive")))

    def select_targets(self, scores: Dict[str, Optional[float]]) -> Dict[str, float]:
        # 로직 구현
        ...

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        # offensive_mode 기준용 (선택 사항, 기본 구현 상속 가능)
        ...
```

```json
// config.json
{
  "strategies": [
    { "name": "my_strategy" },
    ...
  ]
}
```

### assets.json 구조

```json
{
  "offensive": {
    "그룹명": [
      { "ticker": "SPY", "exchange_code": "AMEX", "priority": 1 },
      { "ticker": "SPLG", "exchange_code": "AMEX", "priority": 2 }
    ]
  },
  "defensive": { ... },
  "canary": { ... }
}
```

- `그룹명`은 전략 코드에서 사용하는 식별자 (보통 주자산 티커명)
- `priority` 낮을수록 우선 매수. 주자산 부족 시 예비자산으로 폴백

---

## 데이터 파일 구조

| 파일 | 내용 |
|------|------|
| `data/strategy_signals.csv` | date, strategy, mode, selected_assets, top_score |
| `data/strategy_nav.csv` | date, strategy, daily_return, nav |
| `data/momentum.csv` | date, strategy, group, score, r1m, r3m, r6m, r12m |
| `data/holdings.csv` | date, ticker, group, qty, price, value, exchange |
| `data/portfolio.csv` | date, total_equity, cash, strategy, group, target_weight, selected_ticker |
| `data/ohlc_history.csv` | ticker, date, close |
