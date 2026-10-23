import tempfile
import unittest
from pathlib import Path

from vengeance_soundboard.catalog import download_sound
from vengeance_soundboard.models import Sound


class FakeResponse:
    headers = {"Content-Length": "6", "Content-Type": "audio/mpeg"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, _chunk_size):
        return iter((b"abc", b"def"))


class FakeSession:
    def get(self, *_args, **_kwargs):
        return FakeResponse()


class DownloadTests(unittest.TestCase):
    def test_download_reports_progress(self):
        sound = Sound("remote-1", "Test", preview_url="https://example.test/test.mp3")
        events = []
        with tempfile.TemporaryDirectory() as raw:
            path = download_sound(sound, Path(raw), FakeSession(), lambda current, total: events.append((current, total)))
            self.assertEqual(path.read_bytes(), b"abcdef")
        self.assertEqual(events, [(0, 6), (3, 6), (6, 6)])
