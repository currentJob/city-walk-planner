import { escapeHtml as esc, link } from '../format.js';

const STORAGE_KEY = 'cwp.hk-macau.journey.2026.v1';
const TIME = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const SECTIONS = [['days', '날짜별'], ['prepare', '준비물'], ['activities', '놀거리'], ['info', '교통·팁']];
const maps = query => 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(query);

/** Validate untrusted browser storage; never spread stored properties into application state. */
export function normalizeJourneyState(value, data) {
  const v = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const allowed = new Set([...data.checklist.map(x => x.id), ...data.activities.map(x => x.id),
    ...data.days.flatMap(d => d.stops.map(s => s.id))]);
  const checked = {};
  if (v.checked && typeof v.checked === 'object') for (const id of allowed) if (v.checked[id] === true) checked[id] = true;
  return {macauDate: v.macauDate === '2026-10-07' ? v.macauDate : '2026-10-06',
    flightTime: TIME.test(v.flightTime || '') ? v.flightTime : '',
    hotel: typeof v.hotel === 'string' ? v.hotel.slice(0, 120) : '', checked};
}

/** Fixed Hong Kong offset: midnight subtraction must move onto October 7, regardless of device timezone. */
export function airportTiming(time, transferMinutes = 90) {
  if (!TIME.test(time || '') || !Number.isFinite(transferMinutes) || transferMinutes < 0) return null;
  const departure = Date.parse(`2026-10-08T${time}:00+08:00`);
  const format = ms => new Date(ms + 8 * 3600000).toISOString().slice(5, 16).replace('T', ' ');
  return {departure: format(departure), airport: format(departure - 180 * 60000),
    leave: format(departure - (180 + transferMinutes) * 60000)};
}

/** Travel-day preset is independent of the existing date-free restaurant scheduler. */
export function journeyDays(data, options = {}) {
  const days = structuredClone(data.days);
  if (options.macauDate === '2026-10-07') {
    const macau = days[2], hk = days[3];
    days[2] = {...hk, date: '2026-10-06', label: '6일 · 화 · 홍콩 시간', theme: '구룡 · 하버',
      notes: ['마카오를 7일로 옮겼습니다. 6일에는 구룡·전시를 즐기고 7일 복귀편을 먼저 확보하세요.'],
      stops: hk.stops.filter(s => !['checkout', 'bags', 'airport'].includes(s.id))};
    days[3] = {...macau, date: '2026-10-07', label: '7일 · 수 · 마카오 시간', theme: '마카오 짧게 · 홍콩공항',
      notes: ['귀국 전날 국경 이동은 지연 위험이 큽니다. 코타이를 줄이고 17:30 외항 복귀편을 우선 검토하세요. 실제 좌석·운항을 예약 화면에서 확인합니다.',
        '오전 체크아웃·짐 보관을 완료한 뒤 출발하세요. 악천후나 복귀 교통 불확실 시 홍콩에 머무는 편이 좋습니다.'],
      stops: [...macau.stops.filter(s => s.id !== 'cotai').map(s => s.id === 'ferry-back' ? {...s,
        time: '16:30 / 17:30', note: '16:30 외항 도착·17:30편 홍콩 복귀 후보. 실제 운항·예약 확인. 이후 홍콩 호텔 짐 회수와 공항 이동.'} : s),
        ...hk.stops.filter(s => ['bags', 'airport'].includes(s.id))]};
  }
  const timing = airportTiming(options.flightTime);
  if (timing) {
    const stop = days[3].stops.find(s => s.id === 'airport');
    stop.time = `${timing.leave}까지 출발 계획`;
    stop.note = `홍콩 현지 ${timing.departure} 출발편 기준 공항 ${timing.airport} 도착 목표. 숙소에서 공항까지 90분을 임시로 확보한 계산값입니다. 실제 위치·교통과 항공사 안내를 우선하세요.`;
    days[4].stops[0].time = options.flightTime;
    days[4].stops[0].note = '사용자가 입력한 홍콩 현지 출발 시각입니다. 항공권·탑승 및 수하물 마감을 다시 확인하세요.';
    if (options.flightTime < '02:00') {
      days[3].stops = days[3].stops.filter(s => s.id !== 'lights');
      days[3].notes.push('02시보다 이른 출발편을 입력했습니다. 저녁 쇼를 제외했으며 짐 회수·관광 종료를 공항 이동 계산보다 앞당기세요.');
    }
  }
  return days;
}

export function journeyHtml(data) {
  if (!data) return '';
  return `<section class="section journey" data-trend-section="journey">
    <div class="journey-heading"><p class="eyebrow">2026.10.04 — 10.08 · 여행은 현지 시간</p><h2>${esc(data.title)}</h2>
    <p>${esc(data.summary)}</p><p class="hint">수첩 확인일 ${esc(data.checked_at)} · 가게 리뷰의 조사일은 기존 가게 탭에 따로 표시합니다.</p></div>
    <div class="journey-alert"><b>관광은 5·6·7일, 총 3일</b><p>4일은 한국 출국, 8일은 새벽 귀국편입니다. 마카오는 6일이 여유롭습니다. 홍콩·마카오는 한국보다 1시간 느립니다.</p></div>
    <details class="journey-settings"><summary>마카오 날짜 · 귀국편 · 숙소 설정</summary>
    <form data-journey-settings class="tools"><label>마카오 방문일<select name="macauDate"><option value="2026-10-06">10월 6일 (추천)</option><option value="2026-10-07">10월 7일 (일찍 복귀)</option></select></label>
      <label>8일 홍콩 출발 시각<input type="time" name="flightTime"><small>미확인 시 비워 두세요. 현재 02~05시 범위만 확인.</small></label>
      <label>숙소 이름·주소<input name="hotel" maxlength="120" placeholder="지도 검색에 사용할 숙소"></label><button>설정 적용</button></form>
      <p class="hint">숙소와 체크 상태는 이 기기에만 저장됩니다. 호텔 입력은 지도 검색용이며 이동시간을 자동 계산하지 않습니다.</p></details>
    <div data-journey-timing class="journey-alert"></div><p data-journey-status role="status" aria-live="polite" class="hint"></p>
    <nav class="journey-nav" aria-label="여행수첩 보기">${SECTIONS.map(([id, name]) => `<button type="button" data-journey-tab="${id}" aria-pressed="${id === 'days'}">${name}</button>`).join('')}</nav>
    <div data-journey-body></div><div class="tools journey-download"><button type="button" class="secondary" data-journey-download>오프라인 수첩 저장</button><button type="button" class="secondary" data-journey-copy>전체 일정 복사</button></div>
    <p class="hint">저장한 HTML은 인터넷 없이 읽을 수 있습니다. 지도·공식 링크는 연결이 필요하고 저장 이후 변경은 다시 저장해야 반영됩니다.</p></section>`;
}

function activityWhen(activity, state) {
  if (state.macauDate !== '2026-10-07') return activity.when;
  return activity.city === '마카오' ? activity.when.replace('6일', '7일') : activity.when.replace('7일', '6일');
}

function stopsHtml(day, state, offline = false) {
  return day.stops.map(s => `<article class="journey-stop"><p class="eyebrow">${esc(s.time)}</p><h3>${esc(s.name)}</h3><p>${esc(s.note)}</p>
    <div class="journey-actions">${s.query ? link(maps(s.query), '지도·길찾기') : ''}
    ${offline ? `<span>${state.checked[s.id] ? '완료' : '예정'}</span>` : `<label class="journey-check"><input type="checkbox" data-check="${esc(s.id)}"${state.checked[s.id] ? ' checked' : ''}> 방문 완료</label>`}</div></article>`).join('');
}

/** No scripts, dependencies, or private website URL required in the saved file. */
export function offlineJourneyHtml(data, state) {
  const days = journeyDays(data, state);
  return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(data.title)}</title>
  <style>body{max-width:820px;margin:auto;padding:20px;font:16px/1.7 system-ui;color:#153247}h1,h2{line-height:1.4}article{border:1px solid #cbd9e4;border-radius:8px;padding:18px;margin:14px 0}a{color:#075f8b;overflow-wrap:anywhere}li{margin:9px 0}.eyebrow{color:#526c80}section{margin:36px 0}input{width:20px;height:20px}label{display:block;margin:12px 0}small{display:block} @media print{article{break-inside:avoid}}</style>
  <h1>${esc(data.title)}</h1><p>확인일 ${esc(data.checked_at)} · 저장 시점의 수첩. 지도·출처는 온라인 연결 필요.</p>
  <p>${esc(data.summary)}</p>${state.hotel ? `<p>내 숙소: ${esc(state.hotel)}</p>` : ''}<ul>${data.assumptions.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
  ${days.map(d => `<section><h2>${esc(d.date)} · ${esc(d.theme)}</h2><p>${d.notes.map(esc).join('<br>')}</p>${stopsHtml(d, state, true)}</section>`).join('')}
  <section><h2>준비물</h2>${data.checklist.map(x => `<label><input type="checkbox"${state.checked[x.id] ? ' checked' : ''}> ${esc(x.text)}</label>`).join('')}<small>오프라인 파일의 체크 변경은 파일에 자동 저장되지 않습니다.</small></section>
  <section><h2>놀거리</h2>${data.activities.map(a => `<article><h3>${esc(a.name)}</h3><p>${esc(a.city)} · ${esc(activityWhen(a, state))} · ${esc(a.duration)}</p><p>${esc(a.note)}</p>${link(maps(a.query), '지도')}</article>`).join('')}</section>
  <section><h2>교통·팁</h2>${data.tips.map(t => `<article><h3>${esc(t.title)}</h3><p>${esc(t.body)}</p></article>`).join('')}</section>
  <section><h2>공식 출처</h2>${data.sources.map(s => `<p>${link(s.url, s.name)}</p>`).join('')}</section></html>`;
}

export function bindJourney(root, data, {onMap = () => {}, notice = () => {}} = {}) {
  if (!data) return;
  const host = root.querySelector('.journey'), body = host.querySelector('[data-journey-body]');
  let stored, storage;
  try { storage = window.localStorage; stored = JSON.parse(storage.getItem(STORAGE_KEY) || 'null'); } catch { /* Private-mode and corrupt storage use safe defaults. */ }
  let state = normalizeJourneyState(stored, data), section = 'days', selected = '2026-10-04', city = 'all', onlySaved = false;
  const status = text => { host.querySelector('[data-journey-status]').textContent = text; };
  const save = () => { try { if (!storage) throw new Error(); storage.setItem(STORAGE_KEY, JSON.stringify(state)); status('이 기기에 저장했습니다.'); }
    catch { status('이 브라우저에 저장할 수 없습니다. 화면에서는 계속 사용할 수 있고 오프라인 수첩으로 보관할 수 있습니다.'); } };
  const form = host.querySelector('[data-journey-settings]');
  form.elements.macauDate.value = state.macauDate;
  form.elements.flightTime.value = state.flightTime;
  form.elements.hotel.value = state.hotel;
  function timingHtml() {
    const timing = airportTiming(state.flightTime);
    host.querySelector('[data-journey-timing]').innerHTML = timing ? `<b>공항 ${esc(timing.airport)} 도착 목표</b><p>숙소 ${esc(timing.leave)} 출발 계획 · ${esc(timing.departure)} 항공편 기준. 이동 90분은 임시 여유값이며 실측 교통시간이 아닙니다. 심야 열차·버스 운행과 카운터 개장 확인.</p>` :
      '<b>7일 밤에 공항으로 이동합니다</b><p>기본안: 21:30 숙소 출발, 22:30~23:00 공항 도착 목표. 8일 02~05시편 중 정확한 시각을 입력하면 3시간 전 공항 도착 기준을 계산합니다.</p>';
  }
  function render() {
    const days = journeyDays(data, state);
    if (section === 'days') {
      const d = days.find(x => x.date === selected) || days[0];
      body.innerHTML = `<nav class="journey-nav" aria-label="날짜 선택">${days.map(x => `<button type="button" data-journey-date="${x.date}" aria-pressed="${x.date === d.date}">${esc(x.date.slice(5).replace('-', '/'))}</button>`).join('')}</nav>
        <h3>${esc(d.label)} · ${esc(d.theme)}</h3><div class="journey-alert">${d.notes.map(esc).join('<br>')}</div>
        <div class="journey-actions"><button type="button" class="secondary" data-journey-map>이날 동선을 지도에 보기</button>${state.hotel ? link(maps(state.hotel), '내 숙소 지도') : ''}</div>${stopsHtml(d, state)}`;
    } else if (section === 'prepare') {
      body.innerHTML = `<h3>출발 전 체크리스트</h3><p data-journey-progress aria-live="polite"></p><div class="journey-stop">${data.checklist.map(x => `<label class="journey-check"><input type="checkbox" data-check="${esc(x.id)}"${state.checked[x.id] ? ' checked' : ''}><span>${esc(x.text)}</span></label>`).join('')}</div><details><summary>예약·숙소에서 놓치기 쉬운 점</summary><ul>${data.assumptions.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>`;
      progress();
    } else if (section === 'activities') {
      const items = data.activities.filter(a => (city === 'all' || a.city === city) && (!onlySaved || state.checked[a.id]));
      body.innerHTML = `<div class="tools"><label>지역<select data-journey-city><option value="all">전체</option><option value="홍콩">홍콩</option><option value="마카오">마카오</option></select></label><label class="journey-check"><input type="checkbox" data-only-saved${onlySaved ? ' checked' : ''}> 찜한 곳만</label></div><p class="hint">${items.length}개 · 반나절·하루 코스는 기존 일정과 교체하세요. 찜은 일정에 자동 추가되지 않습니다.</p><div class="place-grid">${items.map(a => `<article class="journey-stop"><p class="eyebrow">${esc(a.city)} · ${esc(a.category)}</p><h3>${esc(a.name)}</h3><p class="hint">${esc(activityWhen(a, state))} · ${esc(a.duration)}</p><p>${esc(a.note)}</p><div class="journey-actions">${link(maps(a.query), '지도·길찾기')}<label class="journey-check"><input type="checkbox" data-check="${esc(a.id)}"${state.checked[a.id] ? ' checked' : ''}> 찜하기</label></div></article>`).join('') || '<p>찜한 놀거리가 없습니다. 전체 목록에서 골라 주세요.</p>'}</div>`;
      body.querySelector('[data-journey-city]').value = city;
    } else {
      body.innerHTML = `<ul>${data.assumptions.map(x => `<li>${esc(x)}</li>`).join('')}</ul><div class="place-grid">${data.tips.map(t => `<article class="journey-stop"><h3>${esc(t.title)}</h3><p>${esc(t.body)}</p></article>`).join('')}</div><details open><summary>공식 출처 · 날씨·예약 확인</summary><div class="journey-sources">${data.sources.map(s => link(s.url, s.name)).join('')}</div></details>`;
    }
  }
  function progress() { const node = body.querySelector('[data-journey-progress]'); if (node) node.textContent = `${data.checklist.filter(x => state.checked[x.id]).length} / ${data.checklist.length} 준비 완료`; }
  form.addEventListener('submit', e => {
    e.preventDefault();
    state = normalizeJourneyState({...state, macauDate: form.elements.macauDate.value, flightTime: form.elements.flightTime.value, hotel: form.elements.hotel.value.trim()}, data);
    save(); timingHtml(); render();
  });
  host.addEventListener('change', e => {
    const id = e.target.dataset.check;
    if (id) { state.checked[id] = e.target.checked; save(); progress(); if (section === 'activities' && onlySaved) render(); }
    if (e.target.matches('[data-journey-city]')) { city = e.target.value; render(); }
    if (e.target.matches('[data-only-saved]')) { onlySaved = e.target.checked; render(); }
  });
  host.addEventListener('click', async e => {
    const button = e.target.closest('button'); if (!button) return;
    if (button.dataset.journeyTab) {
      section = button.dataset.journeyTab;
      host.querySelectorAll('[data-journey-tab]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
      render();
    }
    if (button.dataset.journeyDate) { selected = button.dataset.journeyDate; render(); }
    if (button.hasAttribute('data-journey-map')) {
      const days = journeyDays(data, state); onMap(days, days.findIndex(d => d.date === selected));
    }
    if (button.hasAttribute('data-journey-download')) {
      const url = URL.createObjectURL(new Blob([offlineJourneyHtml(data, state)], {type: 'text/html;charset=utf-8'}));
      const a = document.createElement('a'); a.href = url; a.download = 'hongkong-macau-2026-10.html'; document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000); status('수첩을 저장했습니다. 기기의 다운로드 목록에서 열어 보세요.');
    }
    if (button.hasAttribute('data-journey-copy')) {
      const text = journeyDays(data, state).map(d => `${d.date} ${d.theme}\n${d.notes.join('\n')}\n${d.stops.map(s => `${s.time} ${s.name}\n${s.note}`).join('\n')}`).join('\n\n');
      try { await navigator.clipboard.writeText(text); status('전체 일정을 복사했습니다.'); }
      catch { notice('복사를 허용하지 않는 브라우저입니다. 오프라인 수첩 저장을 이용해 주세요.', true); status('복사하지 못했습니다. 오프라인 저장을 이용하세요.'); }
    }
  });
  timingHtml(); render();
}
