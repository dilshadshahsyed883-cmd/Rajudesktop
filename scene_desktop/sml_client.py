"""Read-only authenticated SML V2 Editor API adapter for a local Windows editor.

SML is the source of truth: only server-approved/searchable media is eligible.
Never calls a mutation/reservation endpoint and never persists the API token.
Portable, no third-party HTTP dependencies, no shell execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError
import hashlib
import ipaddress
import json
import os
import re
import shutil
import tempfile
import threading

ID = re.compile(r"^(CLP|IMG)-[a-zA-Z0-9_-]{1,100}$")
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_IMAGE = 48 * 1024 * 1024
MAX_VIDEO = 256 * 1024 * 1024
MAX_INDEX_RESPONSE = 2 * 1024 * 1024
MAX_ITEMS = 100
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
IMAGE_MIME = {"image/png": ".png", "image/jpeg": ".jpg",
              "image/webp": ".webp", "image/bmp": ".bmp"}


class SMLError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SMLError("SML gateway redirected the request. Use an authorized Editor API URL, not the website login.")


def normalize_url(raw: str) -> str:
    """Origin plus optional reverse-proxy base path, NEVER query credentials."""
    url = str(raw).strip().rstrip("/")
    p = urlsplit(url)
    if (p.scheme not in {"http", "https"} or not p.hostname or
            p.username or p.password or p.query or p.fragment or
            "\\" in p.path or "//" in p.path or ".." in p.path or
            any(ord(c) < 33 or ord(c) > 126 for c in url) or
            p.path.endswith("/api/v1/media")):
        raise SMLError("Invalid SML Editor API base URL")
    if p.scheme == "http":
        try:
            host = ipaddress.ip_address(p.hostname)
            safe = (host.is_loopback or
                    host in ipaddress.ip_network("100.64.0.0/10") or
                    host in ipaddress.ip_network("fd7a:115c:a1e0::/48"))
        except ValueError:
            safe = p.hostname in {"localhost"}
        if not safe:
            raise SMLError("Plain HTTP is allowed only over loopback or a Tailscale address; use HTTPS otherwise")
    return url


@dataclass(frozen=True)
class SMLAsset:
    id: str
    kind: str
    name: str
    sha256: str
    keywords: tuple[str, ...]
    description: str
    source_id: str
    content_path: str
    duration_ms: int
    size_limit: int

    @classmethod
    def parse(cls, row: object) -> "SMLAsset":
        if not isinstance(row, dict):
            raise SMLError("Malformed SML search result")
        ident = row.get("id", "")
        kind = row.get("type", "")
        if not isinstance(ident, str) or not ID.fullmatch(ident):
            raise SMLError("SML result has invalid media ID")
        if kind not in ("video", "image") or ident[:3] != ("CLP" if kind == "video" else "IMG"):
            raise SMLError("SML media type/ID mismatch")
        path = f"/api/v1/media/{kind}/{quote(ident, safe='')}/content"
        # Ignore arbitrary URL hosts even if the server returns one.
        supplied = row.get("content_url", path)
        if supplied != path:
            raise SMLError("SML result contains unexpected content URL")
        digest = row.get("sha256", "")
        if not isinstance(digest, str) or not HASH.fullmatch(digest):
            raise SMLError("SML media lacks verified SHA-256")
        original = row.get("source_filename") or ident
        name = str(original).replace("\\", "/").split("/")[-1].strip()
        if not name or name in (".", ".."):
            name = ident
        tags = row.get("keywords") or []
        if not isinstance(tags, list):
            raise SMLError("Malformed SML keyword list")
        return cls(ident, kind, name[:180], digest.lower(),
                   tuple(str(x).strip()[:60] for x in tags[:40] if str(x).strip()),
                   str(row.get("description") or "")[:500],
                   str(row.get("source_id") or ident)[:128], path,
                   max(0, round(float(row.get("duration") or 0) * 1000)),
                   MAX_VIDEO if kind == "video" else MAX_IMAGE)


def choose_suffix(asset: SMLAsset, mime: str) -> str:
    if asset.kind == "video":
        return ".mp4"
    base = mime.split(";", 1)[0].strip().lower()
    if base in IMAGE_MIME:
        return IMAGE_MIME[base]
    ext = Path(asset.name).suffix.lower()
    if ext in ALLOWED_IMAGE_EXT:
        return ext
    raise SMLError("Unsupported SML image format (no verified content type)")


class SMLClient:
    def __init__(self, base_url: str, token: str, *, opener=None):
        self.url = normalize_url(base_url)
        self._token = str(token).strip()
        if not self._token or "\n" in self._token or "\r" in self._token:
            raise SMLError("SML Editor token required; never put it in the URL")
        self._opener = opener or build_opener(ProxyHandler({}), NoRedirect())

    def _open(self, path: str, *, query: dict | None = None, timeout: int = 20):
        if not path.startswith("/api/v1/media/") or not re.fullmatch(r"/[A-Za-z0-9_/\-]+", path):
            raise SMLError("Only allowlisted read-only SML API paths are supported")
        addr = self.url + path
        if query:
            addr += "?" + urlencode(query)
        req = Request(addr, method="GET", headers={
            "Accept": "application/json, video/mp4, image/*",
            "X-SML-Editor-Token": self._token,
            "User-Agent": "Rajudesktop-SML-ReadOnly/1",
        })
        try:
            return self._opener.open(req, timeout=timeout)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise SMLError("SML editor authorization failed. Check token/gateway access.") from None
            if exc.code == 404:
                raise SMLError("SML media unavailable or removed; refresh approved search") from None
            raise SMLError(f"SML request failed: HTTP {exc.code}") from None
        except URLError:
            raise SMLError("Cannot reach SML over the approved network route") from None

    def _json(self, path: str, query: dict | None = None) -> dict:
        with self._open(path, query=query) as response:
            if response.status != 200:
                raise SMLError("SML API did not return HTTP 200")
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise SMLError("SML gateway returned HTML/non-JSON; check API base URL")
            body = response.read(MAX_INDEX_RESPONSE + 1)
        if len(body) > MAX_INDEX_RESPONSE:
            raise SMLError("Oversized SML API response")
        try:
            result = json.loads(body)
        except (ValueError, UnicodeError):
            raise SMLError("Invalid SML API JSON") from None
        if not isinstance(result, dict):
            raise SMLError("Malformed SML API payload")
        return result

    def inventory(self) -> dict:
        result = self._json("/api/v1/media/inventory")
        if not isinstance(result.get("counts"), dict):
            raise SMLError("SML inventory format mismatch")
        return result["counts"]

    def search(self, query: str = "", kind: str = "all", limit: int = 100) -> list[SMLAsset]:
        if kind not in {"all", "image", "video"} or not 1 <= limit <= MAX_ITEMS:
            raise SMLError("Invalid SML media search filter")
        result = self._json("/api/v1/media/search", {
            "query": query[:200], "media_type": kind, "limit": limit, "semantic": "false"
        })
        items = result.get("items")
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise SMLError("Malformed SML approved-media list")
        parsed = [SMLAsset.parse(x) for x in items]
        if len({x.id for x in parsed}) != len(parsed):
            raise SMLError("Duplicate IDs in SML search results")
        return parsed

    def download(self, asset: SMLAsset, directory: str | Path,
                 stop: threading.Event | None = None,
                 progress=None) -> Path:
        """Atomic verified cache copy. Refuse excess body, redirects or wrong SHA."""
        cache = Path(directory).expanduser().resolve()
        cache.mkdir(parents=True, exist_ok=True)
        response = self._open(asset.content_path, timeout=180)
        scratch: Path | None = None
        try:
            with response:
                mime = response.headers.get("Content-Type", "")
                if mime.lower().startswith("text/html") or mime.lower().startswith("application/json"):
                    raise SMLError("SML returned a login/error page rather than approved media")
                suffix = choose_suffix(asset, mime)
                final = cache / (asset.id + "-" + asset.sha256[:16] + suffix)
                if final.is_file() and self._digest(final) == asset.sha256:
                    return final
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > asset.size_limit:
                    raise SMLError("SML asset exceeds safe local transfer limit")
                with tempfile.NamedTemporaryFile(dir=cache, prefix=".sml-", suffix=".part",
                                                 delete=False) as tmp:
                    scratch = Path(tmp.name)
                    total = 0
                    sha = hashlib.sha256()
                    while True:
                        if stop is not None and stop.is_set():
                            raise SMLError("SML download cancelled")
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > asset.size_limit:
                            raise SMLError("SML asset exceeds safe local transfer limit")
                        sha.update(block)
                        tmp.write(block)
                        if progress:
                            progress(total, int(declared) if declared and declared.isdigit() else 0)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                if total <= 0 or sha.hexdigest() != asset.sha256:
                    raise SMLError("SML SHA-256 mismatch or empty file; import rejected")
                if final.exists():
                    # Do not replace an unrelated user's file in the cache.
                    if self._digest(final) == asset.sha256:
                        return final
                    raise SMLError("Conflicting local SML cache file; no overwrite")
                os.replace(scratch, final)
                scratch = None
                return final
        finally:
            if scratch is not None:
                scratch.unlink(missing_ok=True)

    @staticmethod
    def _digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024*1024), b""):
                h.update(block)
        return h.hexdigest()
