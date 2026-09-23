import io
import os
import subprocess
import sys
import tempfile
import unittest

from jev_ouija.cli import main
from jev_ouija.options import OPTIONS, OPTION_IDS
from jev_ouija.transport import endpoint

from fake_server import FakeJev, winner

ENV = {"JEV_API_KEY": "token"}


def call(argv, environ=ENV):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, environ=environ, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ConfigurationTests(unittest.TestCase):
    def test_rejects_bad_arguments_before_network(self):
        with FakeJev([]) as fake:
            cases = [
                ["", "--base-url", fake.base_url],
                ["   ", "--base-url", fake.base_url],
                ["q"],
                ["q", "--base-url", "ftp://x"],
                ["q", "--base-url", "http://user:pw@127.0.0.1:1"],
                ["q", "--base-url", fake.base_url, "--max-chars", "0"],
                ["q", "--base-url", fake.base_url, "--max-chars", "1.5"],
                ["q", "--base-url", fake.base_url, "--timeout", "-1"],
                ["q", "--base-url", fake.base_url, "--max-seconds", "nan"],
            ]
            for argv in cases:
                with self.subTest(argv=argv):
                    code, out, err = call(argv)
                    self.assertEqual(code, 1)
                    self.assertEqual(out, "")
                    self.assertIn("error", err)
            self.assertEqual(fake.requests, [])

    def test_missing_api_key(self):
        with FakeJev([]) as fake:
            code, _, err = call(["q", "--base-url", fake.base_url, "--api-key-env", "NOPE"], environ={})
        self.assertEqual(code, 1)
        self.assertIn("NOPE", err)
        self.assertEqual(fake.requests, [])

    def test_existing_trace_fails_before_network(self):
        with FakeJev([winner("STOP")]) as fake, tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "run.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("keep me\n")
            code, _, err = call(["q", "--base-url", fake.base_url, "--trace", path])
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "keep me\n")
        self.assertEqual(code, 1)
        self.assertIn("trace", err)
        self.assertEqual(fake.requests, [])

    def test_uncreatable_trace_fails_before_network(self):
        with FakeJev([winner("STOP")]) as fake, tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "missing", "run.jsonl")
            code, _, _ = call(["q", "--base-url", fake.base_url, "--trace", path])
        self.assertEqual(code, 1)
        self.assertEqual(fake.requests, [])

    def test_endpoint_handles_trailing_slash(self):
        self.assertEqual(endpoint("http://h:1"), "http://h:1/v1/systemone")
        self.assertEqual(endpoint("http://h:1/"), "http://h:1/v1/systemone")

    def test_custom_model_and_key_variable(self):
        with FakeJev([winner("STOP")]) as fake:
            code, _, _ = call(
                ["q", "--base-url", fake.base_url, "--model", "jev-2026-09", "--api-key-env", "OTHER"],
                environ={"OTHER": "abc"},
            )
        self.assertEqual(code, 0)
        self.assertEqual(fake.requests[0][1]["model"], "jev-2026-09")
        self.assertEqual(fake.headers[0]["Authorization"], "Bearer abc")


class OptionTests(unittest.TestCase):
    def test_mapping_is_complete_and_unique(self):
        chars = [char for _, char, _ in OPTIONS if char is not None]
        self.assertEqual(len(chars), len(set(chars)))
        self.assertEqual(len(OPTION_IDS), len(set(OPTION_IDS)))
        expected = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \n.,!?:;'\"-()/")
        self.assertEqual(set(chars), expected)
        self.assertEqual(OPTION_IDS[-1], "STOP")
        self.assertIn("LOWER_A", OPTION_IDS)
        self.assertIn("UPPER_A", OPTION_IDS)
        self.assertIn("DIGIT_0", OPTION_IDS)
        self.assertIn("PERIOD", OPTION_IDS)


class ProcessTests(unittest.TestCase):
    def test_installed_module_writes_raw_newline_to_stdout(self):
        script = [winner(key) for key in ("UPPER_H", "LOWER_I", "NEWLINE", "STOP")]
        with FakeJev(script) as fake:
            completed = subprocess.run(
                [sys.executable, "-m", "jev_ouija", "hello", "--base-url", fake.base_url],
                env={**os.environ, "JEV_API_KEY": "token"},
                capture_output=True,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, b"Hi\n")
        self.assertIn(b"stop after 4 requests", completed.stderr)


if __name__ == "__main__":
    unittest.main()
