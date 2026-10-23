from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from .models import Macro, Settings, Sound


APP_DIR = "vengeance-soundboard"


def _xdg_path(env_name: str, fallback: Path) -> Path:
    raw = os.environ.get(env_name)
    return Path(raw).expanduser() if raw else fallback


class Library:
    def __init__(self, config_dir: Path | None = None, data_dir: Path | None = None):
        home = Path.home()
        self.config_dir = config_dir or _xdg_path("XDG_CONFIG_HOME", home / ".config") / APP_DIR
        self.data_dir = data_dir or _xdg_path("XDG_DATA_HOME", home / ".local/share") / APP_DIR
        self.sounds_dir = self.data_dir / "sounds"
        self.config_file = self.config_dir / "config.json"
        self.library_file = self.data_dir / "library.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.sounds_dir.mkdir(parents=True, exist_ok=True)
        self.settings = Settings()
        self.sounds: list[Sound] = []
        self.macros: list[Macro] = []
        self.load()

    @staticmethod
    def _read_json(path: Path, fallback):
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError, TypeError):
            return fallback

    @staticmethod
    def _atomic_json(path: Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self) -> None:
        self.settings = Settings.from_dict(self._read_json(self.config_file, {}))
        raw = self._read_json(self.library_file, {})
        self.sounds = [Sound.from_dict(item) for item in raw.get("sounds", [])]
        self.macros = [Macro.from_dict(item) for item in raw.get("macros", [])]

    def save(self) -> None:
        self._atomic_json(self.config_file, self.settings.to_dict())
        self._atomic_json(
            self.library_file,
            {"sounds": [item.to_dict() for item in self.sounds], "macros": [item.to_dict() for item in self.macros]},
        )

    def add_local(self, source: Path, name: str | None = None, theme: str = "Perso") -> Sound:
        source = source.expanduser().resolve()
        extension = source.suffix.lower() or ".audio"
        sound_id = uuid.uuid4().hex
        destination = self.sounds_dir / f"{sound_id}{extension}"
        shutil.copy2(source, destination)
        sound = Sound(id=sound_id, name=name or source.stem, theme=theme, local_path=str(destination))
        self.sounds.append(sound)
        self.save()
        return sound

    def upsert(self, sound: Sound) -> Sound:
        for index, current in enumerate(self.sounds):
            if current.id == sound.id:
                # Preserve an already downloaded file when refreshing the online catalogue.
                if current.local_path and not sound.local_path:
                    sound.local_path = current.local_path
                sound.favorite = current.favorite
                sound.plays = current.plays
                self.sounds[index] = sound
                break
        else:
            self.sounds.append(sound)
        self.save()
        return sound

    def remove(self, sound: Sound) -> None:
        self.sounds = [item for item in self.sounds if item.id != sound.id]
        local = Path(sound.local_path) if sound.local_path else None
        if local and local.is_file() and self.sounds_dir in local.parents:
            local.unlink(missing_ok=True)
        for macro in self.macros:
            macro.sound_ids = [item for item in macro.sound_ids if item != sound.id]
        self.save()

    def by_id(self, sound_id: str) -> Sound | None:
        return next((item for item in self.sounds if item.id == sound_id), None)
