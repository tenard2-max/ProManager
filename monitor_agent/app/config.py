"""관제 에이전트 설정. 로컬 바인딩·주기·경로만 관리한다."""

from __future__ import annotations

from pathlib import Path

# 프로젝트 루트: monitor_agent/
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SPEC_PATH = DATA_DIR / "spec.ini"
STATUS_PATH = DATA_DIR / "project_status.ini"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
HISTORY_DIR = DATA_DIR / "history"
HISTORY_LOG_PATH = HISTORY_DIR / "events.jsonl"
STATIC_DIR = ROOT_DIR / "static"

HOST = "127.0.0.1"
# 8765는 XFS 시뮬레이터 등과 충돌할 수 있어 관제 전용 포트 사용
PORT = 18765

WATCH_INTERVAL_SEC = 5.0
WATCH_TOLERANCE_SEC = 1.0
HEARTBEAT_TIMEOUT_SEC = 90.0
ACK_TIMEOUT_SEC = 10.0
ACK_MAX_RETRIES = 3
HISTORY_RETENTION_DAYS = 90
SCHEMA_VERSION = 1
TOKEN_LIVE_INTERVAL_SEC = 10.0

# progress 권한
CURSOR_PROGRESS_MAX = 60
QA_PROGRESS_MIN = 80
# 61~79는 표시용만 (실제 저장 금지)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
