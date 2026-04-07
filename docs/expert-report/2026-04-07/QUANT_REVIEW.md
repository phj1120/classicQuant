# classicQuant 전문 퀀트 운용 재점검 보고서

> 최초 진단: 2026-04-07
> 재점검 반영: 2026-04-07
> 기준: 코드 수정 후 재분석 + 로컬 명령 검증

---

## 1. 요약

2026-04-07 1차 점검에서 지적했던 핵심 과제 10개는 이번 라운드에서 모두 코드와 문서에 반영했다. 특히 실거래 관점에서 중요했던 네 가지,

- `portfolio_nav`의 실제 총자산 기준 전환
- 선택 전략 수 부족 시 비중 재정규화
- CSV 로거의 idempotent 저장
- 백테스트 스크립트의 비대화형 실행 지원

은 구조적으로 정리됐다.

이제 이 저장소는 "아이디어 검증용 전략 모음"에서 "개인용 자동 퀀트 운용 도구" 쪽으로 한 단계 올라왔다. 다만 기관형 수준의 체결 검증, 주문 재시도 정책, 세금/수수료 반영, 체결 기준 실현손익 accounting까지는 아직 아니다.

---

## 2. 이번 라운드 핵심 개선

### 2-1. 포트폴리오 accounting 정합성 개선

관련 파일:

- [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)
- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

변경 내용:

- 모델 포트폴리오 NAV는 `portfolio_nav_model.csv`로 분리했다.
- 실제 포트폴리오 NAV는 `portfolio_nav_actual.csv` + `portfolio_state.csv` 기반으로 관리하도록 바꿨다.
- 기존 3컬럼 `portfolio_nav.csv`는 actual NAV 호환 입력으로 자동 승격되도록 마이그레이션 로직을 넣었다.

의미:

- 포트폴리오 MDD 서킷브레이커가 실제 계좌 자산 흐름에 더 가까운 기준을 보게 됐다.
- 과거 synthetic NAV에서 actual-equity 추적으로 넘어가는 handoff 경로도 안전하게 만들었다.

제한:

- 과거 전체 히스토리를 실계좌 총자산 기준으로 재구성한 것은 아니다.
- 실제 체결 기준 realized/unrealized PnL ledger까지는 아직 없다.
- 현재 저장소에는 `portfolio_nav_actual.csv`, `portfolio_state.csv` 실데이터가 아직 쌓여 있지 않다.

### 2-2. 자본배분 버그 제거

관련 파일:

- [app/strategy_selector.py](/Users/parkh/Dev/git/Project/classicQuant/app/strategy_selector.py)

변경 내용:

- 실제 선택된 전략 수 기준으로 최종 비중을 재정규화한다.
- `top_n=2`인데 상관 필터 등으로 1개 전략만 남는 경우도 100% 배분된다.

의미:

- 의도치 않은 숨은 현금 비중이 제거됐다.
- 백테스트와 실거래의 위험 예산이 더 일관되게 맞춰졌다.

### 2-3. 결측 가격 처리 규칙 통일

관련 파일:

- [app/analytics/returns.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/returns.py)
- [run_collect.py](/Users/parkh/Dev/git/Project/classicQuant/run_collect.py)
- [app/analytics/backtest.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/backtest.py)

변경 내용:

- 공용 `compute_weighted_return()`을 도입했다.
- 가격이 없는 그룹은 비중을 유지한 채 0% 수익률로 처리한다.
- 일별 수집과 백테스트가 동일 정책을 사용한다.

의미:

- 전략 NAV와 백테스트 간 정책 불일치가 제거됐다.

### 2-4. 운영 로그 재실행 안전성 확보

관련 파일:

- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

변경 내용:

- `holdings.csv`, `momentum.csv`, `portfolio.csv`, `strategy_signals.csv`에 키 기반 dedupe를 넣었다.

의미:

- GitHub Actions 재시도 시 동일 날짜 중복 누적 가능성이 크게 줄었다.

### 2-5. 실거래 예외 처리 강화

관련 파일:

- [app/data/kis_api.py](/Users/parkh/Dev/git/Project/classicQuant/app/data/kis_api.py)
- [app/execution/portfolio.py](/Users/parkh/Dev/git/Project/classicQuant/app/execution/portfolio.py)
- [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)

변경 내용:

- KIS API에 공통 timeout/예외 처리 래퍼를 추가했다.
- 주문 실행은 성공/실패 요약을 반환한다.
- 주문 후 잔고/현금 재조회 기반 계정 스냅샷을 남긴다.

의미:

- 실거래 실패가 이전보다 더 명확히 보인다.
- "주문을 보냈다"에서 끝나지 않고 "이후 계정이 어떻게 보이는지"까지 확인 가능해졌다.

### 2-6. 리서치 명령 확장

관련 파일:

- [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)
- [WALK_FORWARD_AND_OVERLAP.md](/Users/parkh/Dev/git/Project/classicQuant/docs/expert-report/2026-04-07/WALK_FORWARD_AND_OVERLAP.md)

변경 내용:

- `--walk-forward`
- `--duplication`
- `--apply-config`

를 추가했다.

의미:

- 이제 메타 선택 기준의 OOS 안정성과 전략군 중복도를 코드 경로로 직접 확인할 수 있다.

---

## 3. 재분석 결과

### 3-1. 기본 10년 비교

실행:

```bash
python3 run_selection_backtest.py --top-n 2
```

결과 요약:

| 기준 | CAGR | Sharpe | MDD | Calmar |
|------|------|--------|-----|--------|
| `sharpe_12m` | 10.8% | 0.93 | -23.2% | 0.47 |
| `corr_constrained` | 9.6% | 0.91 | -19.1% | 0.50 |
| `equal_weight` | 9.7% | 1.11 | -12.8% | 0.76 |

판단:

- `sharpe_12m`는 수익률 우위
- `corr_constrained`는 낙폭 통제 우위
- `equal_weight`는 여전히 위험조정 성과가 강함

즉, 메타 셀렉터는 의미는 있지만 "압도적 우위"는 아니다.

### 3-2. Walk-forward 결과

실행:

```bash
python3 run_selection_backtest.py --walk-forward --top-n 2 --train-years 5 --test-years 1
```

핵심 결과:

- 평균 OOS Sharpe 1위: `sharpe_12m` 1.11
- 평균 OOS Sharpe 2위: `corr_constrained` 1.02
- fold 승리 횟수 1위: `calmar_12m` 5회
- `sharpe_12m`와 `corr_constrained`는 장기적으로 가장 일관된 상위권

판단:

- 현 설정의 `corr_constrained`는 충분히 방어적 근거가 있다.
- 다만 pure OOS 평균 Sharpe만 보면 `sharpe_12m`가 더 우세하다.
- 실운용에서 수익률 우선이면 `sharpe_12m`, 방어 우선이면 `corr_constrained`가 합리적이다.

### 3-3. 전략군 중복도

실행:

```bash
python3 run_selection_backtest.py --duplication --years 10
```

핵심 결과:

- 완전 중복 수준:
  - `baa_g4` / `haa` / `vaa`
- 매우 높은 중복:
  - `baa_g12` / `paa`
  - `gtaa` / `ivy`
  - `laa` / `permanent`
- 최근 10년 선택 집중:
  - `laa` 42회
  - `permanent` 30회
  - `daa` 27회
  - `gem` 24회

판단:

- 전략 15개가 곧 15개의 독립 알파는 아니다.
- 현재 구조는 실제로 몇 개 대표 축을 여러 변형으로 중복 보유하고 있다.
- 전략군 축소와 대표 전략화는 여전히 유효한 다음 과제다.

---

## 4. 현재 운용 등급

### 리서치 품질

- 평가: 상
- 근거: 장기 NAV, walk-forward, 중복도 분석까지 코드 경로로 확보

### 개인 실거래 준비도

- 평가: 중상
- 근거: accounting, 날짜 기준, 중복 로그, 주문 후 확인까지 기본 골격 완성

### 고액/기관형 적합성

- 평가: 중하
- 근거: 체결 확정 기준 회계, 세금/수수료, 주문 재시도 정책, 감사용 ledger는 아직 부족

---

## 5. 남은 잔존 리스크

이번 체크리스트는 모두 닫았지만, 아래는 여전히 남는 실무 리스크다.

1. 주문 성공 응답은 체결 완료와 동일하지 않다. 체결 조회 API까지 붙이면 더 견고해진다.
2. 수수료, 세금, 환전 비용이 전략 비교에 반영되지 않는다.
3. `portfolio_nav`는 이제 실제 총자산 기준이지만, 과거 전체 히스토리까지 actual-equity 기준으로 재산출한 것은 아니다.
4. 전략군 중복도가 높아 전략 수 대비 정보량이 낮다.

---

## 6. 결론

이번 라운드 이후 classicQuant는 핵심 운영 결함이 상당 부분 정리됐다. 이전에는 "좋은 전략 연구 저장소"였다면, 지금은 "실제로 돌려볼 수 있는 개인용 자동 퀀트 운용기"에 가깝다.

재점검 기준 최종 평가는 다음과 같다.

> 메타 전략의 알파는 아직 논쟁적이지만, 운용 시스템으로서의 신뢰성은 분명히 올라갔다.

다음 진짜 승부처는 두 가지다.

- 전략군을 줄이고 대표 전략만 남길지
- `corr_constrained`와 `sharpe_12m` 중 실제 운용 철학에 맞는 기준을 고를지
