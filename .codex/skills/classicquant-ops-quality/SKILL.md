---
name: classicquant-ops-quality
description: classicQuant 저장소를 분석해 운영 효율, 실거래 안정성, 데이터 무결성, 개발 품질을 높이는 작업을 수행하는 스킬. 전략 추가/수정, 리밸런싱 로직 변경, 백테스트 점검, GitHub Actions 운영 개선, 데이터 CSV 검증, 운영 가이드/기여자 가이드 작성이 필요할 때 사용한다. 이 스킬을 사용할 때는 결과 요약, 리뷰 코멘트, 운영 문서와 가이드를 기본적으로 한글로 작성한다.
---

# classicQuant 운영·품질 향상

## 개요
이 저장소는 실거래 리밸런싱과 CSV 기반 상태 누적이 결합된 구조다. 변경사항을 볼 때 일반적인 코드 품질뿐 아니라 실거래 영향, 데이터 누적 안정성, 워크플로우 분기(`main` vs 비-`main`)를 함께 점검한다.

## 작업 흐름
1. 먼저 `README.md`, `CLAUDE.md`, `.github/workflows/classicQuant.yml`를 읽어 운영 흐름을 확인한다.
2. 변경 범위를 아래 다섯 가지로 분류한다.
   - 전략 로직: `app/strategies/`, `app/strategy.py`, `app/strategy_selector.py`
   - 주문/실행: `app/execution/`, `run_rebalance.py`
   - 데이터 수집/정규화: `app/data/`, `app/analytics/csv_logger.py`, `run_backfill.py`, `run_collect.py`
   - 백테스트/분석: `run_selection_backtest.py`, `app/analytics/backtest.py`
   - 운영 문서/가이드: `README.md`, `AGENTS.md`, `docs/`
3. 실거래 경로가 닿는 변경이면 `--report-only` 검증 경로를 우선 고려하고, 주문 실행 부작용이 없는지 확인한다.
4. CSV를 다루는 변경이면 날짜 정규화, 중복 행 방지, append-only 동작, 기존 파일과의 호환성을 우선 점검한다.
5. 결과를 낼 때는 위험, 검증 방법, 남은 운영 리스크를 짧게 정리한다.

## 저장소 전용 점검 기준
- `run_rebalance.py` 수정 시: 휴장 체크, MDD 서킷 브레이커, fallback 전략, `--report-only` 경로를 함께 검토한다.
- `app/strategy_selector.py` 수정 시: 점수 부족 구간, NAV 워밍업 부족, `top_n=None`, 상관관계 필터, fallback 보강 로직을 확인한다.
- `app/analytics/csv_logger.py` 수정 시: 날짜 형식이 `YYYY-MM-DD`로 통일되는지, 중복 방지 기준이 유지되는지 본다.
- 새 전략 추가 시: `app/strategies/{name}/__init__.py`, 등록 import, `config.json`, 필요한 자산 정의가 모두 반영됐는지 확인한다.
- 워크플로우 수정 시: `main` 브랜치만 실거래하고 `trading` 브랜치에 결과를 커밋하는 현재 계약을 깨지 않는지 확인한다.

## 검증 기본값
- 의존성 추가 없이 끝나는 변경이면 관련 스크립트를 직접 실행해 검증한다.
- 대표 명령:
  - `python run_selection_backtest.py --top-n 4`
  - `python run_selection_backtest.py --generate-portfolio-nav`
  - `python run_collect.py`
  - `python run_rebalance.py --report-only`
- 테스트가 없으면 “무엇을 실행했고 무엇은 미실행인지”를 명확히 남긴다.

## 출력 규칙
- 운영 보고, 리뷰, 가이드, 제안서는 기본적으로 한글로 작성한다.
- 코드 리뷰는 버그, 리스크, 회귀 가능성, 누락된 검증을 우선순위대로 제시한다.
- 문서를 새로 쓰거나 고칠 때는 저장소의 실제 명령과 경로를 그대로 예시로 넣는다.

## 참고 자료
- 상세 체크리스트와 주요 파일 맵은 `references/project-checklist.md`를 먼저 본다.
