import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vengeance_soundboard.models import DISCORD_INPUT_PATTERN, LEGACY_DISCORD_INPUT_PATTERN, Macro, Sound
from vengeance_soundboard.storage import Library


class LibraryTests(unittest.TestCase):
    def test_legacy_discord_pattern_is_migrated_to_webrtc_mono(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            config = tmp_path / "config"
            config.mkdir()
            (config / "config.json").write_text(
                '{"discord_pattern": "' + LEGACY_DISCORD_INPUT_PATTERN.replace("\\", "\\\\") + '"}',
                encoding="utf-8",
            )
            library = Library(config, tmp_path / "data")
            self.assertEqual(library.settings.discord_pattern, DISCORD_INPUT_PATTERN)

    def test_api_key_can_come_from_environment(self):
        with tempfile.TemporaryDirectory() as raw, patch.dict(
            "os.environ", {"FREESOUND_API_KEY": "test-secret"}, clear=False
        ):
            tmp_path = Path(raw)
            library = Library(tmp_path / "config", tmp_path / "data")
            self.assertEqual(library.settings.freesound_token, "test-secret")

    def test_library_persists_settings_sounds_and_macros(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "source.wav"
            source.write_bytes(b"RIFF-test")
            library = Library(tmp_path / "config", tmp_path / "data")
            sound = library.add_local(source)
            library.settings.volume = 1.2
            library.macros.append(Macro("m1", "Combo", [sound.id], 100))
            library.save()

            loaded = Library(tmp_path / "config", tmp_path / "data")
            self.assertEqual(loaded.settings.volume, 1.2)
            self.assertEqual(loaded.sounds[0].name, "source")
            self.assertTrue(Path(loaded.sounds[0].local_path).is_file())
            self.assertEqual(loaded.macros[0].sound_ids, [sound.id])

    def test_upsert_preserves_download_and_user_state(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            library = Library(tmp_path / "config", tmp_path / "data")
            old = Sound(
                "remote-1",
                "Old",
                local_path="/tmp/audio.mp3",
                favorite=True,
                plays=3,
                cache_expires_at=123,
            )
            library.sounds.append(old)
            updated = Sound("remote-1", "New", preview_url="https://example.test/audio.mp3")
            library.upsert(updated)
            self.assertEqual(library.sounds[0].name, "New")
            self.assertEqual(library.sounds[0].local_path, "/tmp/audio.mp3")
            self.assertTrue(library.sounds[0].favorite)
            self.assertEqual(library.sounds[0].plays, 3)
            self.assertEqual(library.sounds[0].cache_expires_at, 123)

    def test_clear_cache_keeps_catalogue_and_personal_import(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            library = Library(tmp_path / "config", tmp_path / "data")
            cached_file = library.sounds_dir / "remote.mp3"
            cached_file.write_bytes(b"remote")
            personal_source = tmp_path / "personal.wav"
            personal_source.write_bytes(b"personal")
            remote = Sound(
                "remote-1",
                "Remote",
                local_path=str(cached_file),
                preview_url="https://example.test/remote.mp3",
                cache_expires_at=123,
            )
            personal = library.add_local(personal_source)
            library.sounds.append(remote)
            library.save()

            self.assertEqual(library.clear_cache(), 1)
            self.assertFalse(cached_file.exists())
            self.assertEqual(remote.local_path, "")
            self.assertEqual(remote.cache_expires_at, 0)
            self.assertTrue(Path(personal.local_path).exists())
            self.assertIs(library.by_id("remote-1"), remote)
