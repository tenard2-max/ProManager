from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx

db = Path.home() / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
token = con.execute(
    "SELECT value FROM ItemTable WHERE key=?", ("cursorAuth/accessToken",)
).fetchone()[0]
con.close()
if isinstance(token, bytes):
    token = token.decode()
token = token.strip().strip('"')
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Connect-Protocol-Version": "1",
}
base = "https://api2.cursor.sh/aiserver.v1.DashboardService"
names = [
    "GetUsageBasedPremiumRequests",
    "GetHardLimit",
    "GetCurrentPeriodUsage",
    "GetTeams",
    "GetUserPrivacyMode",
]
with httpx.Client(timeout=15.0) as c:
    for n in names:
        r = c.post(f"{base}/{n}", headers=headers, content=b"{}")
        print(n, r.status_code, r.text[:400].replace("\n", " "))
