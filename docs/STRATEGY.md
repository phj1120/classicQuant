# 전략 상세 설명

## 모멘텀 스코어

모든 전략이 동일한 모멘텀 계산 공식을 사용합니다.

```
모멘텀 스코어 = (1개월 수익률 × 12) + (3개월 수익률 × 4) + (6개월 수익률 × 2) + (12개월 수익률 × 1)
```

---

## DAA (Dynamic Asset Allocation)

카나리아 자산의 모멘텀 시그널에 따라 공격/수비 모드를 전환하는 전략입니다.

### 룰

- 카나리아 자산(VWO, BND)의 모멘텀 스코어가 **모두 0 이상** → 공격자산 상위 **2개**에 동일 비중 투자
- 하나라도 0 미만 → 수비자산 상위 **1개**에 100% 투자

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 공격자산 | SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD |
| 수비자산 | SHY, IEF, LQD |
| 카나리아 | VWO, BND |

### 예비자산 매핑

투자 금액이 주자산 1주 가격에 미달하면 저가 대체 ETF(예비자산)를 자동 매수합니다.

| 그룹 | 주자산 (priority 1) | 예비자산 (priority 2) |
|------|---------------------|----------------------|
| SPY  | SPY                 | SPYM                 |
| IWM  | IWM                 | IJR                  |
| QQQ  | QQQ                 | QQQM                 |
| VGK  | VGK                 | IEV                  |
| EWJ  | EWJ                 | HEWJ                 |
| EEM  | EEM                 | IEMG                 |
| VNQ  | VNQ                 | SCHH                 |
| DBC  | DBC                 | PDBC                 |
| GLD  | GLD                 | GLDM                 |
| TLT  | TLT                 | EDV                  |
| HYG  | HYG                 | JNK                  |
| LQD  | LQD                 | VCIT                 |

수비자산(SHY, IEF, LQD)과 카나리아 자산(VWO, BND)은 예비자산 없이 단일 티커로 운용됩니다.

---

## VAA (Vigilant Asset Allocation)

공격자산 전체의 모멘텀 상태에 따라 투자 모드를 결정하는 전략입니다.

### 룰

- 공격자산(SPY, EFA, EEM, AGG) 중 **하나라도** 모멘텀 < 0 → 수비자산 상위 **1개**에 100% 투자
- **모두** 0 이상 → 공격자산 상위 **1개**에 100% 투자

### 자산 유니버스

| 구분 | 자산 |
|------|------|
| 공격자산 | SPY, EFA, EEM, AGG |
| 수비자산 | LQD, IEF, SHY |

### 예비자산 매핑

| 그룹 | 주자산 (priority 1) | 예비자산 (priority 2) |
|------|---------------------|----------------------|
| SPY  | SPY                 | SPLG                 |
| EFA  | EFA                 | VEA                  |
| EEM  | EEM                 | VWO                  |
| AGG  | AGG                 | BND                  |

수비자산(LQD, IEF, SHY)은 예비자산 없이 단일 티커로 운용됩니다.

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
4. `config.json`의 `strategies` 배열에 전략 항목 추가

```json
{
  "strategies": [
    { "name": "daa", "weight": 0.4 },
    { "name": "vaa", "weight": 0.4 },
    { "name": "your_strategy", "weight": 0.2 }
  ]
}
```
