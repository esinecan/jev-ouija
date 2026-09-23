import json
from datetime import datetime, timezone

SCHEMA_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class NullTrace:
    def write(self, event, **fields):
        pass

    def close(self):
        pass


class TraceWriter:
    def __init__(self, path):
        self._file = open(path, "x", encoding="utf-8", newline="\n")

    def write(self, event, **fields):
        record = {"event": event, **fields}
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self):
        self._file.close()
