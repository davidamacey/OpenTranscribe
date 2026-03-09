"""MediacmsProvider plugin for protected media downloads.

Handles password-protected MediaCMS installations configured via database
settings (Admin UI) or environment variables (legacy fallback).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.parse import urlunparse

import requests
from fastapi import HTTPException

from app.services.protected_media_providers import ProtectedMediaProvider

logger = logging.getLogger(__name__)


class MediacmsProvider(ProtectedMediaProvider):
    """ProtectedMediaProvider for MediaCMS-based sites.

    Hostnames are configured via the Admin UI (stored in database) or via the
    legacy MEDIACMS_ALLOWED_HOSTS environment variable (comma-separated list).

    SSL verification can be overridden per-host in the Admin UI or globally
    via MEDIACMS_VERIFY_SSL=false (env).
    """

    def _get_db_sources(self) -> list[dict]:
        """Load MediaCMS sources from database settings."""
        try:
            from app.db.base import SessionLocal
            from app.services.system_settings_service import get_media_sources

            db = SessionLocal()
            try:
                sources = get_media_sources(db)
                return [s for s in sources if s.get("provider_type") == "mediacms"]
            finally:
                db.close()
        except Exception:
            return []

    @property
    def allowed_hosts(self) -> set[str]:
        hosts: set[str] = set()
        # DB sources (primary)
        for s in self._get_db_sources():
            h = s.get("hostname", "").strip()
            if h:
                hosts.add(h)
        # Env fallback (legacy)
        raw = os.getenv("MEDIACMS_ALLOWED_HOSTS", "")
        for h in raw.split(","):
            h = h.strip()
            if h:
                hosts.add(h)
        return hosts

    def _get_verify_ssl_for_host(self, hostname: str) -> bool:
        """Get SSL verification setting for a specific host."""
        for s in self._get_db_sources():
            if s.get("hostname") == hostname:
                return bool(s.get("verify_ssl", True))
        # Env fallback
        return os.getenv("MEDIACMS_VERIFY_SSL", "true").lower() not in ("false", "0", "no")

    def _get_stored_credentials(self, hostname: str) -> tuple[str | None, str | None]:
        """Get stored credentials for a specific host from DB."""
        for s in self._get_db_sources():
            if s.get("hostname") == hostname:
                username = s.get("username") or None
                password = s.get("password") or None
                if username and password:
                    return username, password
        return None, None

    @property
    def verify_ssl(self) -> bool:
        """Global SSL verification fallback (used when host is unknown)."""
        return os.getenv("MEDIACMS_VERIFY_SSL", "true").lower() not in ("false", "0", "no")

    def can_handle(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                return False
            if parsed.netloc not in self.allowed_hosts:
                return False

            # Either ?m=<token> query param or /api/v1/media/<token> path
            query = parse_qs(parsed.query)
            if "m" in query and query["m"]:
                return True

            path_parts = [p for p in parsed.path.split("/") if p]
            return (
                len(path_parts) >= 3
                and path_parts[0] == "api"
                and path_parts[1] == "v1"
                and path_parts[2] == "media"
            )
        except Exception:
            return False

    # --- internal helpers -------------------------------------------------

    def _get_token_and_base_url(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)

        if parsed.netloc not in self.allowed_hosts:
            raise HTTPException(
                status_code=400,
                detail=f"Bad MediaCMS URL: {url}",
            )

        query = parse_qs(parsed.query)
        friendly_token: str | None = None

        # Primary: view URL with ?m=<token>
        if "m" in query and query["m"]:
            friendly_token = query["m"][0]
        else:
            # Fallback: /api/v1/media/<token>
            path_parts = [p for p in parsed.path.split("/") if p]
            if (
                len(path_parts) >= 3
                and path_parts[0] == "api"
                and path_parts[1] == "v1"
                and path_parts[2] == "media"
            ):
                friendly_token = path_parts[3] if len(path_parts) >= 4 else None

        if not friendly_token:
            raise HTTPException(
                status_code=400,
                detail="Missing media token (m query param or /api/v1/media/<token>)",
            )

        base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return friendly_token, base_url

    def _login_and_get_info(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Authenticate against MediaCMS and fetch media JSON."""
        media_user = username
        media_pass = password

        # Fall back to stored credentials if none provided in request
        if not media_user or not media_pass:
            parsed = urlparse(url)
            stored_user, stored_pass = self._get_stored_credentials(parsed.netloc)
            if not media_user:
                media_user = stored_user
            if not media_pass:
                media_pass = stored_pass

        if not media_user or not media_pass:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Credentials for this media source are not configured. "
                    "Either provide credentials in the request or configure "
                    "them in Admin Settings > Media Sources."
                ),
            )

        friendly_token, base_url = self._get_token_and_base_url(url)
        parsed = urlparse(url)
        host_verify_ssl = self._get_verify_ssl_for_host(parsed.netloc)
        auth_payload = {"username": media_user, "password": media_pass}

        try:
            login_resp = requests.post(
                url=f"{base_url}/api/v1/login",
                data=auth_payload,
                timeout=30,
                verify=host_verify_ssl,
            )
            login_resp.raise_for_status()
            token_data = login_resp.json()
            auth_token = token_data.get("token")
            if not auth_token:
                raise HTTPException(
                    status_code=502,
                    detail="MediaCMS login did not return an auth token",
                )

            headers = {
                "authorization": f"Token {auth_token}",
                "accept": "application/json",
            }
            info_resp = requests.get(
                url=f"{base_url}/api/v1/media/{friendly_token}",
                headers=headers,
                timeout=30,
                verify=host_verify_ssl,
            )
            info_resp.raise_for_status()
            info = info_resp.json()

        except HTTPException:
            raise
        except requests.exceptions.RequestException as e:
            # Re-wrap as HTTPException for consistency with FastAPI error handling
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch media information from MediaCMS: {e}",
            ) from e

        return friendly_token, base_url, info

    # --- ProtectedMediaProvider implementation ---------------------------

    def get_public_auth_config(self) -> dict[str, Any]:
        """Expose public auth configuration for this provider.

        Returns host list with auth requirements. Hosts with stored
        credentials indicate that credentials are optional (pre-configured).
        """
        hosts = sorted(self.allowed_hosts)
        if not hosts:
            return {}

        # Check which hosts have stored credentials
        db_sources = self._get_db_sources()
        hosts_with_creds = {
            s["hostname"] for s in db_sources if s.get("username") and s.get("password")
        }

        return {
            "hosts": hosts,
            "hosts_with_stored_credentials": sorted(hosts_with_creds),
            "auth_type": "user_password",
            "fields": [
                {
                    "name": "media_username",
                    "label": "Media username",
                    "type": "text",
                },
                {
                    "name": "media_password",
                    "label": "Media password",
                    "type": "password",
                },
            ],
        }

    def extract_info(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        friendly_token, base_url, info = self._login_and_get_info(
            url, username=username, password=password
        )

        title = info.get("title") or info.get("name") or friendly_token

        # MediaCMS may return relative thumbnail paths like
        # "/media/original/thumbnails/..."; normalize them to absolute URLs.
        raw_thumbnail = info.get("thumbnail_url")
        thumbnail_url: str | None = None
        if raw_thumbnail:
            parsed_thumb = urlparse(str(raw_thumbnail))
            if parsed_thumb.scheme:
                # Already an absolute URL
                thumbnail_url = str(raw_thumbnail)
            else:
                # Treat as path relative to the MediaCMS base URL
                thumbnail_url = urljoin(base_url, str(raw_thumbnail))

        media_info: dict[str, Any] = {
            "id": friendly_token,
            "title": title,
            "description": info.get("description"),
            "uploader": info.get("owner") or info.get("user"),
            "duration": info.get("duration"),
            "extractor": "mediacms",
            "thumbnail": thumbnail_url,
            "original_media_url": info.get("original_media_url"),
            "source": "mediacms",
            "original_url": url,
        }
        media_info["mediacms_raw"] = info
        media_info["mediacms_base_url"] = base_url
        return media_info

    def download(
        self,
        url: str,
        output_path: str,
        progress_callback: Callable[[int, str], None] | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        friendly_token, base_url, info = self._login_and_get_info(
            url, username=username, password=password
        )

        original_media_url = info.get("original_media_url")
        if not original_media_url:
            raise HTTPException(
                status_code=502,
                detail="MediaCMS media info is missing 'original_media_url'",
            )

        download_url = f"{base_url}{original_media_url}"
        parsed = urlparse(url)
        host_verify_ssl = self._get_verify_ssl_for_host(parsed.netloc)

        try:
            if progress_callback:
                progress_callback(20, "Downloading media from authenticated source...")

            with requests.get(
                download_url, stream=True, timeout=300, verify=host_verify_ssl
            ) as resp:
                resp.raise_for_status()
                total_bytes = int(resp.headers.get("Content-Length", "0")) or None
                downloaded = 0

                raw_title = info.get("title") or info.get("name") or friendly_token
                clean_title = re.sub(r"[^\w\-_\. ]", "_", str(raw_title))[:200]
                filename = clean_title if "." in clean_title else f"{clean_title}.mp4"

                file_path = os.path.join(output_path, filename)
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_bytes and total_bytes > 0:
                            progress = int(20 + (downloaded / total_bytes) * 40)
                            progress_callback(min(progress, 60), "Downloading media...")

        except HTTPException:
            raise
        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download media file from MediaCMS: {e}",
            ) from e

        # Build info dict (consistent with extract_info)
        media_info = self.extract_info(url, username=username, password=password)

        return {
            "file_path": file_path,
            "filename": filename,
            "info": media_info,
        }


# Default export for plugin loader
provider = MediacmsProvider()
