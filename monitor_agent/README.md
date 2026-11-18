# Central-Agent Orchestration (AI 관제 에이전트)

Cursor IDE · 그록 봇의 작업을 로컬에서 감시하는 관제 에이전트(FastAPI + 로컬 UI).

## 실행

```bash
cd monitor_agent
pip install -r requirements.txt
python -m app.main
```

브라우저: http://127.0.0.1:18765/  
바인딩: `127.0.0.1` 전용. 포트 `18765` (8765는 XFS 등과 충돌 가능).

## 테스트

```bash
cd monitor_agent
pytest -q
```

## 주요 API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/messages` | SPEC_RESET / STATUS_UPDATE / QA_RESULT / HEARTBEAT / ACK |
| GET | `/api/messages/outbox?agent=cursor\|grok` | 명령 폴링 |
| POST | `/api/commands` | 발주자 명령 |
| GET | `/api/state` | 대시보드 스냅샷 |
| GET | `/api/history` | 이력 |
| GET | `/api/metrics` | 감시 지표 |

## 데이터

- `data/spec.ini` — 요건 INI
- `data/project_status.ini` — 상태 INI
- `data/history/events.jsonl` — 추가 전용 이력
- `data/snapshots/` — 마지막 정상 스냅샷

## 확정 가정

- 메시지 채널: 로컬 HTTP
- progress 61–79: 저장 불가(표시용)
- QA PASSED progress: `80 + round(qa_score * 0.2)`
- 이력 보관: 90일
