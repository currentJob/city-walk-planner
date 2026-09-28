import { escapeHtml as esc, link } from '../format.js';

const WEEKDAYS = '월화수목금토일';
const MAX_DAYS = 14;
/** Cost of leaving a course out when the trip is shorter than all courses (higher = keep first). */
const OMIT_COST = {central: 8, kowloon: 6, macau: 4, wanchai: 2};
const CLOSED_STOP_COST = 3;

/** OpenRice reaction counts → positive share (0–100), or null when any count is missing. */
export function positiveShare(r) {
  if (!r || ![r.smile, r.ok, r.cry].every(Number.isInteger)) return null;
  const total = r.smile + r.ok + r.cry;
  return total ? Math.round(r.smile / total * 100) : null;
}

/** 'YYYY-MM-DD' → 0=월 … 6=일 (서버 규약과 동일). */
export function weekdayOf(iso) {
  return (new Date(iso + 'T12:00:00Z').getUTCDay() + 6) % 7;
}

function datesBetween(start, end) {
  const valid = s => /^\d{4}-\d{2}-\d{2}$/.test(s || '') && !Number.isNaN(Date.parse(s + 'T12:00:00Z'));
  if (!valid(start) || !valid(end)) throw new Error('방문 시작일과 종료일을 모두 골라 주세요.');
  const dates = [];
  for (let t = Date.parse(start + 'T12:00:00Z'); t <= Date.parse(end + 'T12:00:00Z'); t += 86400000) {
    dates.push(new Date(t).toISOString().slice(0, 10));
    if (dates.length > MAX_DAYS) throw new Error(`최대 ${MAX_DAYS}일까지 짤 수 있습니다.`);
  }
  if (!dates.length) throw new Error('종료일이 시작일보다 빠릅니다.');
  return dates;
}

function permutations(items, k) {
  if (!k) return [[]];
  return items.flatMap((x, i) => permutations(items.filter((_, j) => j !== i), k - 1).map(rest => [x, ...rest]));
}

function combinations(items, k) {
  if (!k) return [[]];
  return items.flatMap((x, i) => combinations(items.slice(i + 1), k - 1).map(rest => [x, ...rest]));
}

/** Estimated minutes between two areas; 0 when either is unknown. */
export function travelMinutes(data, a, b) {
  if (!a || !b || a === b) return 0;
  return data.travel_minutes[[a, b].sort().join('|')] ?? 0;
}

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Validates stays and sorts them by check-in; throws a user-facing message on bad input. */
function checkStays(data, stays, start, end) {
  const areas = new Set(data.areas.map(a => a.id));
  const sorted = [...stays].sort((a, b) => String(a.checkin_date).localeCompare(String(b.checkin_date)));
  sorted.forEach((s, i) => {
    const who = `숙소 ${i + 1}(${s.name || '이름 없음'})`;
    if (!areas.has(s.area)) throw new Error(`${who}의 지역을 골라 주세요.`);
    if (![s.checkin_date, s.checkout_date].every(d => /^\d{4}-\d{2}-\d{2}$/.test(d || ''))) throw new Error(`${who}의 입실일과 퇴실일을 입력해 주세요.`);
    if (!TIME.test(s.checkin_time || '') || !TIME.test(s.checkout_time || '')) throw new Error(`${who}의 입실·퇴실 시각을 입력해 주세요.`);
    if (!(s.checkin_date < s.checkout_date)) throw new Error(`${who}의 퇴실일은 입실일보다 늦어야 합니다.`);
    if (s.checkin_date < start || s.checkout_date > end) throw new Error(`${who}의 날짜가 방문 기간(${start}–${end}) 밖에 있습니다.`);
    if (i && sorted[i - 1].checkout_date > s.checkin_date) throw new Error(`${who}의 숙박일이 앞 숙소와 겹칩니다.`);
  });
  return sorted;
}

/**
 * Places the date-free courses on the chosen dates.
 * Cost = closed stops on that weekday + estimated travel from the morning stay to the course start
 * and from the course end back to the night's stay + a small order preference.
 * Arrival and departure days avoid Macau unless stays make it cheaper; the short Wan Chai course prefers the last day.
 * ponytail: brute force over date combinations × course orders (≤ 1001 × 24 for 14 days); fine at this size.
 */
export function schedule(data, start, end, stays = []) {
  const dates = datesBetween(start, end), n = dates.length;
  stays = checkStays(data, stays, start, end);
  const byId = Object.fromEntries([...data.shops, ...data.places].map(x => [x.id, x]));
  const areaLabel = Object.fromEntries(data.areas.map(a => [a.id, a.label]));
  const nightStay = date => stays.find(s => s.checkin_date <= date && date < s.checkout_date);
  const ends = dates.map((date, i) => {
    const morning = (i && nightStay(dates[i - 1])) || stays.find(s => s.checkin_date === date) || nightStay(date);
    return {morning, night: nightStay(date) || (i === n - 1 ? null : morning)};
  });
  const closedStops = (block, date) => block.stops.filter(s => byId[s.ref]?.closed?.includes(weekdayOf(date)));
  const travel = (block, i) => travelMinutes(data, ends[i].morning?.area, block.start_area) + travelMinutes(data, block.end_area, ends[i].night?.area);
  const k = Math.min(n, data.blocks.length);
  const defaultSlots = n <= k ? dates : [...dates.slice(0, k - 1), dates[n - 1]];
  let best = null, bestCost = Infinity;
  // Without stays keep the predictable layout; with stays any date may suit a course better.
  const slotSets = stays.length ? [defaultSlots, ...combinations(dates, k)] : [defaultSlots];
  for (const slots of slotSets) for (const order of permutations(data.blocks, k)) {
    let cost = data.blocks.filter(b => !order.includes(b)).reduce((sum, b) => sum + (OMIT_COST[b.id] ?? 1), 0);
    order.forEach((b, j) => {
      const i = dates.indexOf(slots[j]);
      cost += closedStops(b, slots[j]).length * CLOSED_STOP_COST + travel(b, i) / 15;
      if (b.id === 'macau' && n >= 3 && (i === 0 || i === n - 1)) cost += 5;
      if (b.id === 'wanchai' && n >= 2 && i !== n - 1) cost += 2;
    });
    if (cost < bestCost - 1e-9) { best = {slots, order}; bestCost = cost; }
  }
  const assigned = Object.fromEntries(best.slots.map((d, j) => [d, best.order[j]]));
  return dates.map((date, i) => {
    const wd = weekdayOf(date), block = assigned[date], notes = [], {morning, night} = ends[i];
    const label = `${i + 1}일차 · ${WEEKDAYS[wd]}`;
    const stay = stays.length ? (nightStay(date) ? `🛏 ${nightStay(date).name || '숙소'} · ${areaLabel[nightStay(date).area]}` : '🛏 이날 밤 숙소 없음') : '';
    let stops = [];
    if (block) {
      const closed = closedStops(block, date);
      closed.forEach(s => notes.push(`${s.name}은(는) ${WEEKDAYS[wd]}요일 휴무라 이날 일정에서 뺐습니다.`));
      stops = block.stops.filter(s => !closed.includes(s));
      const inMacau = a => a === 'macau' || a === 'cotai';
      if (stops[0]?.ref === 'ferry' && inMacau(morning?.area)) stops = stops.slice(1);
      if (stops.at(-1)?.ref === 'ferry' && inMacau(night?.area)) stops = stops.slice(0, -1);
      if (block.id !== 'macau' && inMacau(morning?.area)) notes.push('마카오 숙소에서 출발합니다. 페리로 홍콩에 건너가는 시간(약 1시간 반, 추정)을 앞에 더하세요.');
      if (block.id !== 'macau' && inMacau(night?.area)) notes.push('밤에 마카오 숙소로 돌아갑니다. 페리 막차 시간을 확인하세요.');
      if (morning) notes.push(`이동 추정: 숙소 → 첫 방문지 약 ${travelMinutes(data, morning.area, block.start_area)}분${night ? ` · 마지막 방문지 → 숙소 약 ${travelMinutes(data, block.end_area, night.area)}분` : ''}.`);
    } else {
      notes.push('조사한 코스는 모두 배치했습니다. 아래 가게 요약의 대안(카우키·마가렛 카페)이나 쇼핑·휴식으로 채우세요.');
    }
    // Check-out happens before leaving, so it leads the day with its deadline; check-in keeps its time slot.
    const checkouts = stays.filter(s => s.checkout_date === date).map(s => ({time: `~${s.checkout_time}`, kind: 'stay', ref: null,
      name: `숙소 퇴실 · ${s.name || '숙소'}`, note: `${areaLabel[s.area]}. ${s.checkout_time}까지 퇴실하고, 짐은 맡기거나 들고 출발하세요.`}));
    const checkins = stays.filter(s => s.checkin_date === date).map(s => ({time: s.checkin_time, kind: 'stay', ref: null,
      name: `숙소 입실 · ${s.name || '숙소'}`, note: `${areaLabel[s.area]}. 입실 전에 도착하면 짐을 먼저 맡길 수 있는지 숙소에 확인하세요.`}));
    if (stops.length) checkins.filter(e => e.time > stops[0].time && e.time < stops.at(-1).time)
      .forEach(e => notes.push(`${e.name}(${e.time})이 코스 중간에 있습니다. 숙소까지 오가는 시간을 고려해 순서를 조정하세요.`));
    stops = [...checkouts, ...[...stops, ...checkins].sort((x, y) => x.time.localeCompare(y.time))];
    if (n >= 2 && i === n - 1) notes.push('마지막 날입니다. 공항 이동 시간과 짐 보관을 고려해 뒤쪽 일정을 줄이세요.');
    return {date, label, blockId: block?.id, theme: block ? block.theme : '자유 일정', stay, stops, notes};
  });
}

function reactions(r) {
  const share = positiveShare(r);
  const count = (label, n) => Number.isInteger(n) ? `${label} ${n.toLocaleString('ko-KR')}` : `${label} 미확인`;
  return `<p class="rating">${share === null ? '' : `긍정 ${share}% · `}리뷰 ${r.reviews.toLocaleString('ko-KR')}건</p>
    <p class="meta">${[count('좋아요', r.smile), count('보통', r.ok), count('별로', r.cry)].join(' · ')}</p>`;
}

function shopCard(s) {
  return `<article class="place-card" id="trend-${esc(s.id)}"><p class="eyebrow">${esc(s.city)} · ${esc(s.type)}</p>
    <h3>${esc(s.name)} <span class="orig">${esc(s.name_local)}</span></h3>${reactions(s.openrice)}
    <p>${s.must_try.map(m => `<span class="pill">${esc(m)}</span>`).join('')}</p>
    <ul class="tips"><li><b>좋은 점</b> ${esc(s.good)}</li><li><b>아쉬운 점</b> ${esc(s.bad)}</li></ul>
    <p class="meta">🕒 ${esc(s.hours)}<br>💳 ${esc(s.payment)}<br>📍 ${esc(s.area)} · ${esc(s.access)}</p>
    ${s.day_hint ? `<p class="hint">${esc(s.day_hint)}</p>` : ''}
    <p class="source">${link(s.source_url, 'OpenRice 원문')}</p></article>`;
}

function stopRow(stop, byId) {
  const ref = stop.ref && byId[stop.ref];
  const extra = ref?.hours ? `<p class="meta">🕒 ${esc(ref.hours)}</p>` : '';
  const target = stop.kind === 'food' && ref ? ` · <a href="#trend-${esc(ref.id)}">가게 요약 보기</a>` : '';
  return `<div class="stop"><time>${esc(stop.time)}</time><div><h3>${esc(stop.name)}</h3><p class="desc">${esc(stop.note)}${target}</p>${extra}</div></div>`;
}

/** Day cards for a scheduled range (output of `schedule`). */
export function daysHtml(data, days) {
  const byId = Object.fromEntries([...data.shops, ...data.places].map(x => [x.id, x]));
  return days.map(d => `<article class="day"><div class="day-head"><div><h3>${esc(d.label)} · ${esc(d.date)}</h3><span class="daytheme">${esc(d.theme)}</span>${d.stay ? `<span class="hint">${esc(d.stay)}</span>` : ''}</div></div>
    ${d.notes.length ? `<p class="dayexception">${d.notes.map(esc).join('<br>')}</p>` : ''}
    ${d.stops.map(s => stopRow(s, byId)).join('')}</article>`).join('');
}

/** Whole page for the trend category; data comes from data/hk-macau-trend.json. */
export function trendHtml(data) {
  const {start, end} = data.default_range;
  return `<div class="page-heading"><p class="eyebrow">HONG KONG · MACAO · TREND COURSE</p><h1>${esc(data.title)}</h1>
    <p>${esc(data.summary)}</p><p class="hint">조사일 ${esc(data.checked_at)}. ${esc(data.rating_note)}</p></div>
    <section class="section"><h2>날짜별 일정</h2>
      <form id="trendRange"><div class="tools"><label>방문 시작일<input type="date" name="start" value="${esc(start)}" required></label>
        <label>방문 종료일<input type="date" name="end" value="${esc(end)}" required></label></div>
        <fieldset class="stay-box"><legend>숙소 (선택 · 여러 곳 가능)</legend><div class="stay-list"></div>
          <button type="button" class="secondary" data-add-stay>+ 숙소 추가</button></fieldset>
        <button>이 기간으로 일정 짜기</button></form>
      <p class="hint">요일별 휴무를 피해 코스를 배치하고, 도착일과 출국일에는 되도록 마카오를 넣지 않습니다. 숙소를 넣으면 숙소 지역에서 가까운 코스를 우선하고 입실·퇴실을 일정에 표시합니다. 이동 시간은 지역 단위 추정치입니다(${esc(data.travel_minutes.note)}). 최대 ${MAX_DAYS}일까지 짤 수 있고, 공휴일과 임시 휴업은 반영하지 않습니다.</p>
      <p id="trendRangeError" class="message error" role="alert" hidden></p>
      <div id="trendDays">${daysHtml(data, schedule(data, start, end))}</div></section>
    <section class="section"><h2>가게별 평점·리뷰 요약</h2><p class="hint">일정에 넣은 곳과 대안으로 둔 곳입니다.</p>
      <div class="place-grid">${data.shops.map(shopCard).join('')}</div></section>
    <section class="section"><h2>명소 영업시간</h2><div class="place-grid">${data.places.map(p => `<article class="place-card"><h3>${esc(p.name)}</h3>
      <p class="meta">🕒 ${esc(p.hours)}<br>🎟 ${esc(p.fee)}</p><p class="source">${link(p.source_url, p.source_name)}</p></article>`).join('')}</div></section>
    <section class="section"><h2>꿀팁</h2><div class="place-grid">${data.tips.map(t => `<article class="place-card"><h3>${esc(t.title)}</h3><p class="desc">${esc(t.body)}</p></article>`).join('')}</div></section>`;
}

function stayRowHtml(data, s) {
  return `<div class="stay-row tools"><label>숙소 이름<input data-f="name" value="${esc(s.name)}" placeholder="예: 침사추이 호텔" maxlength="60"></label>
    <label>지역<select data-f="area">${data.areas.map(a => `<option value="${esc(a.id)}"${a.id === s.area ? ' selected' : ''}>${esc(a.label)}</option>`).join('')}</select></label>
    <label>입실일<input type="date" data-f="checkin_date" value="${esc(s.checkin_date)}" required></label>
    <label>입실 시각<input type="time" data-f="checkin_time" value="${esc(s.checkin_time)}" required></label>
    <label>퇴실일<input type="date" data-f="checkout_date" value="${esc(s.checkout_date)}" required></label>
    <label>퇴실 시각<input type="time" data-f="checkout_time" value="${esc(s.checkout_time)}" required></label>
    <button type="button" class="secondary" data-remove-stay aria-label="이 숙소 삭제">삭제</button></div>`;
}

/** Binds the date and stay form after `trendHtml` is in the DOM. */
export function bindTrendRange(root, data) {
  const form = root.querySelector('#trendRange'), error = root.querySelector('#trendRangeError');
  const list = form.querySelector('.stay-list');
  const rows = () => [...list.querySelectorAll('.stay-row')].map(row =>
    Object.fromEntries([...row.querySelectorAll('[data-f]')].map(el => [el.dataset.f, el.value.trim()])));
  form.querySelector('[data-add-stay]').addEventListener('click', () => {
    const last = rows().at(-1);
    const checkin = last?.checkout_date || form.start.value;
    list.insertAdjacentHTML('beforeend', stayRowHtml(data, {name: '', area: last?.area || 'kowloon',
      checkin_date: checkin, checkin_time: '15:00', checkout_date: form.end.value, checkout_time: '11:00'}));
    list.querySelector('.stay-row:last-child input').focus();
  });
  list.addEventListener('click', event => event.target.closest('[data-remove-stay]')?.closest('.stay-row').remove());
  form.addEventListener('submit', event => {
    event.preventDefault();
    try {
      root.querySelector('#trendDays').innerHTML = daysHtml(data, schedule(data, form.start.value, form.end.value, rows()));
      error.hidden = true;
    } catch (e) {
      error.textContent = e.message; error.hidden = false;
    }
  });
}
