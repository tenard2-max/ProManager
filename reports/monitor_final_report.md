# 감시 관제 시스템 최종 보고서

작성일: 2026-11-13 · 버전: v1.0 구현

## 1. 요약

- 구현 완료 단계: Phase 1–8 (요건서 11장)
- DoD 달성: 자동 테스트 20건 통과 기준으로 핵심 항목 검증
- 주요 리스크: 그록 봇 호출 방식(QUESTION-3)은 HTTP 수신형으로 임시 확정, 실제 봇 스케줄러는 후속 연동 필요

## 2. DoD 항목별 증빙

| # | 기준 | 증빙 |
|---|------|------|
| 1 | spec.ini 제출 후 UI 표시 | `tests/test_api_dod.py::test_spec_reset_shows_in_state` |
| 2 | 필수 키 누락 거부 | `tests/test_spec_parser.py` |
| 3 | 외부 상태 수정 감지 | `tests/test_watch_loop.py::test_watch_detects_status_change` |
| 4 | progress ≥61 거부 | `tests/test_messaging.py`, `test_api_dod.py` |
| 5 | QA_RESULT 반영 | `tests/test_messaging.py::test_qa_result_and_rework_count` |
| 6 | 반려 시 rework +1 | 동일 |
| 7 | msg_id 멱등 | `tests/test_messaging.py::test_idempotent_msg_id` |
| 8 | 90초 OFFLINE | `HeartbeatTracker(timeout_sec=90)` + heartbeat 단위 테스트 |
| 9 | 명령 ACK UI | `CommandDispatcher` + UI 명령 패널 (`static/app.js`) |
| 10 | 지표 재계산 일치 | `tests/test_metrics.py` |
| 11 | 재시작 복원 | `WatchLoop._restore_snapshots` + `data/snapshots/` |
| 12 | 외부 네트워크 없음 | `HOST=127.0.0.1` 바인딩 (`app/config.py`) |

테스트 실행:

```bash
cd monitor_agent
pytest -q
```

## 3. 감시 지표

초기 샘플 데이터 기준 지표는 서버 기동 후 `GET /api/metrics` 및 `?recalc=true`로 확인한다.  
재계산 로직은 `MetricsCalculator.recalculate_from_history`이며 단위 테스트에서 live ≡ recalc를 검증했다.

## 4. 발견된 결함 / 엣지 케이스

| 재현 | 기대 | 실제 | 심각도 |
|------|------|------|--------|
| ConfigParser 중복 섹션 | SpecValidationError | 초기엔 미처리 → 수정 완료 | 중 (수정됨) |
| progress 61–79 | 저장 거부 | StatusValidationError | 의도된 동작 |
| 상태 INI에 priority 등 명세 부가필드 미저장 | UI는 기동 시 spec 병합으로 표시 | 파일에는 status 스키마만 유지 | 낮음 |

## 5. 미확정 사항 최종 결정

| ID | 결정 |
|----|------|
| QUESTION-1 | 61–79는 표시용만, 저장 불가 |
| QUESTION-2 | 로컬 HTTP |
| QUESTION-3 | 봇이 HTTP로 HEARTBEAT/QA_RESULT 송신 (수신형) |
| QUESTION-4 | 이력 보관 90일 |
| ASSUMPTION-1 | `80 + round(qa_score * 0.2)` 유지 |
| ASSUMPTION-2 | 요건 원본 편집은 발주자, Cursor는 SPEC_RESET만 |

## 6. 재현 명령

```bash
cd D:\Cursor\ProjManager\monitor_agent
pip install -r requirements.txt
pytest -q
python -m app.main
# 다른 터미널
python tools/agent_client.py spec_reset
python tools/agent_client.py heartbeat --agent cursor
python tools/agent_client.py status --req REQ_001 --progress 60
python tools/agent_client.py qa --req REQ_001 --qa-status PASSED --qa-score 90
```

브라우저: http://127.0.0.1:8765
