"""Optional YouTube uploader for local Short Studio, using official desktop OAuth.

No upload starts without the operator pressing Start. A network failure after
videos.insert is marked UNCERTAIN and is never retried automatically.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .core import Store, file_hash, utc_now

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
PKT = timezone(timedelta(hours=5))
VIDEO_CATEGORY = {"Entertainment": "24", "Music": "10", "People & Blogs": "22",
                  "Gaming": "20", "Education": "27", "Sports": "17"}
SLOT_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")


def google_client():
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError("Install google-api-python-client, google-auth-oauthlib and google-auth") from exc
    return build, MediaFileUpload, InstalledAppFlow, Credentials, Request


def connect_channel(store: Store, client_secret: str) -> tuple[str, str]:
    """Desktop OAuth popup. The user chooses a YouTube channel in their browser."""
    if not Path(client_secret).is_file():
        raise FileNotFoundError("Choose Google OAuth Desktop client JSON")
    build, _, flow_type, _, _ = google_client()
    flow = flow_type.from_client_secrets_file(client_secret, scopes=SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True,
                                  authorization_prompt_message="Open this URL to connect YouTube: {url}",
                                  prompt="select_account consent")
    api = build("youtube", "v3", credentials=creds, cache_discovery=False)
    result = api.channels().list(part="snippet", mine=True).execute()
    items = result.get("items") or []
    if not items:
        raise RuntimeError("Authenticated Google account has no accessible YouTube channel")
    channel = items[0]
    channel_id = str(channel["id"])
    label = str(channel.get("snippet", {}).get("title") or channel_id)
    auth_dir = store.root / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    token_file = auth_dir / f"{channel_id}.json"
    tmp = token_file.with_suffix(".tmp")
    tmp.write_text(creds.to_json(), encoding="utf-8")
    os.replace(tmp, token_file)
    with store.db() as conn:
        conn.execute("INSERT INTO channels(id,label,token_file) VALUES(?,?,?) "
                     "ON CONFLICT(id) DO UPDATE SET label=excluded.label,token_file=excluded.token_file",
                     (channel_id, label, str(token_file)))
    return channel_id, label


def load_authenticated_channel(token_file: str):
    build, _, _, creds_type, request_type = google_client()
    path = Path(token_file)
    creds = creds_type.from_authorized_user_file(str(path), scopes=SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(request_type())
        tmp = path.with_suffix(".tmp")
        tmp.write_text(creds.to_json(), encoding="utf-8")
        os.replace(tmp, path)
    if not creds.valid:
        raise RuntimeError("YouTube authorization expired. Reconnect this channel.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def create_group(store: Store, name: str, channel_ids: list[str]) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Group name required (max 80 characters)")
    if not channel_ids:
        raise ValueError("Select at least one connected channel")
    key = uuid.uuid4().hex
    with store.db() as conn:
        for ch in channel_ids:
            if not conn.execute("SELECT 1 FROM channels WHERE id=?", (ch,)).fetchone():
                raise ValueError("Unknown channel: " + ch)
        conn.execute("INSERT INTO groups(id,name) VALUES(?,?)", (key, name))
        conn.executemany("INSERT INTO memberships(group_id,channel_id) VALUES(?,?)",
                         [(key, ch) for ch in set(channel_ids)])
    return key


def create_profile(store: Store, name: str, group_id: str, folder: str,
                   title: str, description: str, category: str = "22",
                   privacy: str = "private", daily_limit: int = 4,
                   schedule_pkt: str = "12:00", delete_after: bool = True) -> str:
    if not name.strip() or len(name) > 100:
        raise ValueError("Profile name required")
    store.folder_path(folder)
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError("Invalid privacy")
    if not (1 <= daily_limit <= 20):
        raise ValueError("Daily channel limit must be 1-20")
    if not SLOT_RE.fullmatch(schedule_pkt):
        raise ValueError("Schedule must be 24-hour HH:MM (PKT)")
    if not category.isdigit():
        raise ValueError("Category must be numeric YouTube category ID")
    with store.db() as conn:
        if not conn.execute("SELECT 1 FROM memberships WHERE group_id=? LIMIT 1", (group_id,)).fetchone():
            raise ValueError("Choose a group with connected channels")
        key = uuid.uuid4().hex
        conn.execute("""INSERT INTO profiles(
          id,name,group_id,folder,title,description,category,privacy,
          daily_limit,schedule_pkt,delete_after) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          (key, name.strip(), group_id, folder, title.strip(),
           description.strip(), category, privacy, daily_limit,
           schedule_pkt, int(delete_after)))
    return key


def profiles(store: Store):
    with store.db() as conn:
        return [dict(zip(("id","name","group_id","folder","title","description","category",
                          "privacy","daily_limit","schedule_pkt","delete_after","group_name","channels"), row))
                for row in conn.execute("""SELECT p.id,p.name,p.group_id,p.folder,p.title,p.description,
                p.category,p.privacy,p.daily_limit,p.schedule_pkt,p.delete_after,g.name,
                (SELECT COUNT(*) FROM memberships m WHERE m.group_id=p.group_id)
                FROM profiles p JOIN groups g ON p.group_id=g.id ORDER BY p.rowid DESC""")]


def upload_rows(store: Store):
    with store.db() as conn:
        return [dict(zip(("id","channel_id","file_path","state","youtube_id","error","profile_id"), r))
                for r in conn.execute("""SELECT id,channel_id,file_path,state,youtube_id,error,profile_id
                   FROM uploads ORDER BY attempted DESC LIMIT 500""")]


def enqueue_profile(store: Store, profile_id: str) -> int:
    p = next((p for p in profiles(store) if p["id"] == profile_id), None)
    if not p:
        raise ValueError("Choose a valid uploader profile")
    paths = store.list_mp4(p["folder"])
    if not paths:
        raise ValueError("Selected folder has no MP4 files")
    with store.db() as conn:
        channels = [r[0] for r in conn.execute(
            "SELECT channel_id FROM memberships WHERE group_id=?", (p["group_id"],))]
        if not channels:
            raise ValueError("Selected group is empty")
        total = 0
        for path in paths:
            digest = file_hash(path)
            for channel in channels:
                key = uuid.uuid4().hex
                cur = conn.execute("""INSERT OR IGNORE INTO uploads(
                    id,channel_id,sha256,file_path,profile_id,state,attempted,updated)
                    VALUES(?,?,?,?,?,'queued',?,?)""",
                    (key, channel, digest, str(path), profile_id, utc_now(), utc_now()))
                total += cur.rowcount
    return total


def find_publish_slot(store: Store, profile: dict, channel_id: str,
                      now: datetime | None = None) -> datetime:
    """Allocate one scheduled-public slot per channel/day, bounded by daily limit."""
    current = (now or datetime.now(timezone.utc)).astimezone(PKT)
    hour, minute = map(int, profile["schedule_pkt"].split(":"))
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current + timedelta(minutes=20):
        candidate += timedelta(days=1)
    with store.db() as conn:
        for _ in range(365):
            day = candidate.date().isoformat()
            # Reserve future publish days before attempting the API.
            # Uncertain uploads keep their slot until manually reconciled.
            existing = conn.execute("""SELECT COUNT(*) FROM uploads
              WHERE channel_id=? AND publish_day_pkt=?""", (channel_id, day)).fetchone()[0]
            if existing < int(profile["daily_limit"]):
                return (candidate + timedelta(minutes=existing * 5)).astimezone(timezone.utc)
            candidate += timedelta(days=1)
    raise RuntimeError("No publish slot available")


def _upload(api, path: Path, profile: dict, publish_at: datetime | None,
            progress: Callable[[str], None]):
    _, media_type, _, _, _ = google_client()
    title = profile["title"] or path.stem
    title = title.replace("{filename}", path.stem)[:100]
    body = {"snippet": {"title": title,
                        "description": profile["description"].replace("{filename}", path.stem)[:5000],
                        "categoryId": profile["category"]},
            "status": {"privacyStatus": profile["privacy"], "selfDeclaredMadeForKids": False}}
    if publish_at is not None:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at.isoformat().replace("+00:00", "Z")
    request = api.videos().insert(part="snippet,status", body=body,
                    media_body=media_type(str(path), chunksize=8 * 1024 * 1024,
                                          resumable=True, mimetype="video/mp4"))
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress(f"Uploading {path.name}: {int(status.progress() * 100)}%")
    video_id = response.get("id", "")
    if not video_id:
        raise RuntimeError("YouTube did not return video ID. Verify manually before retrying.")
    return video_id


def upload_pending(store: Store, progress: Callable[[str], None] = lambda _: None,
                   limit: int = 500) -> int:
    """Serial uploader. A claimed row is never automatically retried after ambiguity."""
    uploaded = 0
    with store.db() as conn:
        conn.execute("UPDATE uploads SET state='uncertain',error='Interrupted previous upload; verify in YouTube Studio' "
                     "WHERE state='uploading'")
    for _ in range(limit):
        with store.db() as conn:
            row = conn.execute("""SELECT u.id,u.channel_id,u.file_path,u.profile_id,c.token_file
              FROM uploads u JOIN channels c ON u.channel_id=c.id
              WHERE u.state='queued' ORDER BY u.attempted LIMIT 1""").fetchone()
            if not row:
                break
            uid, cid, path_text, profile_id, token = row
            conn.execute("UPDATE uploads SET state='uploading',updated=? WHERE id=? AND state='queued'",
                         (utc_now(), uid))
        path = Path(path_text)
        p = next((x for x in profiles(store) if x["id"] == profile_id), None)
        if not p or not path.is_file():
            with store.db() as conn:
                conn.execute("UPDATE uploads SET state='failed',error=?,updated=? WHERE id=?",
                             ("Profile or local MP4 no longer exists", utc_now(), uid))
            continue
        progress(f"Channel {cid}: {path.name}")
        try:
            api = load_authenticated_channel(token)
            publish_at = find_publish_slot(store, p, cid) if p["privacy"] == "public" else None
            if publish_at is not None:
                day = publish_at.astimezone(PKT).date().isoformat()
                with store.db() as conn:
                    conn.execute("UPDATE uploads SET publish_day_pkt=? WHERE id=?", (day, uid))
            video_id = _upload(api, path, p, publish_at, progress)
        except Exception as exc:
            with store.db() as conn:
                conn.execute("UPDATE uploads SET state='uncertain',error=?,updated=? WHERE id=?",
                             (str(exc)[:600], utc_now(), uid))
            progress("Upload outcome uncertain. Inspect YouTube Studio: " + str(exc)[:150])
            break  # halt rather than repeatedly use a potentially invalid credential
        with store.db() as conn:
            conn.execute("UPDATE uploads SET state='uploaded',youtube_id=?,error='',updated=? WHERE id=?",
                         (video_id, utc_now(), uid))
            # Delete only studio-managed MP4 when ALL known channel rows succeeded.
            unfinished = conn.execute("""SELECT COUNT(*) FROM uploads
               WHERE file_path=? AND state!='uploaded'""", (str(path),)).fetchone()[0]
            owner = p["delete_after"] and path.parent.resolve() == store.folder_path(p["folder"]).resolve()
            if owner and unfinished == 0 and path.is_file() and not path.is_symlink():
                # Leave render/job history and upload record intact; remove only final MP4.
                path.unlink()
        uploaded += 1
        progress(f"Uploaded {path.name} -> {video_id}")
    return uploaded
