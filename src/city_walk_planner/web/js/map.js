/* Leaflet 지도 — 다크 타일 · 커스텀 핀 · 타일 실패 폴백 (설계서 §6.15 · NFR-015 · R4)
 *
 * 지도는 **없어도 되는 부품**이다. Leaflet 이 로드되지 않았거나 타일 서버가 죽어도
 * 목록·타임라인·경고·정산은 전부 그대로 동작해야 한다. 그래서 이 모듈의 모든 진입점은
 * "지도가 없다"를 정상 경로로 취급한다.
 *
 * 타일만이 유일하게 남은 런타임 외부 요청이다(CARTO dark_all — 원본과 같은 타일).
 * 나머지 자산은 전부 저장소 안에 있다(AC-042).
 */

import { escapeHtml, link } from './format.js';
import { icon } from './icons.js';

export function ratingLabel(place) {
  const evidence = place.review || place;
  return Number.isFinite(evidence.rating) && evidence.rating >= 1 && evidence.rating <= 5
    && Number.isInteger(evidence.review_count) && evidence.review_count > 0
    ? `★ ${evidence.rating.toFixed(1)} · ${evidence.review_count.toLocaleString('ko-KR')}개 평가`
    : '평가 정보 없음';
}

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
const TILE_ERROR_WINDOW_MS = 10000;
const TILE_ERROR_THRESHOLD = 5;

/** 같은 좌표에 있는 장소들을 한 핀으로 묶는다 (REQ-019).
 *
 * **순수 함수로 떼어 둔 이유**: 큐레이션 좌표의 상당수가 건물 단위여서 랜드마크
 * 한 곳에만 6개 식당이 있다. 그대로 찍으면 핀이 완전히 겹쳐 하나처럼 보이고 맨 위
 * 하나만 눌린다. 이 묶는 규칙이 이 기능의 유일한 진짜 로직인데, Leaflet 안에 두면
 * 브라우저 없이는 한 번도 실행해 볼 수 없다.
 *
 * 좌표가 없는 항목은 지도에 올릴 방법이 없으므로 제외한다(목록에는 남는다).
 *
 * @returns {{lat:number, lng:number, items:object[]}[]} 입력 순서를 보존한 그룹들
 */
export function groupByCoordinate(places, digits = 5) {
  const groups = new Map();
  for (const place of places || []) {
    if (place == null || place.lat == null || place.lng == null) continue;
    const key = `${place.lat.toFixed(digits)},${place.lng.toFixed(digits)}`;
    if (!groups.has(key)) groups.set(key, { lat: place.lat, lng: place.lng, items: [] });
    groups.get(key).items.push(place);
  }
  return [...groups.values()];
}

/** 핀 팝업 본문. 팝업을 누르면 목록의 그 항목으로 간다(`_onPopupClick`). */
export function popupHtml(title, lines = [], go = '목록에서 보기') {
  const body = lines.filter(Boolean).map((line) => `<span class="map-pop-line">${line}</span>`).join('');
  return `<div class="map-pop"><b>${title}</b>${body}${go ? `<button type="button" class="map-pop-go">${go} ›</button>` : ''}</div>`;
}

/** 지도 → 목록: 그 항목으로 스크롤하고 잠깐 강조한다. */
export function scrollToItem(node) {
  if (!node) return;
  node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  node.classList.remove('map-hit');
  void node.offsetWidth;  // 같은 항목을 연달아 눌러도 강조가 다시 보이게
  node.classList.add('map-hit');
}

/** 긴 설명은 팝업에서 한두 줄로 자른다. */
export function shortText(value, max = 70) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 묶인 핀에 찍을 라벨 — 여럿이면 개수, 하나면 별 개수. */
export function pinLabel(group) {
  if (group.items.length > 1) return String(group.items.length);
  return '★'.repeat(Math.max(1, Math.min(3, group.items[0].stars || 1)));
}

export class TripMap {
  constructor(containerId, { onMarkerClick, onTileTrouble } = {}) {
    this.containerId = containerId;
    this.onMarkerClick = onMarkerClick || (() => {});
    this.onTileTrouble = onTileTrouble || (() => {});
    this.map = null;
    this.markers = new Map();  // spot_id -> marker
    this.nearbyMarkers = [];   // 근처 장소 (REQ-017) — 일정 스팟과 **별도 레이어**다.
    this.curatedMarkers = [];  // 미쉐린 큐레이션 (REQ-019) — 또 다른 레이어.
    this.meMarker = null;
    this.tileErrors = [];
    this.available = false;
  }

  /** 지도를 세운다. 실패하면 false 를 돌려주고 앱은 계속 간다. */
  init() {
    const container = document.getElementById(this.containerId);
    if (!container) return false;
    if (typeof L === 'undefined') {
      // 벤더 파일이 빠졌거나 차단됐다. 지도 자리에 이유를 적고 넘어간다.
      this.onTileTrouble('지도 라이브러리를 불러오지 못했습니다 — 목록과 계산은 정상입니다.');
      container.classList.add('map-offline');
      return false;
    }
    try {
      this.map = L.map(this.containerId, { zoomControl: false, attributionControl: false })
        .setView([22.30, 114.10], 11);
      const tiles = L.tileLayer(TILE_URL, { maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin' });
      tiles.on('tileerror', () => this._noteTileError());
      tiles.addTo(this.map);
      L.control.attribution({ prefix: false }).addAttribution(TILE_ATTRIBUTION).addTo(this.map);
      this.available = true;
      setTimeout(() => this.invalidate(), 300);
      return true;
    } catch (error) {
      console.error('지도 초기화 실패', error);
      this.onTileTrouble('지도를 초기화하지 못했습니다 — 목록과 계산은 정상입니다.');
      container.classList.add('map-offline');
      this.map = null;
      this.available = false;
      return false;
    }
  }

  _noteTileError() {
    const now = Date.now();
    this.tileErrors = this.tileErrors.filter((t) => now - t < TILE_ERROR_WINDOW_MS);
    this.tileErrors.push(now);
    if (this.tileErrors.length >= TILE_ERROR_THRESHOLD) {
      const container = document.getElementById(this.containerId);
      if (container) container.classList.add('map-offline');
      this.onTileTrouble('지도 타일을 불러오지 못했습니다 — 목록과 계산은 정상입니다.');
      this.tileErrors = [];
    }
  }

  invalidate() {
    if (this.map) this.map.invalidateSize();
  }

  /** 팝업(링크 제외)을 누르면 `go` 를 부른다. Leaflet 은 팝업을 열 때마다 본문을 다시 그리므로
   *  본문이 아니라 그대로 남는 바깥 틀(`getElement()`)에 묶는다. */
  _onPopupClick(marker, go) {
    if (!go) return marker;
    return marker.on('popupopen', (event) => {
      const frame = event.popup.getElement();
      if (frame) frame.onclick = (click) => {
        if (!click.target.closest('.map-pop') || click.target.closest('a')) return;
        marker.closePopup(); go();
      };
    });
  }

  /** 지도가 화면 밖이면 지도로 스크롤한다(데스크톱처럼 목록 옆에 붙어 있으면 그대로 둔다). */
  reveal() {
    const node = document.getElementById(this.containerId);
    if (!node) return;
    const box = node.getBoundingClientRect();
    if (box.top < 0 || box.bottom > window.innerHeight) node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /** 목록 항목 → 지도: 지도로 스크롤하고 그 핀으로 옮겨 팝업을 연다. */
  _show(marker, zoom = 16) {
    if (!this.map || !marker) return false;
    this.reveal();
    this.invalidate();
    this.map.stop();
    this.map.setView(marker.getLatLng(), Math.max(zoom, this.map.getZoom()), { animate: false });
    // 핀이 가운데라 위로 뜨는 팝업이 지도 위쪽을 넘을 수 있다. Leaflet 의 autoPan 은 애니메이션이라
    // 막 스크롤·탭 전환된 지도에서 밀릴 수 있으니, 여기서는 즉시 내려서 팝업 전체가 보이게 한다.
    const popup = marker.getPopup();
    const autoPan = popup?.options.autoPan;
    if (popup) popup.options.autoPan = false;
    marker.openPopup();
    if (popup) popup.options.autoPan = autoPan;
    const frame = document.getElementById(this.containerId).getBoundingClientRect();
    const box = popup?.getElement()?.getBoundingClientRect();
    const overflow = box ? box.top - frame.top - 16 : 0;
    if (overflow < 0) this.map.panBy([0, overflow], { animate: false });
    return true;
  }

  /** 지도에 핀이 없는 항목(예: 일정에 안 넣은 가게)을 임시 핀 하나로 보여 준다. */
  showPoint(point, { go } = {}) {
    if (!this.map || !point || !Number.isFinite(point.lat) || !Number.isFinite(point.lng)) return false;
    if (this.pointMarker) this.pointMarker.remove();
    this.pointMarker = this._onPopupClick(L.marker([point.lat, point.lng], {
      icon: L.divIcon({ className: '', html: '<div class="nearpin"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }),
    }).addTo(this.map).bindPopup(popupHtml(escapeHtml(point.name), point.lines || []), { autoPanPadding: [16, 16] }), go);
    return this._show(this.pointMarker);
  }

  _pin(color, label) {
    color = ({'#22d3ee':'#28726d','#f472b6':'#a56a65','#ff2e88':'#a56a65',
      '#fbbf24':'#a58135','#f7b733':'#a58135','#a78bfa':'#7a7296'})[color] || color;
    return L.divIcon({
      className: '',
      iconSize: [22, 22],
      iconAnchor: [11, 22],
      popupAnchor: [0, -22],
      html: `<div class="pin" style="background:${color};color:${color}"><i>${label}</i></div>`,
    });
  }

  /** 서버 상태의 모든 스팟을 다시 찍는다. 일자 색이 곧 핀 색이다(원본과 동일). */
  render(days) {
    if (!this.map) return;
    for (const marker of this.markers.values()) marker.remove();
    this.markers.clear();
    for (const day of days || []) {
      day.spots.forEach((spot, index) => {
        const marker = L.marker([spot.lat, spot.lng], { icon: this._pin(day.color, index + 1) })
          .addTo(this.map)
          .bindPopup(popupHtml(escapeHtml(spot.name), [
            `${escapeHtml(spot.time_label)} · ${escapeHtml(spot.name_original || day.title)}`,
            spot.summary ? escapeHtml(shortText(spot.summary)) : '',
            `${icon('clock')} ${escapeHtml(spot.hours_text || '정보 없음')}`,
          ]), { autoPanPadding: [16, 16] });
        this._onPopupClick(marker, () => this.onMarkerClick(day.day_index, spot.id));
        this.markers.set(spot.id, marker);
      });
    }
  }

  /** 근처 장소를 찍는다 (REQ-017).
   *
   *  일정 스팟 핀과 **모양이 달라야 한다** — 같은 모양이면 "내 일정"과 "그냥 근처에 있는
   *  가게"가 지도에서 구분되지 않는다. 스팟은 번호가 박힌 물방울, 이것은 점이다.
   */
  renderNearby(places, { onPick, onGo, numbered = false } = {}) {
    this.clearNearby();
    if (!this.map) return;
    for (const [index, place] of (places || []).entries()) {
      const marker = L.marker([place.lat, place.lng], {
        icon: L.divIcon({
          className: '',
          iconSize: numbered ? [44, 44] : [14, 14],
          iconAnchor: numbered ? [22, 22] : [7, 7],
          popupAnchor: [0, -8],
          html: numbered ? `<div class="picker-pin">${index + 1}</div><span class="picker-rating">${escapeHtml(ratingLabel(place))}</span>` : '<div class="nearpin"></div>',
        }),
      }).addTo(this.map).bindPopup(popupHtml(escapeHtml(place.name), [
        escapeHtml(place.category_label || place.area || place.category || '')
          + (Number.isFinite(place.distance_m) ? ` · ${Math.round(place.distance_m)}m` : ''),
        numbered || place.review || Number.isFinite(place.rating) ? escapeHtml(ratingLabel(place)) : '',
        numbered && place.review ? `${link(place.review.source_url,place.review.source || '평가 출처')} · 조회 ${escapeHtml((place.review.fetched_at || '').slice(0,10))}` : '',
        place.trend_reason ? escapeHtml(shortText(place.trend_reason)) : '',
      ], onGo ? '목록에서 보기' : ''), {autoPan: !numbered, autoPanPadding: [16, 16]});
      if (onPick) marker.on('click', () => onPick(place));
      this._onPopupClick(marker, onGo && (() => onGo(place)));
      marker.place = place;
      this.nearbyMarkers.push(marker);
    }
  }

  /** 목록의 근처 장소 하나 → 지도. 같은 객체나 같은 좌표의 핀을 찾는다. */
  focusNearby(place) {
    const same = (m) => m.place === place || (m.getLatLng().lat === place.lat && m.getLatLng().lng === place.lng);
    return this._show(this.nearbyMarkers.find(same));
  }

  clearNearby() {
    for (const marker of this.nearbyMarkers) marker.remove();
    this.nearbyMarkers = [];
  }

  /** 미쉐린 큐레이션 목록을 찍는다 (REQ-019).
   *
   *  **같은 좌표를 여러 곳이 공유한다.** 좌표 상당수가 건물 단위여서 랜드마크 한
   *  곳에만 6개 식당이 있다 — 그대로 찍으면 핀 6개가 완전히 겹쳐 하나처럼 보이고
   *  맨 위 하나만 눌린다. 그래서 **좌표로 묶어 핀 하나**를 찍고 팝업에 전부 적는다.
   *  묶인 개수는 핀에 숫자로 보인다(클러스터링 라이브러리 없이 되는 선).
   *
   *  좌표가 없는 항목은 지도에 올릴 방법이 없다 — 목록에는 남아 있다.
   */
  renderCurated(places, { onGo } = {}) {
    this.clearCurated();
    if (!this.map) return;

    for (const group of groupByCoordinate(places)) {
      const label = pinLabel(group);
      const lines = group.items
        .map((p) => `${'★'.repeat(p.stars)} ${escapeHtml(p.name)}`)
        .join('<br>');
      const where = group.items[0].address || group.items[0].district || '';
      const marker = L.marker([group.lat, group.lng], {
        icon: L.divIcon({
          className: '',
          iconSize: [24, 24],
          iconAnchor: [12, 12],
          popupAnchor: [0, -12],
          html: `<div class="curpin"><i>${label}</i></div>`,
        }),
      }).addTo(this.map).bindPopup(
        popupHtml(lines, [where ? `<span class="curpopaddr">${escapeHtml(where)}</span>` : ''], onGo ? '목록에서 보기' : ''),
        { autoPanPadding: [16, 16] },
      );
      this._onPopupClick(marker, onGo && (() => onGo(group.items[0])));
      this.curatedMarkers.push(marker);
    }
  }

  clearCurated() {
    for (const marker of this.curatedMarkers) marker.remove();
    this.curatedMarkers = [];
  }

  /** 목록에서 고른 한 곳으로 지도를 옮긴다. 좌표가 없으면 아무것도 하지 않는다. */
  focusCurated(place) {
    if (!this.map || !place || place.lat == null) return;
    const key = `${place.lat.toFixed(5)},${place.lng.toFixed(5)}`;
    const marker = this.curatedMarkers.find(
      (m) => `${m.getLatLng().lat.toFixed(5)},${m.getLatLng().lng.toFixed(5)}` === key,
    );
    this._show(marker);
  }

  /** 일정 항목 → 지도. 핀이 없으면(좌표 없음) false. */
  focus(spot, zoom = 15) {
    if (!this.map || !spot) return false;
    return this._show(this.markers.get(spot.id), zoom);
  }

  focusDay(day) {
    if (!this.map) return;
    if (this.routeLine) { this.routeLine.remove(); this.routeLine = null; }
    const selected = new Set(day?.spots.map(spot => spot.id) || []);
    for (const [id, marker] of this.markers) marker.setOpacity(selected.has(id) ? 1 : 0.35);
    if (!day?.spots.length) return;
    const points = day.spots.map(spot => [spot.lat, spot.lng]);
    this.invalidate();
    this.map.fitBounds(points, { padding: [28, 28], maxZoom: 15, animate: false });
    this.routeLine = L.polyline(points, { color: '#2a6f96', weight: 3, dashArray: '6 8', opacity: 0.7 }).addTo(this.map);
  }

  showMe(me) {
    if (!this.map || !me) return;
    if (!this.meMarker) {
      this.meMarker = L.marker([me.lat, me.lng], {
        icon: L.divIcon({ className: '', html: '<div class="me"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
      }).addTo(this.map);
      this.map.flyTo([me.lat, me.lng], 14);
    } else {
      this.meMarker.setLatLng([me.lat, me.lng]);
    }
  }

  flyToMe(me) {
    if (this.map && me) this.map.flyTo([me.lat, me.lng], 15);
  }
}
