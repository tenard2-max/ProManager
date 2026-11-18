# ProManager — Central-Agent Orchestration

다양한 프로젝트와 에이전트(Cursor IDE · 그록 QA)를 연결해 **감시·보고·명령**하는 관제 플랫폼입니다.

## 모니터링 콘솔 (기본)

**https://tenard2-max.github.io/ProManager/**

Chrome/Edge에서 열고, 감시할 프로젝트의 **`docs/`** 폴더를 선택하세요.  
(`project_status.ini` · `spec.ini` 를 5초마다 읽습니다.)

| 구성 | 설명 |
|------|------|
| `docs/` | GitHub Pages 정적 모니터링 콘솔 (배포 루트) |
| `DOC/` | 요구사항·연동 지시·사용법 |
| `monitor_agent/` | FastAPI 관제 서버 + API (`127.0.0.1:18765`) |
| `monitor_fs_ui/` | 동일 콘솔의 로컬 백업 (`127.0.0.1:18766`) |
| `reports/` | DoD·최종 보고서 |

제품별 런타임 상태 SSOT는 **해당 프로젝트의 `docs/`** (`spec.ini` · `project_status.ini`) 입니다.

---

## 빠른 시작

### 1) 정적 콘솔 (권장)

브라우저: https://tenard2-max.github.io/ProManager/  
→ **docs 폴더 선택** (예: `D:\Cursor\XFS\docs`)

### 2) 관제 API 서버 (메시지·명령)

```bat
cd monitor_agent
pip install -r requirements.txt
run_server.bat
```

브라우저: http://127.0.0.1:18765/

### 3) 로컬 FS 뷰어 (백업)

```bat
cd monitor_fs_ui
open_ui.bat
```

브라우저: http://127.0.0.1:18766/

### 4) 에이전트 클라이언트 예시

```bat
cd monitor_agent
python tools/agent_client.py heartbeat --agent cursor
python tools/agent_client.py status --req REQ_001 --progress 60
```

---

## 문서 안내

| 문서 | 용도 |
|------|------|
| [DOC/6. 요구사항.MD](DOC/6.%20요구사항.MD) | 신규 프로젝트 → Cursor 연동 템플릿 |
| [DOC/6. 요구사항 - 봇.MD](DOC/6.%20요구사항%20-%20봇.MD) | 그록 QA 연동 템플릿 |
| [DOC/6. 요구사항 - XFS.MD](DOC/6.%20요구사항%20-%20XFS.MD) | XFS 프로젝트 기입본 |
| [DOC/7. 관제 서버 사용법.md](DOC/7.%20관제%20서버%20사용법.md) | 서버 운영 |
| [DOC/8. FS 관제 뷰어](DOC/8.%20FS%20관제%20뷰어%20(아들%20프로젝트).md) | Pages 콘솔·아들 뷰어 |

---

## 개발·테스트

```bat
cd monitor_agent
run_tests.bat
```

포트 `18765` 는 XFS 등 다른 로컬 서비스와 `8765` 충돌을 피하기 위해 사용합니다.  
바인딩은 `127.0.0.1` 전용입니다.

---

## 저장소

- GitHub: https://github.com/tenard2-max/ProManager
- Pages: https://tenard2-max.github.io/ProManager/
- 로컬 작업 루트 예: `D:\Cursor\ProjManager`
