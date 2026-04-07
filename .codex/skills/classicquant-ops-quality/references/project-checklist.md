# classicQuant 체크리스트

## 핵심 운영 흐름
- 초기 적재: `python run_backfill.py`
- 포트폴리오 NAV 생성: `python run_selection_backtest.py --generate-portfolio-nav`
- 일별 수집: `python run_collect.py`
- 월별/수동 리밸런싱: `python run_rebalance.py` 또는 `python run_rebalance.py --report-only`

## 주요 코드 핫스팟
- `run_rebalance.py`: 실거래 진입점, 휴장 체크, 포트폴리오 MDD, 보고서 생성
- `app/execution/portfolio.py`: 매수/매도 주문 계산, 대체 티커 승격, 최소 주문 금액 처리
- `app/strategy_selector.py`: 전략 선택 점수, drawdown 필터, fallback 처리
- `app/analytics/csv_logger.py`: CSV append 정책, 날짜 정규화, 중복 제거
- `app/config.py`: `key.json`/환경변수 로딩, selection/strategy 기본값

## 리뷰 시 자주 보는 리스크
- 실거래 경로와 `--report-only` 경로가 섞여 회귀가 발생하는지
- `data/*.csv` 중복 행 또는 날짜 포맷 불일치가 생기는지
- NAV 워밍업 부족 시 `None` 점수 처리와 fallback이 안전한지
- 전략 추가 후 registry import 누락으로 로딩이 실패하지 않는지
- 워크플로우가 `main` 외 브랜치에서 매매를 실행하지 않는지

## 문서 규칙
- 운영 문서, 가이드, 리뷰 요약은 한글 우선
- 외부 사용자를 위한 예제는 실제 저장소 명령 그대로 사용
- `key.json` 실파일은 커밋 금지, 비밀값은 GitHub Secrets 전제로 설명
