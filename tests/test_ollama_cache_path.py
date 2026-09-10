"""The optional Ollama cache path must not fall back to shared host files."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.ollama_config import _sticky_ollama_url, remember_ollama_url


class OllamaCachePathTests(unittest.TestCase):
    def test_configured_cache_is_the_only_read_and_write_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "qa" / "ollama-url"
            with patch.dict(os.environ, {"OLLAMA_CACHE_PATH": str(cache), "OLLAMA_BASE_URL": ""}):
                # An absent isolated cache must not reuse a real workstation marker.
                with patch.object(Path, "is_file", autospec=True, return_value=False) as exists:
                    self.assertIsNone(_sticky_ollama_url())
                    exists.assert_called_once_with(cache)
                remember_ollama_url("http://127.0.0.1:22392/")
                self.assertEqual(cache.read_text(encoding="utf-8"), "http://127.0.0.1:22392\n")
                self.assertEqual(_sticky_ollama_url(), "http://127.0.0.1:22392")

    def test_failed_isolated_write_does_not_try_legacy_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "ollama-url"
            with (
                patch.dict(os.environ, {"OLLAMA_CACHE_PATH": str(cache)}),
                patch.object(Path, "write_text", autospec=True, side_effect=OSError("unwritable")) as write,
            ):
                remember_ollama_url("http://127.0.0.1:22392")
                write.assert_called_once_with(cache, "http://127.0.0.1:22392\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
