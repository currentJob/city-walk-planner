const $ = id => document.getElementById(id);
let csrf = '', payload = null, revision = 0, busy = false, dirty = false;
const message = text => { $('status').textContent = text; };
const arr = value => Array.isArray(value) ? value : [];
const obj = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
function el(tag, text, className) { const n = document.createElement(tag); if (text != null) n.textContent = String(text); if (className) n.className = className; return n; }
function link(text, url) { const n = el('a', text); try { const u = new URL(url); if (!['https:', 'http:'].includes(u.protocol)) return el('span', text); n.href = u.href; n.target = '_blank'; n.rel = 'noopener noreferrer'; } catch { return el('span', text); } return n; }
function map(query) { return link('지도 열기 ↗', `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`); }
async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', cache: 'no-store', ...options,
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers}});
  if (response.status === 401) { clearPrivate(); $('login').hidden = false; throw new Error('세션이 만료되었습니다. 다시 로그인하세요.'); }
  if (!response.ok) { let body = {}; try { body = await response.json(); } catch {} throw new Error(typeof body.detail === 'string' ? body.detail : `요청 실패 (${response.status})`); }
  return response.status === 204 ? null : response.json();
}
function clearPrivate() {
  payload = null; csrf = ''; revision = 0; dirty = false;
  $('workspace').hidden = true; $('notebook').hidden = true; $('identity').textContent = ''; $('notes').value = '';
  ['days','checklist','activities','extras','title','summary','dayNav'].forEach(id => $(id).replaceChildren());
  $('import').value = ''; $('hotel').value = ''; $('flightTime').value = ''; $('variant').replaceChildren(); $('airportTiming').textContent = ''; $('hotelMap').replaceChildren();
}
async function save(next) {
  if (busy) { message('저장이 끝난 뒤 다시 시도하세요.'); return false; }
  busy = true;
  document.querySelectorAll('#workspace button, #workspace input, #workspace select, #workspace textarea').forEach(n => n.disabled = true);
  message('내 계정에 저장 중…');
  try {
    const result = await api('/api/private/journey', {method:'PUT', body:JSON.stringify({payload:next, revision})});
    payload = next; revision = result.revision; dirty = false; message('내 계정에 저장했습니다.'); return true;
  } catch(e) { message(e.message); return false; }
  finally { busy = false; document.querySelectorAll('#workspace button, #workspace input, #workspace select, #workspace textarea').forEach(n => n.disabled = false); }
}
function state() { const s = obj(payload?.state); return {...s, checked:obj(s.checked)}; }
function check(id, label) {
  const row = el('label', null, 'check'), input = el('input'); input.type = 'checkbox'; input.checked = !!state().checked[id];
  row.append(input, el('span', label));
  input.addEventListener('change', async () => {
    const previous = !input.checked, s = state(); s.checked = {...s.checked, [id]:input.checked};
    Object.assign(s, draftState(), {checked:s.checked});
    if (!await save({...payload,state:s})) input.checked = previous; else render();
    updateProgress();
  }); return row;
}
function updateProgress() {
  const items = arr(payload?.journey?.checklist); $('progress').textContent = `${items.filter(x => state().checked[x.id]).length} / ${items.length}`;
}
function activities() {
  $('activities').replaceChildren(); const query = $('search').value.toLocaleLowerCase();
  arr(payload?.journey?.activities).filter(a => JSON.stringify(a).toLocaleLowerCase().includes(query)).forEach(a => {
    const n = el('article', null, 'activity'); n.append(check(a.id, a.name), el('p', `${a.city || ''} · ${a.category || ''} · ${a.when || ''}`), el('p', a.duration), el('p', a.note));
    if(a.query) n.append(map(a.query)); $('activities').append(n);
  });
}
function section(title) { const n=el('section', null,'card'); n.append(el('h2',title)); return n; }
function render() {
  const j = obj(payload?.journey); $('empty').hidden = !!payload; $('notebook').hidden = !payload; if(!payload) return;
  $('title').textContent = j.title || '내 여행'; $('summary').textContent = j.summary || '';
  $('notes').value = state().notes || ''; ['days','dayNav','checklist','extras'].forEach(id => $(id).replaceChildren());
  renderSettings();
  activeDays().forEach((d,i) => {
    const n = section(`${d.label || d.date || ''} · ${d.theme || ''}`); n.id=`day-${i}`;
    const nav = el('a',d.date ? String(d.date).slice(5) : `${i+1}일`); nav.href=`#day-${i}`; $('dayNav').append(nav);
    arr(d.notes).forEach(note=>n.append(el('p',note)));
    arr(d.stops).forEach(s=>{const row=el('article',null,'stop'), detail=el('div'); detail.append(check(s.id,s.name),el('p',s.note)); if(s.query) detail.append(map(s.query)); row.append(el('div',s.time,'time'),detail); n.append(row);}); $('days').append(n);
  });
  arr(j.checklist).forEach(c => $('checklist').append(check(c.id,c.text))); updateProgress(); activities();
  const assumptions=section('예약 전에 확인할 것'); arr(j.assumptions).forEach(t=>assumptions.append(el('p',t))); $('extras').append(assumptions);
  const tips=section('현지에서 유용한 팁'); arr(j.tips).forEach(t=>tips.append(el('h3',t.title),el('p',t.body))); $('extras').append(tips);
  const sources=section('공식 정보 다시 확인'); sources.append(el('p',`정보 확인일: ${j.checked_at || '미기재'}`)); arr(j.sources).forEach(s=>{const p=el('p');p.append(link(s.name,s.url));sources.append(p);}); $('extras').append(sources);
}
function activeDays() {
  const j = payload.journey, s = state();
  const selected = arr(j.variants).find(v => v.id === s.variant);
  const days=structuredClone(selected?.days || j.days), timing=flightTiming();
  if(timing) days.forEach(d=>{
    d.stops=arr(d.stops).filter(stop=>!(s.flightTime<'02:00' && stop.id==='lights'));
    d.stops.forEach(stop=>{
      if(stop.id==='airport'){stop.time=`${timing.leave}까지 출발 계획`;stop.note=`공항 ${timing.airport} 도착 목표. 이동 90분과 출발 3시간 전 수속 여유를 가정합니다. 항공사 안내·실제 교통을 확인하세요.`;}
      if(stop.id==='flight'){stop.time=s.flightTime;stop.note='입력한 홍콩 현지 출발 시각입니다. 항공권·탑승 및 수하물 마감을 다시 확인하세요.';}
    });
  });
  return days;
}
function renderSettings() {
  const j=payload.journey,s=state(); $('variant').replaceChildren();
  arr(j.variants).forEach(v=>{const o=el('option',v.label);o.value=v.id;$('variant').append(o);});
  $('variant').hidden=$('variantLabel').hidden=!arr(j.variants).length;
  $('variant').value=s.variant || arr(j.variants)[0]?.id || '';
  $('flightTime').value=s.flightTime || ''; $('hotel').value=s.hotel || ''; updateAirport();
  $('hotelMap').replaceChildren();if(s.hotel)$('hotelMap').append(map(s.hotel));
}
function flightTiming(time=state().flightTime) {
  const date=arr(payload.journey.days).at(-1)?.date;
  if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time||'') || !/^\d{4}-\d{2}-\d{2}$/.test(date||''))return null;
  const ms=Date.parse(`${date}T${time}:00+08:00`);if(!Number.isFinite(ms))return null;
  const fmt=n=>new Date(n+8*3600000).toISOString().slice(5,16).replace('T',' ');
  return {departure:fmt(ms),airport:fmt(ms-180*60000),leave:fmt(ms-270*60000)};
}
function updateAirport() {
  const timing=flightTiming($('flightTime').value);
  $('airportTiming').textContent=timing ? `홍콩 현지 ${timing.departure} 출발 → 공항 ${timing.airport} 도착 목표 → 숙소 ${timing.leave} 출발 계획. 공항 3시간 전 도착·이동 90분을 가정한 값이며 항공사 안내와 실제 교통을 우선하세요. 저녁 관광은 이 시각에 맞춰 줄이세요.` : '항공권에서 정확한 출발 시각을 확인한 뒤 입력하세요.';
}
function draftState() {
  return {...state(),variant:$('variant').value,flightTime:$('flightTime').value,hotel:$('hotel').value,notes:$('notes').value};
}
$('flightTime').addEventListener('input',()=>{dirty=true;updateAirport();});
$('hotel').addEventListener('input',()=>{dirty=true;});
$('variant').addEventListener('change',()=>{dirty=true;message('변경한 방문일 계획을 저장하세요.');});
$('saveSettings').addEventListener('click',async()=>{
  const s=draftState();
  if(await save({...payload,state:s}))render();
});
$('import').addEventListener('change', async e=>{
  const file=e.target.files[0]; if(!file) return;
  try {
    if(file.size>250000) throw new Error('250 KB 이하의 JSON 파일을 선택하세요.');
    const next=JSON.parse(await file.text());
    if(!next?.journey || typeof next.journey.title!=='string' || !Array.isArray(next.journey.days)) throw new Error('여행수첩 JSON 파일을 선택하세요.');
    if(payload && !confirm('현재 계정 일정을 이 파일로 바꿀까요? 필요하면 먼저 백업하세요.')) return;
    if(await save({journey:next.journey,state:obj(next.state)})) render();
  } catch(e) {message(e.message);} finally { $('import').value=''; }
});
$('notes').addEventListener('input',()=>{dirty=true;message('메모 변경 사항을 저장하세요.');});
$('saveNotes').addEventListener('click',async()=>{if(await save({...payload,state:draftState()}))render();});
$('search').addEventListener('input',activities);
$('export').addEventListener('click',()=>{
  if(!payload) return message('먼저 일정을 가져오세요.');
  const copy={...payload,state:draftState()};
  const url=URL.createObjectURL(new Blob([JSON.stringify(copy,null,2)],{type:'application/json'}));
  const a=el('a');a.href=url;a.download='my-private-journey.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('print').addEventListener('click',()=>window.print());
$('logout').addEventListener('click',async()=>{
  if(dirty&&!confirm('저장하지 않은 메모가 있습니다. 로그아웃할까요?'))return;
  try {await api('/auth/logout',{method:'POST'});clearPrivate();$('login').hidden=false;message('로그아웃했습니다.');}catch(e){message(e.message);}
});
window.addEventListener('beforeunload',e=>{if(dirty||busy){e.preventDefault();e.returnValue='';}});
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
async function init() {
  try { const user=await api('/auth/me');csrf=user.csrf;$('identity').textContent=`@${user.login} · 비공개`; const result=await api('/api/private/journey');payload=result.payload;revision=result.revision;$('workspace').hidden=false;render();message('본인 계정만 접근할 수 있는 여행수첩입니다.'); }
  catch(e){message(e.message);$('login').hidden=false;}
}
init();
