# ProManager — Central-Agent Orchestration

다양한 프로젝트와 에이전트(Cursor IDE · 그록 QA)를 연결해 **감시·보고·명령**하는 로컬 관제 플랫폼입니다.

| 구성 | 설명 |
|------|------|
| `DOC/` | 요구사항·연동 지시·사용법 (SSOT 문서) |
| `monitor_agent/` | FastAPI 관제 서버 + 대시보드 UI (`127.0.0.1:18765`) |
| `monitor_fs_ui/` | File System Access API 기반 정적 뷰어 (`127.0.0.1:18766`) |
| `reports/` | DoD·최종 보고서 |

제품별 런타임 상태 SSOT는 **해당 GitHub/제품 프로젝트의 `docs/`** (`spec.ini` · `project_status.ini`) 입니다.  
관제 인프라 자체는 이 저장소의 `monitor_agent` 를 사용합니다.

---

## 빠른 시작

### 1) 관제 서버 (부모)

```bat
cd monitor_agent
pip install -r requirements.txt
run_server.bat
```

브라우저: http://127.0.0.1:18765/

### 2) FS 뷰어 (아들, 선택)

```bat
cd monitor_fs_ui
open_ui.bat
```

브라우저: http://127.0.0.1:18766/  
→ **data / docs 폴더 선택** 후 `project_status.ini` 자동 갱신

### 3) 에이전트 클라이언트 예시

```bat
cd monitor_agent
python tools/agent_client.py heartbeat --agent cursor
python tools/agent_client.py status --req REQ_001 --progress 60
```

---

## 문서 안내

| 문서 | 용도 |
|------|------|
| [DOC/3. 개발 요건서](DOC/3.%20%5B개발%20요건서%5D%20에이전트%20감시%20관제%20시스템%20(Cursor%20IDE%20·%20그록%20봇%20모니터링).md) | 관제 시스템 본체 요건 |
| [DOC/6. 요구사항.MD](DOC/6.%20요구사항.MD) | 신규 프로젝트 → Cursor 연동 템플릿 |
| [DOC/6. 요구사항 - 봇.MD](DOC/6.%20요구사항%20-%20봇.MD) | 그록 QA 연동 템플릿 |
| [DOC/6. 요구사항 - XFS.MD](DOC/6.%20요구사항%20-%20XFS.MD) | XFS 프로젝트 기입본 |
| [DOC/7. 관제 서버 사용법.md](DOC/7.%20관제%20서버%20사용법.md) | 서버 운영 |
| [DOC/8. FS 관제 뷰어](DOC/8.%20FS%20관제%20뷰어%20(아들%20프로젝트).md) | 아들 뷰어 |

---

## 개발·테스트

```bat
cd monitor_agent
run_tests.bat
```

포트 `18765` 는 XFS 등 다른 로컬 서비스와 `8765` 충돌을 피하기 위해 사용합니다.  
바인딩은 `127.0.0.1` 전용입니다.

---

## 라이선스 / 저장소

- GitHub: https://github.com/tenard2-max/ProManager
- 로컬 작업 루트 예: `D:\Cursor\ProjManager`
