# classicQuant

9개 근본 퀀트 전략을 매일 추적하고, 현재 시장 상황에 따라 조건을 만족하는 전략만 선택해 자동 리밸런싱합니다.
GitHub Actions로 운용되며, Fork 후 API 키만 등록하면 바로 사용할 수 있습니다.

> 전략 상세 설명은 [docs/STRATEGY.md](docs/STRATEGY.md)를 참고하세요.

## 동작 방식

```
[최초 1회] run_backfill.py
    전체 자산 과거 가격 수집 (KIS API, 최대 5년)
    → 9개 전략 NAV 곡선 과거분 일괄 생성

[매일] run_collect.py  (GitHub Actions)
    전략 신호 계산 (잔고 조회 없음)
    → data/strategy_signals.csv  (오늘 포지션)
    → data/strategy_nav.csv      (NAV 누적)

[월별] run_rebalance.py  (GitHub Actions)
    strategy_nav.csv 기반 → 조건 충족 전략만 선택
    → active 전략 균등 비중으로 실제 매매 실행
    → 폴백: 아무것도 없으면 Permanent Portfolio
```

## Fork & 시작하기

### 1. 이 저장소를 Fork

우측 상단 **Fork** 버튼을 클릭합니다.

### 2. KIS API 키 발급

[한국투자증권 KIS API 포털](https://apiportal.koreainvestment.com/)에서 앱 키를 발급받습니다.

### 3. GitHub Secret 등록

Fork한 저장소의 **Settings > Secrets and variables > Actions**에서 `KIS_KEY_JSON` Secret을 등록합니다.

```json
{
  "app_key": "YOUR_APP_KEY",
  "app_secret": "YOUR_APP_SECRET",
  "account_number": "YOUR_ACCOUNT_NUMBER",
  "account_code": "YOUR_ACCOUNT_CODE"
}
```

### 4. Workflow 권한 설정

**Settings > Actions > General > Workflow permissions**에서 **Read and write permissions**를 활성화합니다.

### 5. 완료

설정이 끝나면 평일 15:30 UTC (한국시간 00:30)에 자동으로 실행됩니다.
바로 테스트하려면 Actions 탭에서 수동 실행(`Run workflow`)할 수 있습니다.

## 전략 설정 (선택)

기본값으로도 바로 사용 가능합니다.
전략 구성이나 선택 기준을 바꾸고 싶다면 `CONFIG_JSON` Secret을 등록하세요.

**Settings > Secrets and variables > Actions**에서 `CONFIG_JSON` Secret에 원하는 설정을 입력합니다:

```json
{
  "strategies": [
    { "name": "vaa" },
    { "name": "daa" },
    { "name": "paa" },
    { "name": "baa_g12" },
    { "name": "baa_g4" },
    { "name": "gem" },
    { "name": "haa" },
    { "name": "permanent" },
    { "name": "all_weather" }
  ],
  "selection": {
    "criteria": "strategy_momentum",
    "top_n": null,
    "mdd_filter_threshold": -0.15,
    "min_active_strategies": 1,
    "fallback_strategy": "permanent"
  },
  "strategy": {
    "rebalance_threshold_pct": 0.05,
    "cash_buffer_pct": 0.0,
    "min_trade_value_usd": 5.0
  }
}
```

### selection 파라미터

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `criteria` | `"strategy_momentum"` | 선택 기준: `strategy_momentum` 또는 `offensive_mode` |
| `top_n` | `null` | 상위 N개만 선택. `null`이면 양수 전략 전부 |
| `mdd_filter_threshold` | `-0.15` | 이 낙폭 이하인 전략 제외. `null`이면 비활성화 |
| `min_active_strategies` | `1` | 최소 active 전략 수. 부족하면 fallback 사용 |
| `fallback_strategy` | `"permanent"` | 아무것도 선택 안 될 때 사용할 전략 |

### strategy 파라미터

| 항목 | 설명 |
|------|------|
| `rebalance_threshold_pct` | 목표 비중과의 차이가 이 값 이상일 때만 리밸런싱 |
| `cash_buffer_pct` | 현금 보유 비율 (0.0 = 전액 투자) |
| `min_trade_value_usd` | 최소 매매 금액 (USD) |

> Secret이 없으면 저장소의 기본 `config.json`이 사용됩니다.
> Secret으로 관리하면 Sync fork로 소스를 업데이트해도 개인 설정이 유지됩니다.

## GitHub Actions

### 일별 수집 (`classicQuant-collect.yml`) — 예정
- 평일 매일 실행
- 매매 없음, 신호 + NAV만 기록

### 자동 리밸런싱 (`classicQuant.yml`)
- 평일 15:30 UTC (한국시간 00:30) 자동 실행
- 매매 실행 + 리포트 생성 + 데이터 커밋
- 최대 5회 재시도

### 리포트 전용 (`classicQuant-report.yml`)
- Actions 탭 > "ClassicQuant Report Only" > "Run workflow"로 수동 실행
- 매매 없이 모멘텀 분석 리포트만 생성

### 브랜치 구조

`trading` 브랜치는 첫 워크플로우 실행 시 자동 생성됩니다.
매 실행마다 `main`을 리베이스하여 최신 소스를 반영한 뒤, 운용 결과를 커밋합니다.

| 브랜치 | 용도 |
|--------|------|
| `main` | 소스 코드, 설정, 워크플로우 |
| `trading` | `main` + 일별 리포트(`reports/`), CSV 데이터(`data/`) |

```
main:       A ── B ── C (소스 업데이트)
                       \
trading:                C ── report-0211 ── report-0212 ── ...
```

원본 저장소의 소스가 업데이트되면 **Sync fork** → 다음 워크플로우 실행 시 자동 반영됩니다.

## 로컬 실행 (테스트용)

```bash
pip install requests
cp key.json.example key.json   # API 정보 입력
```

```bash
# 최초 1회: 과거 NAV 데이터 생성 (strategy_momentum 기준 사용 시 필요)
python run_backfill.py

# 매일: 신호 + NAV 수집 (매매 없음)
python run_collect.py

# 리포트만 생성 (매매 없이 전략 선택 결과 확인)
python run_rebalance.py --report-only

# 리밸런싱 실행 (실제 매매 발생)
python run_rebalance.py
```

> `key.json`은 `.gitignore`에 포함되어 있어 커밋되지 않습니다.

## 프로젝트 구조

```
classicQuant/
├── app/
│   ├── strategies/
│   │   ├── vaa/          # VAA 전략 + assets.json
│   │   ├── daa/          # DAA 전략 + assets.json
│   │   ├── paa/          # PAA 전략 + assets.json
│   │   ├── baa_g12/      # BAA-G12 전략 + assets.json
│   │   ├── baa_g4/       # BAA-G4 전략 + assets.json
│   │   ├── gem/          # GEM 전략 + assets.json
│   │   ├── haa/          # HAA 전략 + assets.json
│   │   ├── permanent/    # Permanent Portfolio + assets.json
│   │   └── all_weather/  # All Weather Portfolio + assets.json
│   ├── strategy.py        # BaseStrategy 추상 클래스
│   ├── strategy_selector.py  # 전략 선택 로직
│   ├── backtest.py        # NAV 백테스트 (과거 시뮬레이션)
│   ├── config.py          # 설정 로드
│   ├── csv_logger.py      # CSV 데이터 로깅
│   ├── kis_api.py         # KIS API 클라이언트
│   ├── momentum.py        # 모멘텀 스코어 계산
│   ├── portfolio.py       # 포트폴리오 주문 생성/실행
│   └── report.py          # 리포트 생성
├── data/                  # CSV 출력 (trading 브랜치에서 관리)
│   ├── strategy_signals.csv   # 일별 전략 신호
│   ├── strategy_nav.csv       # 전략별 NAV 누적
│   ├── momentum.csv           # 자산별 모멘텀 스코어
│   ├── holdings.csv           # 보유 현황
│   └── ohlc_history.csv       # 자산 가격 히스토리
├── docs/
│   └── STRATEGY.md        # 전략 상세 설명
├── config.json            # 전략/선택 설정
├── key.json.example       # API 키 템플릿
├── run_rebalance.py       # 리밸런싱 엔트리포인트
├── run_collect.py         # 일별 수집 엔트리포인트
└── run_backfill.py        # 과거 데이터 백필 엔트리포인트
```

## 주의사항

- **실거래 주문이 발생합니다.** 충분히 검증 후 실행하세요.
- 처음 사용 시 `--report-only` 또는 리포트 전용 워크플로우로 먼저 확인하는 것을 권장합니다.
- `strategy_momentum` 기준 사용 시 `run_backfill.py`를 먼저 실행해야 NAV 데이터가 생성됩니다.
- 새 전략 추가 방법은 [docs/STRATEGY.md](docs/STRATEGY.md#새-전략-추가하기)를 참고하세요.
