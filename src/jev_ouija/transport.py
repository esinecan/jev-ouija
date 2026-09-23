import json
import socket
import urllib.error
import urllib.request


class TransportError(Exception):
    def __init__(self, reason, message, status=None):
        super().__init__(message)
        self.reason = reason
        self.status = status


def endpoint(base_url):
    return base_url.rstrip("/") + "/v1/systemone"


def post_json(url, body, api_key, timeout):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        excerpt = error.read(500).decode("utf-8", "replace")
        raise TransportError("http_error", f"HTTP {error.code}: {excerpt}", error.code) from None
    except (TimeoutError, socket.timeout) as error:
        raise TransportError("request_timeout", f"request timed out after {timeout:.2f}s") from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise TransportError("request_timeout", f"request timed out after {timeout:.2f}s") from None
        raise TransportError("transport_error", f"connection failed: {error.reason}") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransportError("invalid_response", f"response is not JSON: {error}") from None
