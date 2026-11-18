# monitor_fs_ui (아들 프로젝트)

**Central-Agent Orchestration**의 File System Access API 기반 **정적 관제 뷰어**.

- 부모: `../monitor_agent` (FastAPI · bat · 메시지 API) — **기존 기능 유지**
- 아들: 본 폴더 — 로컬 INI를 브라우저가 직접 5초마다 읽음

## 실행

```bat
open_ui.bat
```

브라우저: http://127.0.0.1:18766/  
(Chrome / Edge 권장. `file://` 및 Firefox는 API 제한)

1. **data 폴더 선택** 클릭  
2. `D:\Cursor\ProjManager\monitor_agent\data` 선택  
3. `project_status.ini` 표시 · 5초 자동 갱신  

## 부모와 역할 분담

| | 부모 `monitor_agent` | 아들 `monitor_fs_ui` |
|--|----------------------|----------------------|
| 기동 | `run_server.bat` → :18765 | `open_ui.bat` → :18766 |
| INI 쓰기 | 서버·에이전트 메시지 | 읽기 전용 |
| 명령/ACK | 지원 | 없음 (뷰어) |
| 토큰 라이브 API | 지원 | `token_usage.json` 있으면 표시 |

프로젝트(에이전트)가 INI를 실시간 수정하면, 이 뷰어는 5초 안에 반영합니다.

## 구성

- `index.html` / `styles.css` / `app.js`
- `ini.js` — INI 파싱
- `fs.js` — 폴더 선택 · IndexedDB 핸들 저장
- `open_ui.bat` — localhost 정적 서버 (Secure Context)
