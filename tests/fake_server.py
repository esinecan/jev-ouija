import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jev_ouija.options import OPTION_IDS, QUESTION_ID

MODEL = "fake-jev-7"


def distribution(winner, weight=0.9, extra=None):
    rest = (1 - weight) / (len(OPTION_IDS) - 1)
    probabilities = {key: rest for key in OPTION_IDS}
    probabilities[winner] = weight
    if extra:
        probabilities.update(extra)
    return probabilities


def choice_payload(probabilities, choice=None, model=MODEL, usage=None):
    if choice is None:
        best = max(probabilities.values())
        choice = next(key for key in OPTION_IDS if probabilities.get(key) == best)
    return {
        "model": model,
        "answers": {
            QUESTION_ID: {
                "type": "choice",
                "choice": choice,
                "confidence": 0.5,
                "probabilities": probabilities,
            }
        },
        "usage": usage if usage is not None else {"input_tokens": 100, "output_tokens": 5},
    }


def winner(option_id, **kwargs):
    return (200, choice_payload(distribution(option_id), **kwargs), 0)


class FakeJev:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.headers = []
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                fake.requests.append((self.path, body))
                fake.headers.append(dict(self.headers))
                status, payload, delay = fake.script.pop(0) if fake.script else (500, {"detail": "script exhausted"}, 0)
                if delay:
                    time.sleep(delay)
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass

        return Handler
