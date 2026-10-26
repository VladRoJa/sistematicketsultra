"""QA local sin acceso a credenciales, APIs ni producción."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.training.generate import (
    EXPECTED_ACK, export_video, load_storyboard, make_srt,
    srt_time, validate_codes, validate_target,
)

ROOT = Path(__file__).resolve().parents[1]


class TrainingV1Tests(unittest.TestCase):
    def test_reject_remote_and_unsafe_urls(self):
        bad_urls = (
            "https://suite.ultragym.com", "http://suite.ultragym.com:4200",
            "https://localhost:4200", "http://127.0.0.1",
            "http://localhost:4200/api", "http://127.0.0.1:4200/#/login",
            "http://user:pass@localhost:4200",
        )
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_target(url, EXPECTED_ACK)
        with self.assertRaises(ValueError):
            validate_target("http://127.0.0.1:4200", "SI")
        self.assertEqual(
            validate_target("http://127.0.0.1:4200/", EXPECTED_ACK),
            "http://127.0.0.1:4200",
        )

    def test_demo_codes_must_be_unique(self):
        for codes in (["a", "b"], ["a", "a", "c"], ["a", " ", "c"]):
            with self.assertRaises(ValueError):
                validate_codes(codes)
        validate_codes(["DM-1", "DM-2", "DM-3"])

    def test_storyboard_and_subtitles(self):
        story = load_storyboard(ROOT / "storyboards/tapizado_multiaparato.json")
        self.assertEqual(len(story), 9)
        self.assertEqual(srt_time(3661.125), "01:01:01,125")
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "sub.srt"
            make_srt([{"at": 0.0, "text": "Inicio"},
                      {"at": 3.0, "text": "Fin"}], 5.0, p)
            data = p.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:03,000", data)
            self.assertIn("00:00:03,000 --> 00:00:05,000", data)

    def test_export_mp4_without_mutating_suite(self):
        import shutil
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg no disponible")
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = base / "navegacion.webm"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                            "-i", "color=s=320x180:r=10:d=2",
                            "-c:v", "libvpx", str(raw)],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            scenes = [{"at": 0.0, "text": "Hola, Suite Ultra"}]
            make_srt(scenes, 2.0, base / "subtitulos.srt")
            output = export_video(raw, base, scenes, voice="none")
            self.assertTrue(output.is_file())
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "stream=codec_name", "-of", "json", str(output)],
                text=True, capture_output=True, check=True,
            )
            codecs = [x["codec_name"] for x in json.loads(probe.stdout)["streams"]]
            self.assertIn("h264", codecs)
            self.assertIn("mov_text", codecs)


if __name__ == "__main__":
    unittest.main()
