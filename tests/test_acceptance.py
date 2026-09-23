import io
import json
import math
import os
import tempfile
import time
import unittest

from jev_ouija.cli import main
from jev_ouija.options import INSTRUCTIONS, OPTION_IDS, QUESTION_ID, criteria
from jev_ouija.transport import endpoint, post_json

from fake_server import MODEL, FakeJev, choice_payload, distribution, winner

SECRET = "sk-test-secret-4417"
ENV = {"JEV_API_KEY": SECRET}


class Run:
    def __init__(self, code, stdout, stderr, trace):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.trace = trace


def invoke(fake, *extra, prompt="Say hi", post=None, trace=True):
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "run.jsonl")
        argv = [prompt, "--base-url", fake.base_url if fake else "http://127.0.0.1:9", *extra]
        if trace:
            argv += ["--trace", path]
        out, err = io.StringIO(), io.StringIO()
        code = main(argv, environ=ENV, stdout=out, stderr=err, post=post)
        records = []
        if trace and os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                raw = handle.read()
            records = [json.loads(line) for line in raw.splitlines()]
    return Run(code, out.getvalue(), err.getvalue(), records)


class GenerationTests(unittest.TestCase):
    def test_scripted_sequence_emits_exact_text(self):
        script = [winner(key) for key in ("UPPER_H", "LOWER_I", "SPACE", "DIGIT_2", "NEWLINE", "STOP")]
        with FakeJev(script) as fake:
            run = invoke(fake)
        self.assertEqual(run.code, 0)
        self.assertEqual(run.stdout, "Hi 2\n")
        self.assertEqual(len(fake.requests), 6)
        prefixes = [body["state"]["answer_so_far"] for _, body in fake.requests]
        self.assertEqual(prefixes, ["", "H", "Hi", "Hi ", "Hi 2", "Hi 2\n"])
        for path, body in fake.requests:
            self.assertEqual(path, "/v1/systemone")
            self.assertEqual(body["model"], "jev-latest")
            self.assertEqual(body["state"]["prompt"], "Say hi")
            question = body["questions"][QUESTION_ID]
            self.assertEqual(question["type"], "choice")
            self.assertEqual(question["instructions"], INSTRUCTIONS)
            self.assertEqual(list(question["criteria"]), list(OPTION_IDS))
            self.assertEqual(question["criteria"], criteria())
        self.assertEqual(list(OPTION_IDS)[-1], "STOP")

    def test_immediate_stop_emits_nothing(self):
        with FakeJev([winner("STOP")]) as fake:
            run = invoke(fake)
        self.assertEqual(run.code, 0)
        self.assertEqual(run.stdout, "")
        self.assertEqual(run.trace[-1]["reason"], "stop")

    def test_exact_tie_follows_option_order(self):
        tie = distribution("UPPER_Q", weight=0.4, extra={"LOWER_B": 0.4})
        total = math.fsum(tie.values())
        tie = {key: value / total for key, value in tie.items()}
        tie["LOWER_B"] = tie["UPPER_Q"]
        script = [(200, choice_payload(tie, choice="UPPER_Q"), 0), winner("STOP")]
        with FakeJev(script) as fake:
            run = invoke(fake)
        self.assertEqual(run.stdout, "b")
        step = run.trace[1]
        self.assertEqual(step["server_choice"], "UPPER_Q")
        self.assertEqual(step["selected"], "LOWER_B")

    def test_character_tied_with_stop_emits_character(self):
        tie = distribution("STOP", weight=0.45, extra={"PERIOD": 0.45})
        tie = {key: (value if key in ("STOP", "PERIOD") else 0.1 / (len(OPTION_IDS) - 2)) for key, value in tie.items()}
        script = [(200, choice_payload(tie, choice="STOP"), 0), winner("STOP")]
        with FakeJev(script) as fake:
            run = invoke(fake)
        self.assertEqual(run.code, 0)
        self.assertEqual(run.stdout, ".")
        self.assertEqual(run.trace[1]["selected"], "PERIOD")
        self.assertEqual(run.trace[1]["server_choice"], "STOP")


class LimitTests(unittest.TestCase):
    def test_character_limit_stops_without_extra_request(self):
        script = [winner("LOWER_A") for _ in range(10)]
        with FakeJev(script) as fake:
            run = invoke(fake, "--max-chars", "3")
        self.assertEqual(run.code, 2)
        self.assertEqual(run.stdout, "aaa")
        self.assertEqual(len(fake.requests), 3)
        self.assertEqual(run.trace[-1]["reason"], "max_chars")

    def test_time_budget_bounds_slow_endpoint(self):
        script = [winner("LOWER_A"), (200, choice_payload(distribution("LOWER_B")), 5)]
        with FakeJev(script) as fake:
            began = time.monotonic()
            run = invoke(fake, "--max-seconds", "1", "--timeout", "30")
            took = time.monotonic() - began
        self.assertEqual(run.code, 2)
        self.assertEqual(run.stdout, "a")
        self.assertLess(took, 3)
        self.assertEqual(run.trace[-1]["reason"], "max_seconds")

    def test_request_timeout_below_budget_is_an_error(self):
        script = [(200, choice_payload(distribution("LOWER_B")), 3)]
        with FakeJev(script) as fake:
            run = invoke(fake, "--timeout", "0.5", "--max-seconds", "60")
        self.assertEqual(run.code, 1)
        self.assertEqual(run.trace[-1]["reason"], "request_timeout")


class FailureTests(unittest.TestCase):
    def assert_fails_after_prefix(self, bad, reason="invalid_response"):
        with FakeJev([winner("UPPER_O"), winner("LOWER_K"), bad]) as fake:
            run = invoke(fake)
        self.assertEqual(run.code, 1)
        self.assertEqual(run.stdout, "Ok")
        end = run.trace[-1]
        self.assertEqual(end["event"], "end")
        self.assertEqual(end["reason"], reason)
        self.assertEqual(end["answer"], "Ok")
        self.assertTrue(end["error"])
        self.assertIn("error:", run.stderr)
        return end

    def test_http_failure(self):
        end = self.assert_fails_after_prefix((500, {"detail": "boom"}, 0), reason="http_error")
        self.assertIn("HTTP 500", end["error"])

    def test_missing_probability_key(self):
        probabilities = distribution("LOWER_A")
        probabilities.pop("SLASH")
        self.assert_fails_after_prefix((200, choice_payload(probabilities, choice="LOWER_A"), 0))

    def test_extra_probability_key(self):
        probabilities = distribution("LOWER_A", weight=0.8)
        probabilities["EMOJI"] = 0.0
        self.assert_fails_after_prefix((200, choice_payload(probabilities, choice="LOWER_A"), 0))

    def test_out_of_range_value(self):
        probabilities = distribution("LOWER_A")
        probabilities["LOWER_B"] = -0.01
        self.assert_fails_after_prefix((200, choice_payload(probabilities, choice="LOWER_A"), 0))

    def test_non_numeric_value(self):
        probabilities = distribution("LOWER_A")
        probabilities["LOWER_B"] = "0.1"
        self.assert_fails_after_prefix((200, choice_payload(probabilities, choice="LOWER_A"), 0))

    def test_non_finite_value(self):
        probabilities = distribution("LOWER_A")
        raw = json.dumps(choice_payload(probabilities, choice="LOWER_A"))
        raw = raw.replace(json.dumps(probabilities["LOWER_B"]), "NaN", 1).encode("utf-8")
        self.assert_fails_after_prefix((200, raw, 0))

    def test_invalid_total(self):
        probabilities = distribution("LOWER_A", weight=0.5)
        probabilities["LOWER_B"] = 0.3
        self.assert_fails_after_prefix((200, choice_payload(probabilities, choice="LOWER_A"), 0))

    def test_total_within_tolerance_is_accepted(self):
        probabilities = distribution("LOWER_A")
        probabilities["LOWER_A"] += 0.0009
        with FakeJev([(200, choice_payload(probabilities), 0), winner("STOP")]) as fake:
            run = invoke(fake)
        self.assertEqual((run.code, run.stdout), (0, "a"))

    def test_inconsistent_server_choice(self):
        self.assert_fails_after_prefix((200, choice_payload(distribution("LOWER_A"), choice="LOWER_Z"), 0))

    def test_non_json_body(self):
        self.assert_fails_after_prefix((200, b"<html>oops</html>", 0))

    def test_ctrl_c_preserves_partial_work(self):
        with FakeJev([winner("UPPER_O"), winner("LOWER_K")]) as fake:
            url = endpoint(fake.base_url)
            calls = []

            def post(body, timeout):
                calls.append(body)
                if len(calls) == 3:
                    raise KeyboardInterrupt
                return post_json(url, body, SECRET, timeout)

            run = invoke(fake, post=post)
        self.assertEqual(run.code, 130)
        self.assertEqual(run.stdout, "Ok")
        self.assertEqual(run.trace[-1]["reason"], "interrupted")
        self.assertEqual(run.trace[-1]["answer"], "Ok")


class ObservabilityTests(unittest.TestCase):
    def test_output_trace_and_credentials(self):
        script = [
            winner("UPPER_H", model="model-a"),
            winner("LOWER_I", model="model-a", usage={}),
            (500, {"detail": f"server rejected key {SECRET}"}, 0),
        ]
        with FakeJev(script) as fake:
            run = invoke(fake)
        self.assertEqual(run.stdout, "Hi")
        self.assertNotIn("step", run.stdout)
        events = [record["event"] for record in run.trace]
        self.assertEqual(events, ["start", "step", "step", "end"])
        start = run.trace[0]
        self.assertEqual(start["schema_version"], 1)
        self.assertEqual([item["id"] for item in start["options"]], list(OPTION_IDS))
        self.assertEqual(start["limits"], {"max_chars": 300, "timeout": 30.0, "max_seconds": 300.0})
        steps = run.trace[1:3]
        self.assertEqual("".join(step["emitted"] for step in steps), run.stdout)
        self.assertEqual([step["prefix"] for step in steps], ["", "H"])
        self.assertEqual({step["model"] for step in steps}, {"model-a"})
        self.assertEqual(steps[0]["usage"], {"input_tokens": 100, "output_tokens": 5})
        self.assertIn("step 1 UPPER_H", run.stderr)
        self.assertIn("usage in=100 out=5", run.stderr)
        self.assertIn("step 2 LOWER_I", run.stderr)
        self.assertIn("model model-a", run.stderr)
        self.assertEqual(fake.headers[0]["Authorization"], f"Bearer {SECRET}")
        dumped = json.dumps(run.trace)
        for text in (run.stdout, run.stderr, dumped):
            self.assertNotIn(SECRET, text)
        self.assertIn("***", run.trace[-1]["error"])

    def test_stop_step_records_null_emission(self):
        with FakeJev([winner("STOP")]) as fake:
            run = invoke(fake)
        self.assertIsNone(run.trace[1]["emitted"])
        self.assertEqual(run.trace[1]["model"], MODEL)


if __name__ == "__main__":
    unittest.main()
