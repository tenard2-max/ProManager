"""로컬 Cursor state.vscdb에서 auth 키 존재 여부만 확인 (토큰 전문 출력 금지)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

db = Path.home() / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()
rows = cur.execute(
    "SELECT key FROM ItemTable WHERE key LIKE ? OR key LIKE ? OR key LIKE ?",
    ("%cursorAuth%", "%accessToken%", "%Workos%"),
).fetchall()
print("keys:", [r[0] for r in rows])
for key in (
    "cursorAuth/accessToken",
    "cursorAuth/refreshToken",
    "cursorAuth/cachedEmail",
    "cursorAuth/stripeMembershipType",
    "cursorAuth/stripeSubscriptionStatus",
):
    r = cur.execute(
        "SELECT length(value), substr(value,1,12) FROM ItemTable WHERE key=?",
        (key,),
    ).fetchone()
    print(key, r)
con.close()
