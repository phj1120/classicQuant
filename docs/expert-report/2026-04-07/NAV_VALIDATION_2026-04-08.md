# NAV 분리 정합성 검증 메모

> 작성일: 2026-04-08
> 범위: 저장소 로컬 데이터 기준 NAV 분리 상태 점검

## 1. 검증 목적

이번 점검의 목적은 "코드가 바뀌었다" 수준이 아니라, 현재 저장소에 들어 있는 실제 CSV 상태가 새 NAV 정책과 얼마나 맞는지 확인하는 것이다.

실계좌 API 키가 없는 환경이므로, 이번 검증은 다음 범위로 제한했다.

- 로컬 CSV 파일 존재 여부
- 레거시/신규 NAV 파일 간 행 수와 내용 비교
- 무키 환경 `run_rebalance.py --report-only` 동작 여부

실계좌 정합성 검증은 이번 범위에 포함되지 않는다.

## 2. 확인 결과

### 2-1. 전략/포트폴리오 NAV 파일

| 파일 | 상태 | 비고 |
|------|------|------|
| `data/strategy_nav.csv` | 존재 | 전략별 NAV 원장 |
| `data/portfolio_nav.csv` | 존재 | 레거시 파일 |
| `data/portfolio_nav_model.csv` | 존재 | 모델 포트폴리오 NAV |
| `data/portfolio_nav_actual.csv` | 없음 | actual NAV 실데이터 미적재 |
| `data/portfolio_state.csv` | 없음 | 실제 총자산 스냅샷 미적재 |

### 2-2. 레거시/모델 파일 비교

현재 저장소의 `data/portfolio_nav.csv`와 `data/portfolio_nav_model.csv`는:

- 행 수 동일: 5032행
- 첫 날짜 동일: `2006-03-31`
- 마지막 날짜 동일: `2026-04-01`
- 전 행 내용 동일

해석:

- 현재 커밋된 `portfolio_nav.csv`는 사실상 model NAV의 레거시 복사본이다.
- 아직 actual NAV로 분리 적재된 운영 데이터는 저장소에 없다.

## 3. 무키 환경 검증

기존에는 `python3 run_rebalance.py --report-only`도 API 키가 없으면 즉시 실패했다.

이번 라운드에서:

- API 키가 없고
- `data/ohlc_history.csv`가 존재하면

`run_rebalance.py --report-only`가 offline 캐시 모드로 실행되도록 변경했다.

이 모드의 보장 범위:

- 전략 신호 계산
- 전략 선택 로직 검증
- 마크다운 리포트 생성
- legacy NAV를 읽더라도 `portfolio_nav_actual.csv`를 디스크에 새로 만들지 않음

이 모드의 비보장 범위:

- 실제 계좌 잔고 조회
- 실제 주문 생성 검증
- actual NAV 적재
- `portfolio_state.csv` 적재

## 4. 운용 관점 결론

현재 classicQuant의 NAV 상태는 이렇게 봐야 한다.

1. 전략 NAV: 정상 운영 중
2. 모델 포트폴리오 NAV: 정상 분리 완료
3. 실제 포트폴리오 NAV: 코드 경로는 준비됐지만 저장소 실데이터는 아직 없음

즉,

> 코드 레벨 NAV 분리는 완료됐지만, actual NAV 데이터셋은 아직 시작 전 상태다.

## 5. 다음 운영 단계

실계좌 접근이 가능한 시점에 다음 순서로 마무리하는 게 맞다.

1. `python run_rebalance.py --report-only`를 키가 있는 환경에서 1회 실행
2. `data/portfolio_state.csv` 생성 확인
3. `data/portfolio_nav_actual.csv` 생성 확인
4. 리포트의 총자산 값과 `portfolio_state.csv` 값 대조
5. actual NAV의 첫 handoff 로직이 의도대로 적용됐는지 확인

그 전까지는 `portfolio_nav_actual`을 실운용 히스토리로 해석하면 안 된다.
