"""MediacmsProvider plugin for protected media downloads.

Handles password-protected MediaCMS installations configured via environment.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse, urlunparse, urljoin

import requests
from fastapi import HTTPException

from app.services.protected_media_providers import ProtectedMediaProvider


class MediacmsProvider(ProtectedMediaProvider):
    """ProtectedMediaProvider for MediaCMS-based sites.

    Hostnames are configured via the MEDIACMS_ALLOWED_HOSTS environment
    variable (comma-separated list, e.g. "media.example.com,mediacms.internal").
    """

    @property
    def allowed_hosts(self) -> set[str]:
        raw = os.getenv("MEDIACMS_ALLOWED_HOSTS", "")
        return {h.strip() for h in raw.split(",") if h.strip()}

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
            if len(path_parts) >= 3 and path_parts[0] == "api" and path_parts[1] == "v1" and path_parts[2] == "media":
                return True

            return False
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
        friendly_token: Optional[str] = None

        # Primary: view URL with ?m=<token>
        if "m" in query and query["m"]:
            friendly_token = query["m"][0]
        else:
            # Fallback: /api/v1/media/<token>
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) >= 3 and path_parts[0] == "api" and path_parts[1] == "v1" and path_parts[2] == "media":
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
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Authenticate against MediaCMS and fetch media JSON."""
        media_user = username
        media_pass = password

        if not media_user or not media_pass:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Credentials for protected media are not configured. "
                    "Either provide media_username/media_password in the request."
                ),
            )

        friendly_token, base_url = self._get_token_and_base_url(url)
        auth_payload = {"username": media_user, "password": media_pass}

        try:
            login_resp = requests.post(
                url=f"{base_url}/api/v1/login",
                data=auth_payload,
                timeout=30,
                verify=False,
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
                verify=False,
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

        Currently uses username/password for all configured hosts.
        """
        hosts = sorted(self.allowed_hosts)
        if not hosts:
            return {}
        return {
            "hosts": hosts,
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
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        friendly_token, base_url, info = self._login_and_get_info(
            url, username=username, password=password
        )

        title = info.get("title") or info.get("name") or friendly_token

        # MediaCMS may return relative thumbnail paths like
        # "/media/original/thumbnails/..."; normalize them to absolute URLs.
        raw_thumbnail = info.get("thumbnail_url")
        thumbnail_url: Optional[str] = None
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
        progress_callback: Optional[Callable[[int, str], None]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
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

        try:
            if progress_callback:
                progress_callback(20, "Downloading media from authenticated source...")

            with requests.get(download_url, stream=True, timeout=300, verify=False) as resp:
                resp.raise_for_status()
                total_bytes = int(resp.headers.get("Content-Length", "0")) or None
                downloaded = 0

                raw_title = info.get("title") or info.get("name") or friendly_token
                clean_title = re.sub(r"[^\w\-_\. ]", "_", str(raw_title))[:200]
                if "." in clean_title:
                    filename = clean_title
                else:
                    filename = f"{clean_title}.mp4"

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
