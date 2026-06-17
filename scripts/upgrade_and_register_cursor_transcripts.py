"""Upgrade imported transcripts to full Cursor bubble format + register sidebar.

Close Cursor completely before running.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

APP = Path(os.environ["APPDATA"]) / "Cursor" / "User"
GLOBAL_DB = APP / "globalStorage" / "state.vscdb"
WS_ID = "3bfced73905b25feccd3f25ddd8399f1"
WS_DB = APP / "workspaceStorage" / WS_ID / "state.vscdb"
TRANSCRIPT_ROOT = Path(r"E:\AI file\agent-transcripts")
TEMPLATE_DIR = Path(r"E:\AI file\artifacts\_cursor_templates")
LOCAL_IDS = {
    "637a9452-f7c4-4d43-807d-9825b05ce062",
    "6a53a677-1880-4bf4-8690-d026c303881b",
}
PATH_RE = re.compile(r"d:\\AI file", re.I)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite(text: str) -> str:
    return PATH_RE.sub(lambda _: r"E:\AI file", text)


def _extract_text(content) -> str:
    if isinstance(content, str):
        return _rewrite(content)
    if not isinstance(content, list):
        return _rewrite(str(content))
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(_rewrite(str(block["text"])))
        elif block.get("type") == "tool_use":
            parts.append(f"[Tool: {block.get('name', 'tool')}]")
    return "\n".join(parts).strip()


def _title_from_text(text: str) -> str:
    m = re.search(r"<user_query>\s*(.+?)(?:\n|$)", text, re.S)
    raw = m.group(1) if m else text
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:80] or "Imported chat"


def _rich_text_plain(text: str) -> str:
    safe = text[:2000]
    payload = {
        "root": {
            "children": [
                {
                    "children": [
                        {
                            "detail": 0,
                            "format": 0,
                            "mode": "normal",
                            "style": "",
                            "text": safe,
                            "type": "text",
                            "version": 1,
                        }
                    ],
                    "direction": "ltr",
                    "format": "",
                    "indent": 0,
                    "type": "paragraph",
                    "version": 1,
                }
            ],
            "direction": "ltr",
            "format": "",
            "indent": 0,
            "type": "root",
            "version": 1,
        }
    }
    return json.dumps(payload, ensure_ascii=False)


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _load_db(con, table, key):
    row = con.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
    if not row or row[0] is None:
        return None
    v = row[0]
    if isinstance(v, bytes):
        v = v.decode("utf-8")
    return json.loads(v)


def _set_db(con, table, key, obj):
    con.execute(
        f"INSERT OR REPLACE INTO {table} (key, value) VALUES (?, ?)",
        (key, json.dumps(obj, ensure_ascii=False)),
    )


def _header(composer_id: str, name: str, created_ms: int, updated_ms: int, header_tpl: dict) -> dict:
    h = copy.deepcopy(header_tpl)
    h["composerId"] = composer_id
    h["name"] = name
    h["createdAt"] = created_ms
    h["lastUpdatedAt"] = updated_ms
    h["conversationCheckpointLastUpdatedAt"] = updated_ms
    h["subtitle"] = name[:160]
    h["totalLinesAdded"] = 0
    h["totalLinesRemoved"] = 0
    h["filesChangedCount"] = 0
    h["contextUsagePercent"] = 0
    h["workspaceIdentifier"] = {
        "id": WS_ID,
        "uri": {
            "$mid": 1,
            "fsPath": "e:\\AI file",
            "_sep": 1,
            "external": "file:///e%3A/AI%20file",
            "path": "/e:/AI file",
            "scheme": "file",
        },
    }
    return h


def _make_bubble(tpl: dict, composer_id: str, msg_type: int, text: str, ts_ms: int) -> tuple[str, dict, dict]:
    bubble_id = str(uuid.uuid4())
    b = copy.deepcopy(tpl)
    b["bubbleId"] = bubble_id
    b["type"] = msg_type
    b["text"] = text[:50000]
    b["createdAt"] = _iso_ms(ts_ms)
    b["conversationState"] = "~"
    if msg_type == 1:
        b["richText"] = _rich_text_plain(text[:2000])
    else:
        b.pop("richText", None)
        b["codeBlocks"] = b.get("codeBlocks") or []
    header = {
        "bubbleId": bubble_id,
        "type": msg_type,
        "grouping": {
            "isRenderable": True,
            "hasText": bool(text.strip()),
            "isShortPlainText": len(text) < 200,
        },
    }
    if msg_type == 2 and text.strip():
        header["grouping"]["isKeptFinalAiVisibleOutsideWorkedForGroup"] = True
    return bubble_id, b, header


def upgrade_all() -> int:
    if not TEMPLATE_DIR.exists():
        raise SystemExit("Run scripts/_dump_cursor_templates.py first (with Cursor open once).")

    user_tpl = _load_json(TEMPLATE_DIR / "bubble_user.json")
    asst_tpl = _load_json(TEMPLATE_DIR / "bubble_assistant.json")
    header_tpl = _load_json(TEMPLATE_DIR / "header.json")
    composer_shell = _load_json(TEMPLATE_DIR / "composer.json")

    backup = GLOBAL_DB.with_suffix(".vscdb.bak-upgrade")
    ws_backup = WS_DB.with_suffix(".vscdb.bak-upgrade")
    shutil.copy2(GLOBAL_DB, backup)
    shutil.copy2(WS_DB, ws_backup)

    gcon = sqlite3.connect(GLOBAL_DB)
    wcon = sqlite3.connect(WS_DB)
    upgraded = 0
    new_headers: list[dict] = []

    try:
        # Remove old minimal bubbles
        for jsonl in TRANSCRIPT_ROOT.glob("*/*.jsonl"):
            cid = jsonl.parent.name
            if cid in LOCAL_IDS:
                continue
            for key, in gcon.execute(
                "SELECT key FROM cursorDiskKV WHERE key LIKE ?",
                (f"bubbleId:{cid}:%",),
            ):
                gcon.execute("DELETE FROM cursorDiskKV WHERE key=?", (key,))

        for jsonl in sorted(TRANSCRIPT_ROOT.glob("*/*.jsonl")):
            composer_id = jsonl.parent.name
            if composer_id in LOCAL_IDS:
                continue

            rows = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
            if not rows:
                continue

            created_ms = int(jsonl.stat().st_mtime * 1000)
            title = "Imported chat"
            headers_only: list[dict] = []
            ts = created_ms

            for row in rows:
                role = row.get("role")
                if role not in {"user", "assistant"}:
                    continue
                text = _extract_text(row.get("message", {}).get("content", []))
                if not text:
                    continue
                if role == "user" and title == "Imported chat":
                    title = _title_from_text(text)
                msg_type = 1 if role == "user" else 2
                tpl = user_tpl if msg_type == 1 else asst_tpl
                _, bubble, hdr = _make_bubble(tpl, composer_id, msg_type, text, ts)
                ts += 1000
                _set_db(gcon, "cursorDiskKV", f"bubbleId:{composer_id}:{bubble['bubbleId']}", bubble)
                headers_only.append(hdr)

            if not headers_only:
                continue

            composer = copy.deepcopy(composer_shell)
            composer["composerId"] = composer_id
            composer["name"] = title
            composer["createdAt"] = created_ms
            composer["lastUpdatedAt"] = ts
            composer["fullConversationHeadersOnly"] = headers_only
            composer["conversationMap"] = {}
            composer["text"] = ""
            composer["status"] = "completed"
            composer["hasLoaded"] = True
            composer["isAgentic"] = True
            composer["unifiedMode"] = "agent"
            composer["forceMode"] = "edit"
            _set_db(gcon, "cursorDiskKV", f"composerData:{composer_id}", composer)
            new_headers.append(_header(composer_id, title, created_ms, ts, header_tpl))
            upgraded += 1
            print(f"upgraded: {composer_id[:8]}... | {title[:50]} | bubbles={len(headers_only)}")

        headers_doc = _load_db(gcon, "ItemTable", "composer.composerHeaders") or {"allComposers": []}
        existing = [
            h
            for h in headers_doc.get("allComposers", [])
            if isinstance(h, dict) and h.get("composerId") not in {h2["composerId"] for h2 in new_headers}
        ]
        headers_doc["allComposers"] = existing + new_headers
        _set_db(gcon, "ItemTable", "composer.composerHeaders", headers_doc)

        ws_doc = _load_db(wcon, "ItemTable", "composer.composerData") or {}
        selected = [x for x in (ws_doc.get("selectedComposerIds") or []) if x not in LOCAL_IDS]
        for h in new_headers:
            cid = h["composerId"]
            if cid not in selected:
                selected.append(cid)
        ws_doc["selectedComposerIds"] = ["637a9452-f7c4-4d43-807d-9825b05ce062"] + selected[:20]
        ws_doc["lastFocusedComposerIds"] = ws_doc["selectedComposerIds"][:3]
        ws_doc.setdefault("hasMigratedComposerData", True)
        ws_doc.setdefault("hasMigratedMultipleComposers", True)
        _set_db(wcon, "ItemTable", "composer.composerData", ws_doc)

        gcon.commit()
        wcon.commit()
    except Exception:
        gcon.close()
        wcon.close()
        shutil.copy2(backup, GLOBAL_DB)
        shutil.copy2(ws_backup, WS_DB)
        raise
    finally:
        gcon.close()
        wcon.close()

    print(f"\nUpgraded {upgraded} chats. Backup: {backup}")
    print("Quit Cursor completely, reopen E:\\AI file.")
    return upgraded


if __name__ == "__main__":
    try:
        upgrade_all()
    except sqlite3.OperationalError as exc:
        if "database is locked" in str(exc).lower():
            raise SystemExit("Cursor is running. Quit Cursor fully, then rerun.") from exc
        raise
