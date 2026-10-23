from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Sound:
    id: str
    name: str
    theme: str = "Perso"
    local_path: str = ""
    preview_url: str = ""
    source_url: str = ""
    author: str = ""
    license: str = ""
    duration: float = 0.0
    favorite: bool = False
    plays: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Sound":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in allowed if key in value})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Macro:
    id: str
    name: str
    sound_ids: list[str] = field(default_factory=list)
    delay_ms: int = 250

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Macro":
        return cls(
            id=str(value.get("id", "")),
            name=str(value.get("name", "Macro")),
            sound_ids=[str(item) for item in value.get("sound_ids", [])],
            delay_ms=int(value.get("delay_ms", 250)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Settings:
    volume: float = 0.8
    effect: str = "Aucun"
    auto_route: bool = True
    monitor_locally: bool = True
    discord_pattern: str = r"(?i)(WEBRTC VoiceEngine|Discord).*:input"
    passthrough_enabled: bool = False
    passthrough_source: str = ""
    freesound_token: str = ""
    window_width: int = 1120
    window_height: int = 760
    last_tab: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Settings":
        defaults = cls()
        kwargs = {}
        for key in cls.__dataclass_fields__:
            kwargs[key] = value.get(key, getattr(defaults, key))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
