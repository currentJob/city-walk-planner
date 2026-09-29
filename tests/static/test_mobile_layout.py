"""The phone layout is one stylesheet, loaded only under 760px, with a bottom tab bar on every page."""
import re

from tests.static.test_plan_map import PROJECT_ROOT

WEB = PROJECT_ROOT / "src" / "city_walk_planner" / "web"
MOBILE = (WEB / "css" / "mobile.css").read_text(encoding="utf-8")
PLATFORM = (WEB / "css" / "platform.css").read_text(encoding="utf-8")


def test_pages_load_mobile_css_after_platform_css_only_on_phones():
    for page in ("index.html", "hongkong.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        platform = html.index('href="./css/platform.css"')
        mobile = re.search(r'<link rel="stylesheet" href="\./css/mobile\.css" media="\(max-width: 760px\)">', html)
        assert mobile and mobile.start() > platform, page
        nav = re.search(r'<nav aria-label="서비스 메뉴">(.*?)</nav>', html).group(1)
        items = re.findall(r'<a href="\./index\.html#(\w+)" data-view="\1" aria-label="[^"]+">', nav)
        assert items == ["discover", "planner", "food", "trend", "saved"], page
        assert nav.count('class="nav-icon"') == 5 and nav.count('class="nav-short"') == 5, page


def test_mobile_rules_live_only_in_mobile_css():
    assert "@media(max-width:760px)" not in PLATFORM.replace(" ", "")
    assert re.search(r"\.nav-short,\.trend-tabs,\.shop-more>summary\{display:none\}", PLATFORM)


def test_bottom_tab_bar_is_fixed_and_thumb_sized():
    nav = re.search(r"\.platform-header nav\{([^}]*)\}", MOBILE).group(1)
    assert "position:fixed" in nav and "bottom:0" in nav
    tab_height = int(re.search(r"--m-nav:(\d+)px", MOBILE).group(1))
    assert tab_height >= 44
    assert "min-height:var(--m-nav)" in re.search(r"\.platform-header nav a\{([^}]*)\}", MOBILE).group(1)
    # Body leaves room so the last content is never hidden behind the bar.
    assert "padding-bottom:calc(var(--m-nav)" in re.search(r"body\{([^}]*)\}", MOBILE).group(1)


def test_trend_sections_are_switchable_on_phones():
    for section in ("plan", "shops", "places", "tips"):
        assert f"[data-trend-section={section}]" in MOBILE
    trend = (WEB / "js" / "render" / "trend.js").read_text(encoding="utf-8")
    for section in ("plan", "shops", "places", "tips"):
        assert f'data-trend-section="{section}"' in trend
