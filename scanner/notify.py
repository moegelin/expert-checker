"""ntfy push (docs/plan.md §2 and §5). The topic is a secret: NTFY_TOPIC in the environment
(phone: ~/.expert-checker.env), never in the repo. A push must never fail a run, so `send` never raises.
"""

import http.client
import json
import os
import urllib.error
import urllib.request

DEFAULT_SERVER = "https://ntfy.sh"
TIMEOUT = 15
PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5, "max": 5}


def urllib_transport(url, payload, timeout=TIMEOUT):
    """POST the JSON publish payload (UTF-8 safe, unlike header-based titles). Returns the HTTP status."""
    data = json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


class Ntfy:
    def __init__(self, topic=None, server=None, env=os.environ, transport=urllib_transport):
        self.topic = topic if topic is not None else env.get("NTFY_TOPIC", "")
        self.server = (server or env.get("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")
        self._transport = transport
        self.log = []  # (payload, status or error) per attempt

    @property
    def enabled(self):
        return bool(self.topic)

    def send(self, title, message, click=None, tags=(), priority=None):
        """True when ntfy accepted the message; False without a topic, on a network error or a non-2xx."""
        if not self.enabled:
            return False
        payload = {"topic": self.topic, "title": title, "message": message}
        if click:
            payload["click"] = click
        if tags:
            payload["tags"] = list(tags)
        if priority is not None:
            payload["priority"] = PRIORITIES.get(priority, priority) if isinstance(priority, str) else int(priority)
        try:
            status = self._transport(self.server, payload)
        except (OSError, http.client.HTTPException, ValueError) as e:
            self.log.append((payload, repr(e)))
            return False
        self.log.append((payload, status))
        return 200 <= status < 300

    def last_error(self):
        if not self.log:
            return "no NTFY_TOPIC" if not self.enabled else None
        result = self.log[-1][1]
        return None if isinstance(result, int) and 200 <= result < 300 else f"ntfy: {result}"


def main(args, env=os.environ, ntfy=None):
    """`python -m scanner notify --title T --message M [--click URL] [--tags a,b] [--priority high]`.
    Exit 0 when sent, 1 otherwise (phone/run.sh then falls back to termux-notification)."""
    ntfy = ntfy or Ntfy(env=env)
    tags = [t for t in (args.tags or "").split(",") if t]
    if ntfy.send(args.title, args.message, click=args.click, tags=tags, priority=args.priority):
        return 0
    print(f"not sent: {ntfy.last_error()}")
    return 1
