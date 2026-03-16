# classicQuant

15개 근본 퀀트 전략을 매일 추적하고, 상관관계 기반 분산 선택으로 최적 전략 조합에 자동 리밸런싱합니다.
GitHub Actions로 운용되며, Fork 후 API 키만 등록하면 바로 사용할 수 있습니다.

> 전략 상세 설명은 [docs/STRATEGY.md](docs/STRATEGY.md)를 참고하세요.

## 동작 방식

```
[최초 1회] run_backfill.py
    전체 자산 과거 가격 수집 (KIS API, 최대 5년)
    → 15개 전략 NAV 곡선 과거분 일괄 생성

[최초 1회] run_selection_backtest.py --generate-portfolio-nav
    strategy_nav.csv 기반으로 포트폴리오 NAV 백필
    → data/portfolio_nav.csv 생성 (MDD 서킷 브레이커에 사용)

[매일] run_collect.py  (GitHub Actions)
    전략 신호 계산 (잔고 조회 없음)
    → data/strategy_signals.csv  (오늘 포지션)
    → data/strategy_nav.csv      (NAV 누적)

[월별] run_rebalance.py  (GitHub Actions)
    1. portfolio_nav.csv 기반 포트폴리오 MDD 서킷 브레이커 체크
    2. strategy_nav.csv 기반 → corr_constrained 기준으로 top 4 전략 선택
       (sharpe_12m 랭킹 + 상관관계 0.7 이상 전략 제외)
    3. active 전략 균등 비중으로 실제 매매 실행
    4. 폴백: 서킷 브레이커 발동 또는 선택 실패 시 Permanent Portfolio
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
    { "name": "all_weather" },
    { "name": "golden_butterfly" },
    { "name": "gtaa" },
    { "name": "ivy" },
    { "name": "faa" },
    { "name": "eaa" },
    { "name": "laa" }
  ],
  "selection": {
    "criteria": "corr_constrained",
    "top_n": 4,
    "mdd_filter_threshold": -0.05,
    "fallback_strategy": "permanent",
    "portfolio_mdd_limit": -0.20
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
| `criteria` | `"corr_constrained"` | 선택 기준 (아래 표 참고) |
| `top_n` | `4` | 상위 N개 전략 선택 |
| `mdd_filter_threshold` | `-0.05` | 전략 레벨: 이 낙폭 이하인 전략 제외. `null`이면 비활성화 |
| `fallback_strategy` | `"permanent"` | 아무것도 선택 안 될 때 사용할 전략 |
| `portfolio_mdd_limit` | `-0.20` | 포트폴리오 레벨: 이 낙폭 이하이면 서킷 브레이커 발동. `null`이면 비활성화 |

#### criteria 옵션

| 값 | 설명 |
|----|------|
| `corr_constrained` | sharpe_12m 랭킹 후 상관관계 0.7 이상 전략 제외 (권장) |
| `sharpe_12m` | 최근 12개월 Sharpe ratio 상위 N개 |
| `calmar_12m` | 최근 12개월 CAGR / \|MDD\| 상위 N개 |
| `strategy_momentum` | NAV에 Keller 복합 공식 적용 |
| `return_1m` / `return_3m` / `return_6m` / `return_12m` | 기간별 NAV 수익률 |
| `offensive_mode` | 공격자산 투자 여부 (NAV 데이터 없을 때) |

### strategy 파라미터

| 항목 | 설명 |
|------|------|
| `rebalance_threshold_pct` | 목표 비중과의 차이가 이 값 이상일 때만 리밸런싱 |
| `cash_buffer_pct` | 현금 보유 비율 (0.0 = 전액 투자) |
| `min_trade_value_usd` | 최소 매매 금액 (USD) |

> Secret이 없으면 저장소의 기본 `config.json`이 사용됩니다.
> Secret으로 관리하면 Sync fork로 소스를 업데이트해도 개인 설정이 유지됩니다.

## GitHub Actions

### 일별 수집 (`classicQuant-collect.yml`)
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
# 최초 1회: 과거 NAV 데이터 생성
python run_backfill.py

# 최초 1회: 포트폴리오 NAV 백필 (MDD 서킷 브레이커용)
python run_selection_backtest.py --generate-portfolio-nav

# 선택 기준 백테스트 비교 (top_n=4 기준)
python run_selection_backtest.py --top-n 4

# top_n 최적값 합의 분석 (과적합 방지)
python run_selection_backtest.py --robust-n

# 전체 조합 파레토 분석 (criteria × top_n × mdd_threshold)
python run_selection_backtest.py --full

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
│   │   ├── vaa/              # VAA 전략 + assets.json
│   │   ├── daa/              # DAA 전략 + assets.json
│   │   ├── paa/              # PAA 전략 + assets.json
│   │   ├── baa_g12/          # BAA-G12 전략 + assets.json
│   │   ├── baa_g4/           # BAA-G4 전략 + assets.json
│   │   ├── gem/              # GEM 전략 + assets.json
│   │   ├── haa/              # HAA 전략 + assets.json
│   │   ├── permanent/        # Permanent Portfolio + assets.json
│   │   ├── all_weather/      # All Weather Portfolio + assets.json
│   │   ├── golden_butterfly/ # Golden Butterfly + assets.json
│   │   ├── gtaa/             # GTAA-5 전략 + assets.json
│   │   ├── ivy/              # Ivy-5 전략 + assets.json
│   │   ├── faa/              # FAA 전략 + assets.json
│   │   ├── eaa/              # EAA 전략 + assets.json
│   │   └── laa/              # LAA 전략 + assets.json
│   ├── strategy.py           # BaseStrategy 추상 클래스
│   ├── strategy_selector.py  # 전략 선택 로직 (corr_constrained 포함)
│   ├── backtest.py           # NAV 백테스트 (과거 시뮬레이션)
│   ├── config.py             # 설정 로드
│   ├── csv_logger.py         # CSV 데이터 로깅 (portfolio_nav 포함)
│   ├── factor.py             # 변동성/상관관계 계산 (FAA, EAA용)
│   ├── fred_api.py           # FRED 실업률 데이터 연동 (LAA용)
│   ├── sma.py                # SMA 계산 유틸리티 (GTAA, Ivy, LAA용)
│   ├── kis_api.py            # KIS API 클라이언트
│   ├── momentum.py           # 모멘텀 스코어 계산
│   ├── portfolio.py          # 포트폴리오 주문 생성/실행
│   ├── report.py             # 리포트 생성
│   └── yfinance_loader.py    # yfinance 가격 로더
├── data/                     # CSV 출력 (trading 브랜치에서 관리)
│   ├── strategy_signals.csv  # 일별 전략 신호
│   ├── strategy_nav.csv      # 전략별 NAV 누적
│   ├── portfolio_nav.csv     # 포트폴리오 합산 NAV (서킷 브레이커용)
│   ├── momentum.csv          # 자산별 모멘텀 스코어
│   ├── holdings.csv          # 보유 현황
│   └── ohlc_history.csv      # 자산 가격 히스토리
├── docs/
│   └── STRATEGY.md           # 전략 상세 설명
├── config.json               # 전략/선택 설정
├── key.json.example          # API 키 템플릿
├── run_rebalance.py          # 리밸런싱 엔트리포인트
├── run_collect.py            # 일별 수집 엔트리포인트
├── run_backfill.py           # 과거 데이터 백필 엔트리포인트
└── run_selection_backtest.py # 전략 선택 기준 비교 백테스트
```

## 주의사항

- **실거래 주문이 발생합니다.** 충분히 검증 후 실행하세요.
- 처음 사용 시 `--report-only` 또는 리포트 전용 워크플로우로 먼저 확인하는 것을 권장합니다.
- `run_backfill.py`를 먼저 실행해야 NAV 데이터가 생성됩니다.
- `run_selection_backtest.py --generate-portfolio-nav`로 포트폴리오 NAV를 백필해야 MDD 서킷 브레이커가 동작합니다.
- 새 전략 추가 방법은 [docs/STRATEGY.md](docs/STRATEGY.md#새-전략-추가하기)를 참고하세요.
