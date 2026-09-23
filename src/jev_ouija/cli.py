import argparse
import os
import sys
import urllib.parse

from . import __version__
from .generator import EXIT_ERROR, EXIT_INTERRUPT, Config, run
from .trace import NullTrace, TraceWriter
from .transport import endpoint, post_json


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be positive: {text!r}")
    return value


def _positive_float(text):
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not value > 0 or value == float("inf"):
        raise argparse.ArgumentTypeError(f"must be a positive finite number: {text!r}")
    return value


def build_parser():
    parser = _Parser(
        prog="jev-ouija",
        description="Generate text one character at a time from Jev choice questions.",
        epilog="Exit codes: 0 model chose STOP, 2 character or time limit, 1 error, 130 Ctrl+C. "
        "A trace file contains the prompt and the generated text.",
    )
    parser.add_argument("prompt", help="question or instruction to answer")
    parser.add_argument("--base-url", required=True, help="API origin; /v1/systemone is appended")
    parser.add_argument("--model", default="jev-latest", help="model name (default: jev-latest)")
    parser.add_argument("--api-key-env", default="JEV_API_KEY", help="environment variable holding the bearer token")
    parser.add_argument("--max-chars", type=_positive_int, default=300, help="maximum emitted characters (default: 300)")
    parser.add_argument("--timeout", type=_positive_float, default=30.0, help="per-request timeout in seconds (default: 30)")
    parser.add_argument("--max-seconds", type=_positive_float, default=300.0, help="whole-run time limit in seconds (default: 300)")
    parser.add_argument("--trace", help="new UTF-8 JSONL trace file; must not exist")
    parser.add_argument("--version", action="version", version=f"jev-ouija {__version__}")
    return parser


def _check_base_url(base_url):
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UsageError(f"--base-url must be an http or https origin: {base_url!r}")
    if parts.username or parts.password:
        raise UsageError("--base-url must not contain credentials; use --api-key-env")


def main(argv=None, environ=None, stdout=None, stderr=None, post=None):
    environ = os.environ if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        args = build_parser().parse_args(argv)
        if not args.prompt.strip():
            raise UsageError("prompt must be nonempty")
        _check_base_url(args.base_url)
        api_key = environ.get(args.api_key_env, "")
        if not api_key:
            raise UsageError(f"environment variable {args.api_key_env} is unset or empty")
    except UsageError as error:
        stderr.write(f"jev-ouija: error: {error}\n")
        return EXIT_ERROR
    try:
        trace = TraceWriter(args.trace) if args.trace else NullTrace()
    except OSError as error:
        stderr.write(f"jev-ouija: error: cannot create trace file {args.trace!r}: {error.strerror or error}\n")
        return EXIT_ERROR
    url = endpoint(args.base_url)
    if post is None:
        def post(body, timeout):
            return post_json(url, body, api_key, timeout)
    config = Config(
        prompt=args.prompt,
        base_url=args.base_url,
        model=args.model,
        max_chars=args.max_chars,
        timeout=args.timeout,
        max_seconds=args.max_seconds,
        secrets=(api_key,),
    )
    try:
        result = run(config, post, trace, stdout, stderr)
    finally:
        trace.close()
    models = ", ".join(sorted(set(result.models))) or "none"
    stderr.write(
        f"\njev-ouija: {result.reason} after {result.requests} requests, "
        f"{len(result.answer)} characters, {result.elapsed:.2f}s, model {models}\n"
    )
    if result.error:
        stderr.write(f"jev-ouija: error: {result.error}\n")
    return result.exit_code


def entry():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        code = main()
    except KeyboardInterrupt:
        sys.stderr.write("\njev-ouija: interrupted\n")
        code = EXIT_INTERRUPT
    sys.exit(code)
