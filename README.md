# classicQuant

모멘텀 기반 퀀트 전략(DAA, VAA)을 GitHub Actions로 자동 운용합니다.
Fork 후 API 키만 등록하면 매일 자동으로 리밸런싱이 실행됩니다.

> 전략 상세 설명은 [docs/STRATEGY.md](docs/STRATEGY.md)를 참고하세요.

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

설정이 끝나면 평일 15:30 UTC (한국시간 00:30)에 자동으로 리밸런싱이 실행됩니다.
바로 테스트하려면 Actions 탭에서 수동 실행(`Run workflow`)할 수 있습니다.

## 전략 설정 (선택)

기본값(DAA 50% + VAA 50%)으로도 바로 사용 가능합니다.
전략 비중이나 매매 파라미터를 바꾸고 싶다면 `CONFIG_JSON` Secret을 등록하세요.

**Settings > Secrets and variables > Actions**에서 `CONFIG_JSON` Secret에 원하는 설정을 입력합니다:

```json
{
  "strategies": [
    { "name": "daa", "weight": 0.7 },
    { "name": "vaa", "weight": 0.3 }
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

> Secret이 없으면 저장소의 기본 `config.json`이 사용됩니다.
> Secret으로 관리하면 Sync fork로 소스를 업데이트해도 개인 설정이 유지됩니다.

## GitHub Actions

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

로컬에서 직접 동작을 확인할 수도 있습니다.

```bash
pip install requests
cp key.json.example key.json   # API 정보 입력
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
├── config.json           # 전략 설정
├── key.json.example      # API 키 템플릿
└── run_rebalance.py      # 실행 엔트리포인트
```

## 주의사항

- **실거래 주문이 발생합니다.** 충분히 검증 후 실행하세요.
- 처음 사용 시 `--report-only` 또는 리포트 전용 워크플로우로 먼저 확인하는 것을 권장합니다.
- 새 전략 추가 방법은 [docs/STRATEGY.md](docs/STRATEGY.md#새-전략-추가하기)를 참고하세요.
