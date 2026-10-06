"""The trend scheduler never puts a stop on its weekly closing day, for any start weekday and length."""
from tests.static.test_plan_map import PROJECT_ROOT, _run_node, node_only


@node_only
def test_trend_schedule_avoids_closures_and_escapes():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/trend.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{trendHtml,positiveShare,schedule,weekdayOf}} from {module!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8'));
      const byId=Object.fromEntries([...data.shops,...data.places].map(x=>[x.id,x]));
      const missing=data.blocks.flatMap(b=>b.stops).filter(s=>s.ref&&!byId[s.ref]).map(s=>s.ref);
      const closedVisits=[],shape=[];
      for(let start=5;start<12;start++) for(let n=1;n<=8;n++){{
        const a='2026-10-'+String(start).padStart(2,'0'), b='2026-10-'+String(start+n-1).padStart(2,'0');
        const days=schedule(data,a,b);
        const blocks=days.filter(d=>d.blockId).map(d=>d.blockId);
        shape.push(days.length===n && new Set(blocks).size===blocks.length && blocks.length===Math.min(n,4));
        if(n>=3) shape.push(days[0].blockId!=='macau' && days.at(-1).blockId!=='macau');
        for(const d of days) for(const s of d.stops)
          if(byId[s.ref]?.closed?.includes(weekdayOf(d.date))) closedVisits.push(d.date+' '+s.ref);
      }}
      const errors=[['2026-10-08','2026-10-05'],['2026-10-01','2026-10-30'],['','2026-10-01']]
        .map(([a,b])=>{{try{{schedule(data,a,b);return false}}catch{{return true}}}});
      const evil=structuredClone(data);
      evil.shops[0].name='<script>x</script>';evil.blocks[0].stops[0].name='<img onerror=x>';
      console.log(JSON.stringify({{
        missing,closedVisits,shape:shape.every(Boolean),errors,
        original:schedule(data,'2026-10-05','2026-10-08').map(d=>d.blockId),
        share:positiveShare({{smile:1,ok:1,cry:2}}),unknown:positiveShare({{smile:1,ok:null,cry:2}}),
        escaped:!/<script>|<img/.test(trendHtml(evil)),
        sourced:data.shops.every(s=>s.source_url.startsWith('https://www.openrice.com/'))
      }}));
    """)
    assert result['missing'] == []
    assert result['closedVisits'] == []
    assert result['shape'] and result['errors'] == [True, True, True]
    assert result['original'] == ['central', 'kowloon', 'macau', 'wanchai']
    assert result['share'] == 25 and result['unknown'] is None
    assert result['escaped'] and result['sourced']


@node_only
def test_trend_schedule_follows_stays():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/trend.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{schedule,daysHtml}} from {module!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8'));
      const stay=(name,area,a,b)=>({{name,area,checkin_date:a,checkin_time:'15:00',
        checkout_date:b,checkout_time:'11:00'}});
      const hk=stay('K','kowloon','2026-10-05','2026-10-07'), mo=stay('<b>M</b>','cotai','2026-10-07','2026-10-08');
      const split=schedule(data,'2026-10-05','2026-10-08',[mo,hk]);
      const macauDay=split.find(d=>d.blockId==='macau');
      const long=schedule(data,'2026-10-05','2026-10-11',
        [stay('K','kowloon','2026-10-05','2026-10-09'),stay('M','cotai','2026-10-09','2026-10-11')]);
      const bad=[[{{...hk,area:''}}],[{{...hk,checkout_date:'2026-10-05'}}],[hk,{{...mo,checkin_date:'2026-10-06'}}],
        [{{...hk,checkout_date:'2026-10-20'}}],[{{...hk,checkin_time:''}}],[{{...hk,checkin_date:''}}]]
        .map(s=>{{try{{schedule(data,'2026-10-05','2026-10-08',s);return false}}catch{{return true}}}});
      console.log(JSON.stringify({{
        plain:schedule(data,'2026-10-05','2026-10-08',[stay('K','kowloon','2026-10-05','2026-10-08')]).map(d=>d.blockId),
        macauDate:macauDay.date,
        macauFerries:macauDay.stops.filter(s=>s.ref==='ferry').length,
        checkoutFirst:macauDay.stops[0].name.startsWith('숙소 퇴실'),
        checkin:macauDay.stops.some(s=>s.name==='숙소 입실 · <b>M</b>'),
        lastDayNight:split.at(-1).stay,
        longMacau:long.find(d=>d.blockId==='macau').date,
        escaped:!daysHtml(data,split).includes('<b>M</b>'),
        bad
      }}));
    """)
    assert result['plain'] == ['central', 'kowloon', 'macau', 'wanchai']
    # Sleeping in Macau on 10/7 keeps the Macau course that day and drops only the return ferry.
    assert result['macauDate'] == '2026-10-07' and result['macauFerries'] == 1
    assert result['checkoutFirst'] and result['checkin'] and result['escaped']
    assert result['lastDayNight'] == '이날 밤 숙소 없음'
    # Macau nights 10/9–10/10 pull the Macau course onto a day that starts and ends there.
    assert result['longMacau'] == '2026-10-10'
    assert result['bad'] == [True] * 6


@node_only
def test_trend_map_pins_every_stop_with_matching_rows():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/trend.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{schedule,daysHtml,trendHtml,trendMapDays}} from {module!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8'));
      const stay={{name:'K',area:'kowloon',checkin_date:'2026-10-05',checkin_time:'15:00',
        checkout_date:'2026-10-08',checkout_time:'11:00'}};
      const days=schedule(data,'2026-10-05','2026-10-08',[stay]);
      const mapDays=trendMapDays(data,days), html=daysHtml(data,days);
      const inArea=s=>s.lat>22.10&&s.lat<22.45&&s.lng>113.50&&s.lng<114.30;
      const macau=mapDays.find(d=>days[d.day_index].blockId==='macau').spots;
      console.log(JSON.stringify({{
        counts:mapDays.map(d=>d.spots.length),
        expected:days.map(d=>d.stops.filter(s=>s.kind!=='stay').length),
        rows:mapDays.flatMap(d=>d.spots).every(s=>html.includes('id="'+s.id+'"')),
        inArea:mapDays.flatMap(d=>d.spots).every(inArea),
        ferryEnds:[macau[0].lng>114, macau.at(-1).lng<114],
        // Map ↔ list: every pin has a popup summary, and every referenced shop/place has a card to scroll back to.
        summaries:mapDays.flatMap(d=>d.spots).every(s=>typeof s.summary==='string'&&s.summary.length>0),
        cards:mapDays.flatMap(d=>d.spots).filter(s=>s.ref).every(s=>trendHtml(data).includes('data-trend-ref="'+s.ref+'"')),
        refs:mapDays.flatMap(d=>d.spots).filter(s=>s.ref).length
      }}));
    """)
    # Every visitable stop gets a pin; stay events have only an area, so they are left off the map.
    assert result['counts'] == result['expected']
    assert result['rows'] and result['inArea']
    # The Macau day starts at the Sheung Wan terminal and ends at Taipa.
    assert result['ferryEnds'] == [True, True]
    assert result['summaries'] and result['cards'] and result['refs'] > 0

@node_only
def test_displayed_plan_uses_confirmed_notebook_and_preserves_generic_scheduler():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/render/trend.js').as_uri()
    result = _run_node(f"""
      import {{readFileSync}} from 'node:fs';
      import {{displayedSchedule,trendHtml}} from {module!r};
      const data=JSON.parse(readFileSync('src/city_walk_planner/web/data/hk-macau-trend.json','utf8'));
      const days=displayedSchedule(data,'2026-10-05','2026-10-08');
      const last=days.find(d=>d.date==='2026-10-07');
      console.log(JSON.stringify({{
        ids:last.stops.map(s=>s.id),
        airport:last.stops.find(s=>s.id==='airport').time,
        flight:days.at(-1).stops[0].time,
        html:trendHtml(data).includes('침사추이 스타페리 → 센트럴 → 호텔'),
        single:displayedSchedule(data,'2026-10-07','2026-10-07')[0].stops.map(s=>s.id),
        generic:displayedSchedule(data,'2026-10-10','2026-10-12').length
      }}));
    """)
    assert 'wanchai-ferry' in result['ids'] and 'tst-ferry-return' in result['ids']
    assert result['airport'].startswith('22:00') and result['flight'] == '01:10'
    assert result['html'] and result['single'] == result['ids']
    assert result['generic'] == 3
