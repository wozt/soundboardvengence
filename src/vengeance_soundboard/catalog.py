from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from .models import Sound


FREESOUND_SEARCH = "https://freesound.org/apiv2/search/"
THEME_QUERIES = {
    "Populaires": "meme OR funny OR reaction",
    "Réactions": "reaction OR laugh OR applause OR fail",
    "Gaming": "game OR arcade OR victory OR defeat",
    "Cinéma": "cinematic OR dramatic OR suspense",
    "Ambiance": "ambient OR nature OR city",
}


class CatalogError(RuntimeError):
    pass


class FreesoundCatalog:
    def __init__(self, token: str, session: requests.Session | None = None):
        self.token = token.strip()
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "VengeanceSoundboard/0.1"})

    def search(self, theme: str, page_size: int = 18) -> list[Sound]:
        if not self.token:
            raise CatalogError("Ajoute une clé API Freesound dans les réglages.")
        query = THEME_QUERIES.get(theme, theme)
        params = {
            "query": query,
            "sort": "rating_desc",
            "page_size": max(1, min(page_size, 50)),
            "filter": "duration:[0 TO 30]",
            "fields": "id,name,username,duration,license,previews,url",
        }
        try:
            response = self.session.get(
                FREESOUND_SEARCH,
                params=params,
                headers={"Authorization": f"Token {self.token}"},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise CatalogError(f"Catalogue indisponible : {error}") from error
        return [self._convert(item, theme) for item in payload.get("results", [])]

    @staticmethod
    def _convert(item: dict, theme: str) -> Sound:
        previews = item.get("previews") or {}
        preview = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or previews.get("preview-hq-ogg") or ""
        return Sound(
            id=f"freesound-{item['id']}",
            name=str(item.get("name") or f"Son {item['id']}"),
            theme=theme,
            preview_url=preview,
            source_url=str(item.get("url") or ""),
            author=str(item.get("username") or ""),
            license=str(item.get("license") or ""),
            duration=float(item.get("duration") or 0),
        )


def safe_extension(url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".mp3", ".ogg", ".wav", ".flac", ".opus", ".m4a", ".aac"}:
        return suffix
    guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) if content_type else None
    return guessed if guessed in {".mp3", ".ogg", ".wav", ".flac", ".opus", ".m4a", ".aac"} else ".mp3"


def download_sound(sound: Sound, sounds_dir: Path, session: requests.Session | None = None) -> Path:
    url = sound.preview_url
    if not url:
        raise CatalogError("Ce son ne fournit pas de fichier de préécoute téléchargeable.")
    if urlparse(url).scheme not in {"http", "https"}:
        raise CatalogError("L’URL doit utiliser HTTP ou HTTPS.")
    client = session or requests.Session()
    try:
        with client.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            declared_size = int(response.headers.get("Content-Length", "0") or 0)
            if declared_size > 50 * 1024 * 1024:
                raise CatalogError("Le fichier dépasse la limite de 50 Mo.")
            extension = safe_extension(url, response.headers.get("Content-Type", ""))
            stable_id = re.sub(r"[^a-zA-Z0-9_-]", "_", sound.id) or hashlib.sha256(url.encode()).hexdigest()[:20]
            destination = sounds_dir / f"{stable_id}{extension}"
            temporary = destination.with_suffix(destination.suffix + ".part")
            with temporary.open("wb") as handle:
                total = 0
                for chunk in response.iter_content(64 * 1024):
                    if chunk:
                        total += len(chunk)
                        if total > 50 * 1024 * 1024:
                            raise CatalogError("Le fichier dépasse la limite de 50 Mo.")
                        handle.write(chunk)
            temporary.replace(destination)
            return destination
    except (requests.RequestException, OSError) as error:
        raise CatalogError(f"Téléchargement impossible : {error}") from error
