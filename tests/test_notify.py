import argparse
import contextlib
import io
import unittest

from scanner import notify


class FakeTransport:
    def __init__(self, status=200, error=None):
        self.status, self.error, self.calls = status, error, []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.error:
            raise self.error
        return self.status


class SendTest(unittest.TestCase):
    def test_json_payload_with_all_fields(self):
        t = FakeTransport()
        n = notify.Ntfy(topic="abc", transport=t, env={})
        ok = n.send("LG OLED65C69LB", "1 294 € pickup · expert Bischofswerda, 32 km",
                    click="https://www.expert.de/shop/x.html?branch_id=e_1", tags=["chart_with_downwards_trend"],
                    priority="high")
        self.assertTrue(ok)
        url, payload = t.calls[0]
        self.assertEqual(url, "https://ntfy.sh")
        self.assertEqual(payload, {"topic": "abc", "title": "LG OLED65C69LB",
                                   "message": "1 294 € pickup · expert Bischofswerda, 32 km",
                                   "click": "https://www.expert.de/shop/x.html?branch_id=e_1",
                                   "tags": ["chart_with_downwards_trend"], "priority": 4})
        self.assertIsNone(n.last_error())

    def test_minimal_payload_and_numeric_priority(self):
        t = FakeTransport()
        n = notify.Ntfy(topic="abc", transport=t, env={})
        n.send("t", "m", priority=5)
        self.assertEqual(t.calls[0][1], {"topic": "abc", "title": "t", "message": "m", "priority": 5})

    def test_topic_and_server_from_env(self):
        t = FakeTransport()
        n = notify.Ntfy(env={"NTFY_TOPIC": "secret", "NTFY_SERVER": "https://ntfy.example/"}, transport=t)
        n.send("t", "m")
        self.assertEqual(t.calls[0], ("https://ntfy.example", {"topic": "secret", "title": "t", "message": "m"}))

    def test_without_topic_nothing_is_sent(self):
        t = FakeTransport()
        n = notify.Ntfy(env={}, transport=t)
        self.assertFalse(n.enabled)
        self.assertFalse(n.send("t", "m"))
        self.assertEqual(t.calls, [])
        self.assertEqual(n.last_error(), "no NTFY_TOPIC")

    def test_network_error_and_http_error_return_false(self):
        n = notify.Ntfy(topic="abc", transport=FakeTransport(error=OSError("down")), env={})
        self.assertFalse(n.send("t", "m"))
        self.assertEqual(n.last_error(), "ntfy: OSError('down')")
        n = notify.Ntfy(topic="abc", transport=FakeTransport(status=429), env={})
        self.assertFalse(n.send("t", "m"))
        self.assertEqual(n.last_error(), "ntfy: 429")


class MainTest(unittest.TestCase):
    def args(self, **kw):
        base = {"title": "t", "message": "m", "click": None, "tags": None, "priority": None}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_exit_codes(self):
        t = FakeTransport()
        n = notify.Ntfy(topic="abc", transport=t, env={})
        self.assertEqual(notify.main(self.args(tags="a,b", priority="high"), ntfy=n), 0)
        self.assertEqual(t.calls[0][1]["tags"], ["a", "b"])
        self.assertEqual(t.calls[0][1]["priority"], 4)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(notify.main(self.args(), ntfy=notify.Ntfy(env={}, transport=t)), 1)
        self.assertIn("no NTFY_TOPIC", out.getvalue())


if __name__ == "__main__":
    unittest.main()
