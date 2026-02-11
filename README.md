# classicQuant

모멘텀 기반 퀀트 전략(DAA, VAA)을 동시에 운용하며, GitHub Actions로 매일 자동 리밸런싱을 수행합니다.
한국투자증권 KIS API를 통해 미국 ETF를 자동 매매합니다.

## 주요 기능

- GitHub Actions 기반 완전 자동 리밸런싱 (평일 매일 실행)
- DAA / VAA 전략 동시 운용 (비중 조절 가능)
- 모멘텀 스코어 기반 자동 종목 선정
- 예비자산 자동 폴백 및 승격
- 일별 리포트 자동 생성 및 커밋

> 전략 상세 설명은 [docs/STRATEGY.md](docs/STRATEGY.md)를 참고하세요.

## 설정 방법

### 1. 사전 준비

- [한국투자증권 KIS API](https://apiportal.koreainvestment.com/) 앱 키 발급
- 이 저장소를 Fork 또는 본인 계정에 복제

### 2. GitHub Secrets 등록

저장소의 **Settings > Secrets and variables > Actions**에서 다음 Secrets를 등록합니다:

| Secret | 설명 |
|--------|------|
| `KIS_APP_KEY` | KIS API 앱 키 |
| `KIS_APP_SECRET` | KIS API 앱 시크릿 |
| `KIS_ACCOUNT_NUMBER` | 계좌번호 |
| `KIS_ACCOUNT_CODE` | 계좌 상품코드 |

### 3. Workflow 권한 설정

**Settings > Actions > General > Workflow permissions**에서 **Read and write permissions**를 활성화합니다.
(리포트/데이터 자동 커밋에 필요)

### 4. 전략 설정 (선택)

`config.json`에서 전략 비중과 매매 파라미터를 조정할 수 있습니다. 기본값으로도 바로 사용 가능합니다.

```json
{
  "strategies": [
    { "name": "daa", "weight": 0.5 },
    { "name": "vaa", "weight": 0.5 }
  ],
  "strategy": {
    "rebalance_threshold_pct": 0.05,
    "cash_buffer_pct": 0.0,
    "min_trade_value_usd": 5.0
  }
}
```

| 항목 | 설명 |
|------|------|
| `rebalance_threshold_pct` | 목표 비중과의 차이가 이 값 이상일 때만 리밸런싱 |
| `cash_buffer_pct` | 현금 보유 비율 (0.0 = 전액 투자) |
| `min_trade_value_usd` | 최소 매매 금액 (USD) |

## GitHub Actions (메인 운용 방식)

### 자동 리밸런싱 (`classicQuant.yml`)
- 평일 15:30 UTC (한국시간 00:30) 자동 실행
- 매매 실행 + 리포트 생성 + 데이터 자동 커밋
- 최대 5회 재시도

### 리포트 전용 (`classicQuant-report.yml`)
- 수동 실행 전용 (Actions 탭 > "ClassicQuant Report Only" > "Run workflow")
- 매매 없이 모멘텀 분석 리포트만 생성

리포트는 `reports/YYYY-MM-DD.md`에 자동 저장됩니다.

## 로컬 실행 (테스트용)

로컬에서 직접 실행하여 동작을 확인할 수도 있습니다.

```bash
pip install requests
```

`key.json.example`을 복사하여 `key.json`을 생성하고 API 정보를 입력합니다.

```bash
cp key.json.example key.json
```

```bash
# 리포트만 생성 (매매 없이 모멘텀 분석 확인)
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
│   │   ├── daa/          # DAA 전략 + assets.json
│   │   └── vaa/          # VAA 전략 + assets.json
│   ├── config.py         # 설정 로드
│   ├── kis_api.py        # KIS API 클라이언트
│   ├── momentum.py       # 모멘텀 스코어 계산
│   ├── portfolio.py      # 포트폴리오 주문 생성/실행
│   └── report.py         # 리포트 생성
├── data/                 # CSV 로그 데이터
├── reports/              # 일별 리포트
├── config.json           # 전략 설정
├── key.json.example      # API 키 템플릿
└── run_rebalance.py      # 실행 엔트리포인트
```

## 주의사항

- **실거래 주문이 발생합니다.** 충분히 검증 후 실행하세요.
- 로컬 테스트 시 `--report-only`로 먼저 확인하는 것을 권장합니다.
- 새 전략 추가 방법은 [docs/STRATEGY.md](docs/STRATEGY.md#새-전략-추가하기)를 참고하세요.
