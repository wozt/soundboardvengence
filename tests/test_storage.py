import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vengeance_soundboard.models import Macro, Sound
from vengeance_soundboard.storage import Library


class LibraryTests(unittest.TestCase):
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
            old = Sound("remote-1", "Old", local_path="/tmp/audio.mp3", favorite=True, plays=3)
            library.sounds.append(old)
            updated = Sound("remote-1", "New", preview_url="https://example.test/audio.mp3")
            library.upsert(updated)
            self.assertEqual(library.sounds[0].name, "New")
            self.assertEqual(library.sounds[0].local_path, "/tmp/audio.mp3")
            self.assertTrue(library.sounds[0].favorite)
            self.assertEqual(library.sounds[0].plays, 3)
