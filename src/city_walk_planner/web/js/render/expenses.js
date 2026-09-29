/* 경비 기록 (설계서 §6.20 · REQ-007 · AC-012 · AC-013 · AC-029)
 *
 * 금액은 화면에서만 'HK$12.34' 이고, 서버로는 **정수 cent** 로만 보낸다(NFR-014).
 * 원화 환산값(amount_krw)은 서버가 계산해 준 것을 그대로 찍는다 — 환율이 없으면 null 이고,
 * 그때는 HKD 만 보인다. 환율이 죽었다고 경비 기록이 막히면 안 된다.
 */

import { escapeHtml, formatHkd, formatKrw } from '../format.js';
import { icon } from '../icons.js';

function participantOptions(participants, selectedId) {
  return participants
    .map((p) => `<option value="${escapeHtml(p.id)}"${p.id === selectedId ? ' selected' : ''}>`
      + `${escapeHtml(p.display_name)}</option>`)
    .join('');
}

/** 폼 입력값. 동기화로 다시 그려도 쓰던 값이 사라지지 않게 그리기 전에 읽어 둔다. */
function formValues(form) {
  if (!form) return null;
  const data = new FormData(form);
  return {
    payer_id: String(data.get('payer_id') || ''), amount: String(data.get('amount') || ''),
    note: String(data.get('note') || ''), spot_id: String(data.get('spot_id') || ''),
    share: data.getAll('share').map(String),
  };
}

function restoreForm(form, values) {
  if (!form || !values) return;
  for (const name of ['payer_id', 'amount', 'note', 'spot_id']) {
    if (values[name] != null && form.elements[name]) form.elements[name].value = values[name];
  }
  if (values.share) for (const box of form.querySelectorAll('[name="share"]')) box.checked = values.share.includes(box.value);
}

export function renderExpenses(container, ctx) {
  const { expenses, participants, spots, me, actions, formOpen, receipt } = ctx;
  const kept = formOpen ? formValues(container.querySelector('form')) : null;
  const items = (expenses && expenses.items) || [];
  const byId = new Map(participants.map((p) => [p.id, p]));

  const rows = items.length
    ? items.map((item) => {
      const payer = byId.get(item.payer_id);
      const krw = formatKrw(item.amount_krw);
      return '<div class="rowitem">'
        + `<div><div class="who">${escapeHtml(payer ? payer.display_name : '알 수 없음')}</div>`
        + `<div class="memo">${escapeHtml(item.note || '메모 없음')} · ${item.shares.length}명 분담</div></div>`
        + `<div class="amt">${escapeHtml(formatHkd(item.amount_minor))}`
        + `${krw ? `<small>${escapeHtml(krw)}</small>` : ''}</div>`
        + `<button class="mini danger" type="button" data-del="${escapeHtml(item.id)}" aria-label="삭제">${icon('trash')}</button>`
        + '</div>';
    }).join('')
    : '<div class="empty">아직 기록된 경비가 없습니다.</div>';

  const totalKrw = expenses ? formatKrw(expenses.total_krw) : null;
  const total = expenses
    ? `<span>합계 ${escapeHtml(formatHkd(expenses.total_minor))}${totalKrw ? ` · ${escapeHtml(totalKrw)}` : ''}</span>`
    : '';

  container.innerHTML = `<h2>경비 ${total}</h2>${rows}`
    + (formOpen ? '' : '<button class="secondary" type="button" data-act="add">＋ 경비 추가</button>')
    + (formOpen ? expenseForm(participants, spots, me, receipt) : '');

  const addBtn = container.querySelector('[data-act="add"]');
  if (addBtn) addBtn.addEventListener('click', actions.openForm);

  for (const button of container.querySelectorAll('[data-del]')) {
    button.addEventListener('click', () => actions.remove(button.dataset.del));
  }

  const form = container.querySelector('form');
  if (form) {
    // 쓰던 값 → 그 위에 영수증에서 읽은 값(한 번만 적용).
    restoreForm(form, kept);
    if (receipt && receipt.fill) restoreForm(form, receipt.fill);
    const scan = form.querySelector('[data-receipt]');
    if (scan) {
      scan.addEventListener('change', () => {
        const file = scan.files && scan.files[0];
        scan.value = '';
        if (file) actions.scanReceipt(file);
      });
    }
    form.querySelector('[data-act="cancel"]').addEventListener('click', actions.closeForm);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const amount = Number(data.get('amount'));
      const shareIds = data.getAll('share').map(String);
      if (!Number.isFinite(amount) || amount <= 0) {
        actions.invalid('금액은 0보다 커야 합니다.');
        return;
      }
      if (!shareIds.length) {
        actions.invalid('분담할 사람을 한 명 이상 고르세요.');
        return;
      }
      const spotId = String(data.get('spot_id') || '');
      actions.submit({
        payer_id: String(data.get('payer_id')),
        amount_minor: Math.round(amount * 100), // HKD → cent. 정수로 굳혀서 보낸다.
        currency: 'HKD',
        note: String(data.get('note') || '').trim(),
        spot_id: spotId || null,
        share_participant_ids: shareIds,
      });
    });
  }
}

function receiptBlock(receipt) {
  if (!receipt || !receipt.enabled) return '';
  return '<div class="receipt-scan">'
    + `<label class="receipt-btn${receipt.busy ? ' busy' : ''}">${icon('card')} 영수증 사진으로 채우기`
    + `<input type="file" accept="image/*" data-receipt${receipt.busy ? ' disabled' : ''}></label>`
    + `<p class="receipt-status" role="status">${escapeHtml(receipt.status || '사진은 이 기기에서만 읽고 어디로도 보내지 않습니다. 금액·날짜·영문 상호를 채웁니다.')}</p>`
    + '</div>';
}

function expenseForm(participants, spots, me, receipt) {
  const checks = participants.map((p) =>
    '<label><input type="checkbox" name="share" checked '
    + `value="${escapeHtml(p.id)}">${escapeHtml(p.display_name)}</label>`).join('');
  const spotOptions = ['<option value="">(스팟 연결 안 함)</option>']
    .concat(spots.map((s) => `<option value="${escapeHtml(s.id)}">Day ${s.day_index} · ${escapeHtml(s.name)}</option>`))
    .join('');
  return '<form class="form" novalidate>'
    + '<h3>경비 추가</h3>'
    + receiptBlock(receipt)
    + `<label class="field"><span>낸 사람</span><select name="payer_id">`
    + `${participantOptions(participants, me && me.id)}</select></label>`
    + '<label class="field"><span>금액 (HKD)</span>'
    + '<input name="amount" type="number" inputmode="decimal" step="0.01" min="0.01" required></label>'
    + '<label class="field"><span>메모</span><input name="note" type="text" maxlength="200"></label>'
    + `<label class="field"><span>스팟</span><select name="spot_id">${spotOptions}</select></label>`
    + `<div class="field"><span>분담</span><div class="checks">${checks}</div></div>`
    + '<div class="formbtns"><button class="primary" type="submit">기록</button>'
    + '<button class="secondary" type="button" data-act="cancel">취소</button></div>'
    + '</form>';
}
