"""Recorded expert API responses (tests/fixtures/*.json, 2026-11-23) served through the real client."""

import json
from pathlib import Path

from scanner.expert_api import ONLINE_SHOP
from tests.test_expert_api import FakeTransport, json_response, make_api

FIXTURES = Path(__file__).parent / "fixtures"
PHILIPS, SONY65 = "11128346052", "11128378730"
RANGSDORF, TAUENTZIEN, FREITAL, PASTERNAK, PIRNA, RHEINFELDEN = (
    "e_32472581", "e_34627162", "e_26051723", "e_1907435", "e_26051722", "e_36696318")
BERLIN = {"zip": "14167", "lat": 52.5167, "lng": 13.4, "maxDistanceKm": 50}


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def pricepds_key(webcode, store_id):
    return f"pricepds?webcode={webcode}&storeId={store_id}"


def scripts(**overrides):
    """URL fragment → list of responses. Philips: online, Rangsdorf (Aussteller), Freital (pickup only) have
    an offer; Pasternak none; every other store answers like Pasternak. Sony 65: online only."""
    base = {
        "storeFinder": [json_response(fixture("storeFinder"))],
        pricepds_key(PHILIPS, ONLINE_SHOP): [json_response(fixture("pricepds-philips-online"))],
        pricepds_key(PHILIPS, RANGSDORF): [json_response(fixture("pricepds-philips-rangsdorf"))],
        pricepds_key(PHILIPS, FREITAL): [json_response(fixture("pricepds-philips-freital"))],
        pricepds_key(SONY65, ONLINE_SHOP): [json_response(fixture("pricepds-sony65-online"))],
        f"search/article?webcode={PHILIPS}": [json_response(fixture("article-philips"))],
        f"search/article?webcode={SONY65}": [json_response(fixture("article-sony65"))],
        "medium/6a83118b516e44538f9f2c55": [json_response(fixture("medium-philips"))],
        "medium/6a1d92d53a26e400017ef395": [json_response(fixture("medium-sony65"))],
    }
    base.update(overrides)
    return base


def no_offer(url):
    body = fixture("pricepds-philips-pasternak") if PHILIPS in url else fixture("pricepds-sony65-tauentzien")
    return json_response(body)


def recorded_api(**overrides):
    """A real ExpertApi over the recorded responses. Returns (api, transport, clock)."""
    transport = FakeTransport(scripts(**overrides), default=no_offer)
    api, clock = make_api(transport)
    return api, transport, clock
