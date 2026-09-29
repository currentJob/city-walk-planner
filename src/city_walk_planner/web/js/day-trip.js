import { escapeHtml as esc, link } from './format.js';

/** Notes for a day saved with the (retired) Macau excursion, so trips saved before its removal still read correctly. */
export function excursionHtml(day) {
  const info = day.excursion;
  if (!info) return '';
  return `<aside class="excursion-notes"><p class="eyebrow">HONG KONG → MACAO · 당일치기</p><h3>${esc(info.title)}</h3><p>${esc(info.reason)}</p>
    <ol>${info.transport.map(t=>`<li>${esc(t)}</li>`).join('')}</ol>
    <p class="hint">${esc(info.fare)}</p><p class="hint">${esc(info.caution)}</p>
    <details><summary>출발 전 준비물과 현지 팁</summary><ul>${info.tips.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></details>
    <p class="source">확인 ${esc(info.checked_at)} · ${info.sources.map(s=>link(s.url,s.name)).join(' · ')}</p></aside>`;
}
