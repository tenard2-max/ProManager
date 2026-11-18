"""Cursor GetCurrentPeriodUsage / GetSandUsageStatus 응답 스키마 확인."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx

db = Path.home() / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
token = con.execute(
    "SELECT value FROM ItemTable WHERE key=?",
    ("cursorAuth/accessToken",),
).fetchone()[0]
con.close()
if isinstance(token, bytes):
    token = token.decode("utf-8")
token = token.strip().strip('"')

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Connect-Protocol-Version": "1",
}

with httpx.Client(timeout=20.0) as client:
    for name in (
        "GetCurrentPeriodUsage",
        "GetSandUsageStatus",
        "GetPlanInfo",
    ):
        url = f"https://api2.cursor.sh/aiserver.v1.DashboardService/{name}"
        try:
            r = client.post(url, headers=headers, content=b"{}")
            print("===", name, r.status_code, "===")
            try:
                data = r.json()
            except Exception:
                print(r.text[:500])
                continue
            print(json.dumps(data, ensure_ascii=False, indent=2)[:2500])
        except Exception as exc:
            print(name, "ERR", exc)

    # REST fallback
    r = client.get(
        "https://cursor.com/api/usage-summary",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20.0,
    )
    print("=== usage-summary", r.status_code, "===")
    print(r.text[:2000])
