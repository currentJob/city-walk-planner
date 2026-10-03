"""Public artifacts must not contain the account's personal notebook."""
import json
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'src/city_walk_planner/web'


def test_private_itinerary_not_in_public_data():
    data = json.loads((WEB / 'data/hk-macau-trend.json').read_text())
    assert 'journey' not in data
    assert '다은마을' not in json.dumps(data, ensure_ascii=False)
    assert not (WEB / 'js/render/journey.js').exists()


def test_public_trend_links_to_account():
    js = (WEB / 'js/render/trend.js').read_text()
    assert '/account/' in js
    assert 'GitHub로 내 여행 관리' in js
