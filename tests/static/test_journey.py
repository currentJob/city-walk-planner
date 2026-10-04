"""Trip-specific midnight handling, safe persistence, and the map adapter contract."""
from tests.static.test_plan_map import PROJECT_ROOT, _run_node, node_only


@node_only
def test_airport_deadlines_use_hong_kong_dates():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/journey.js').as_uri()
    result = _run_node(f"""
      import {{airportTiming}} from {module!r};
      console.log(JSON.stringify({{
        two: airportTiming('02:00'), five: airportTiming('05:00'),
        midnight: airportTiming('00:15'), invalid: ['', '24:00','02:99','bad'].map(t=>airportTiming(t))
      }}));
    """)
    assert result['two'] == {'departure': '10-08 02:00', 'airport': '10-07 23:00', 'leave': '10-07 21:30'}
    assert result['five']['leave'] == '10-08 00:30'
    assert result['midnight']['airport'] == '10-07 21:15'
    assert result['invalid'] == [None] * 4


@node_only
def test_macau_switch_keeps_flight_day_free_and_early_return():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/journey.js').as_uri()
    trend = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/trend.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{journeyDays}} from {module!r};
      import {{trendMapDays, daysHtml}} from {trend!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8'));
      const initial=JSON.stringify(data.journey);
      const days=journeyDays(data.journey,{{macauDate:'2026-10-07',flightTime:'02:00'}});
      const macau=days[3]; const pins=trendMapDays(data, days); const html=daysHtml(data,days);
      console.log(JSON.stringify({{
        dates:days.map(d=>d.date),
        macauIds:macau.stops.map(s=>s.id), back:macau.stops.find(s=>s.id==='ferry-back').time,
        departure:days[4].stops.map(s=>s.id),
        unchanged:JSON.stringify(data.journey)===initial,
        pins:pins.flatMap(d=>d.spots).every(s=>Number.isFinite(s.lat)&&html.includes('id="'+s.id+'"')),
        early:journeyDays(data.journey,{{flightTime:'00:15'}})[3].stops.some(s=>s.id==='lights')
      }}));
    """)
    assert result['dates'] == [f'2026-10-{n:02d}' for n in range(4, 9)]
    assert 'cotai' not in result['macauIds']
    assert 'airport' in result['macauIds'] and '17:30' in result['back']
    assert result['departure'] == ['flight', 'home']
    assert result['unchanged'] and result['pins'] and not result['early']


@node_only
def test_corrupt_state_and_offline_export_escape_user_content():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/journey.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{normalizeJourneyState,offlineJourneyHtml}} from {module!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8')).journey;
      const state=normalizeJourneyState({{macauDate:'bad',flightTime:'99:99',hotel:'<img src=x onerror=alert(1)>',
        checked:{{'prep-0':true,'prep-1':'true',unknown:true}}}}, data);
      const html=offlineJourneyHtml(data,state);
      console.log(JSON.stringify({{
        defaults:normalizeJourneyState(null,data), state,
        safe:!html.includes('<img src=x')&&!html.includes('<script'),
        full:data.days.every(d=>html.includes(d.date))&&data.activities.every(a=>html.includes(a.name)),
        independent:!html.includes('<script src')&&!html.includes('<link rel="stylesheet"')
      }}));
    """)
    assert result['defaults']['macauDate'] == '2026-10-06'
    assert result['state']['checked'] == {'prep-0': True}
    assert result['state']['flightTime'] == ''
    assert result['safe'] and result['full'] and result['independent']


@node_only
def test_public_trend_renders_approved_notebook_without_account_link():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/trend.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{trendHtml}} from {module!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8'));
      const html=trendHtml(data);
      console.log(JSON.stringify({{
        title:html.includes(data.journey.title),
        publicNotice:html.includes('로그인 없이 누구나 볼 수 있는 공개 여행수첩'),
        journeyFirst:html.includes('data-trend-tab="journey" aria-pressed="true"'),
        noLogin:!html.includes('/account/')&&!html.includes('/auth/'),
        dates:data.journey.days.map(day=>day.date)
      }}));
    """)
    assert result['title'] and result['publicNotice'] and result['journeyFirst'] and result['noLogin']
    assert result['dates'] == [f'2026-10-{n:02d}' for n in range(4, 9)]


def test_public_trend_routes_stay_on_pages_and_reset_requested_section():
    web = PROJECT_ROOT / 'src/city_walk_planner/web'
    js = (web / 'js/platform.js').read_text()
    assert 'location.assign' not in js
    assert '/account/' not in js and '/auth/' not in js
    assert "if (hash === 'trend') trendView?.showTab('journey');" in js
    assert "else if (hash === 'trend-guide') trendView?.showTab('plan');" in js
    assert "if (location.hash.slice(1) !== hash) return;" in js
    assert 'trendHtml(data)' in js
    notebook = (web / 'js/render/journey.js').read_text()
    assert '/api/private/' not in notebook and '/auth/' not in notebook
    assert 'fetch(' not in notebook
