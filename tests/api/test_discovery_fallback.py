import httpx

from city_walk_planner.services.external.discovery import DiscoveryProvider


def test_busy_primary_uses_fallback_and_cools_down():
    hosts = []
    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "overpass-api.de":
            return httpx.Response(429)
        return httpx.Response(200, json={"elements": []})
    provider = DiscoveryProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider._overpass("test") == {"elements": []}
    assert hosts == ["overpass-api.de", "overpass.private.coffee"]
    assert provider._overpass("another") == {"elements": []}
    assert hosts[-1] == "overpass.private.coffee" and hosts.count("overpass-api.de") == 1


def test_user_search_fallback_returns_real_metadata():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(504)
        assert request.url.params["bounded"] == "1"
        assert request.url.params["q"] == "[restaurant]"
        return httpx.Response(200, json=[{"osm_type": "node", "osm_id": 20, "lat": "35", "lon": "135",
            "name": "Sample", "type": "restaurant", "extratags": {"opening_hours": "24/7"}}])
    provider = DiscoveryProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.places(35, 135, 800, True)
    assert result[0]["name"] == "Sample" and result[0]["opening_hours"] == "24/7"
    assert result[0]["limited_search"] is True and result[0]["rating"] is None


def test_configured_mirror_list_is_tried_in_order(monkeypatch):
    """Deployments whose egress some mirrors refuse (Cloudflare Workers) set their own order."""
    monkeypatch.setenv("CWP_DISCOVERY_OVERPASS_URL", "https://first.example/api, https://second.example/api")
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "first.example":
            return httpx.Response(503)
        return httpx.Response(200, json={"elements": []})

    provider = DiscoveryProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider._overpass("q") == {"elements": []}
    assert hosts == ["first.example", "second.example"]
