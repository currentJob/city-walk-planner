/* 영수증 사진 → 경비 입력값 (금액 · 가게 · 날짜).
 *
 * 글자 인식은 작성자의 OCR 프로젝트(ocr-llm-page)가 배포한 모듈을 그대로 불러 쓴다
 * (`CWP_CONFIG.ocrModule`, 예: https://currentjob.github.io/ocr-llm-page/lib/korean-ocr.mjs).
 * 모델과 연산은 모두 브라우저 안에서 돈다 — 사진은 어디로도 보내지 않는다. 설정이 비어 있으면
 * (셀프 호스팅 기본값) 이 기능은 화면에 나오지 않는다.
 *
 * 인식 모델은 한국어·영문·숫자용이라 한자(중국어)는 읽지 못한다. 금액·날짜·영문 상호가 대상이고,
 * 결과는 입력 칸을 **채우기만** 한다 — 저장은 사용자가 확인한 뒤에 한다.
 */

export function ocrModuleUrl() {
  return (window.CWP_CONFIG && window.CWP_CONFIG.ocrModule) || '';
}

let enginePromise = null;

/** 모델을 한 번만 받는다(첫 사용 때 약 30MB, 이후 브라우저 캐시). 실패하면 다음에 다시 시도한다. */
function engine(onProgress) {
  enginePromise ??= import(ocrModuleUrl())
    .then(({ KoreanOCR }) => KoreanOCR.create((p) => onProgress?.(p)))
    .catch((error) => { enginePromise = null; throw error; });
  return enginePromise;
}

export async function readReceipt(file, onProgress) {
  const ocr = await engine(onProgress);
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return parseReceipt(await ocr.predict(img));
  } finally {
    URL.revokeObjectURL(url);
  }
}

// ── 순수 함수: OCR 줄 → 입력값 ─────────────────────────────────────────────

const TOTAL_RE = /(grand\s*total|total|amount\s*due|net\s*amount|합\s*계|총\s*액|총\s*금\s*액|결\s*제\s*금\s*액|받을\s*금\s*액|청\s*구\s*금\s*액)/i;
const NOT_TOTAL_RE = /(sub\s*-?\s*total|소\s*계|부가세|vat|tax|service|change|거스름|잔돈|cash|현금|card|카드)/i;
const MONEY_RE = /(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?/g;
const SKIP_MERCHANT_RE = /(receipt|invoice|tel|fax|phone|table|date|time|order|영수증|전화|주문|테이블|사업자|대표|주소|www\.|http)/i;

/** 같은 높이에 있는 조각을 한 줄로 묶는다("TOTAL" 과 "HK$ 48.40" 이 따로 잡히기 때문). */
function rows(items) {
  const lines = (items || [])
    .filter((it) => it && typeof it.text === 'string' && it.text.trim())
    .map((it) => {
      const ys = (it.box || []).map((p) => p[1]);
      const xs = (it.box || []).map((p) => p[0]);
      const top = ys.length ? Math.min(...ys) : 0;
      const bottom = ys.length ? Math.max(...ys) : 0;
      return { text: it.text.trim(), x: xs.length ? Math.min(...xs) : 0, cy: (top + bottom) / 2, h: Math.max(1, bottom - top) };
    })
    .sort((a, b) => a.cy - b.cy);
  const grouped = [];
  for (const line of lines) {
    const row = grouped.at(-1);
    if (row && Math.abs(row.cy - line.cy) < Math.min(row.h, line.h) * 0.6) row.parts.push(line);
    else grouped.push({ cy: line.cy, h: line.h, parts: [line] });
  }
  return grouped.map((row) => row.parts.sort((a, b) => a.x - b.x).map((p) => p.text).join(' '));
}

const isDateOrTime = (text) => /\d{1,4}[-./]\d{1,2}[-./]\d{1,4}|\d{1,2}:\d{2}/.test(text);

function amounts(text) {
  const cleaned = text.replace(/\d{1,4}[-./]\d{1,2}[-./]\d{1,4}/g, ' ').replace(/\d{1,2}:\d{2}(:\d{2})?/g, ' ');
  return (cleaned.match(MONEY_RE) || []).map((m) => Number(m.replace(/,/g, ''))).filter((n) => Number.isFinite(n) && n > 0);
}

function findAmount(lines) {
  // 1) '합계/TOTAL' 줄(소계·세금·거스름 제외)의 마지막 금액. 아래쪽 줄을 우선한다.
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!TOTAL_RE.test(lines[i]) || NOT_TOTAL_RE.test(lines[i])) continue;
    const here = amounts(lines[i]);
    if (here.length) return here.at(-1);
    const next = lines[i + 1] && amounts(lines[i + 1]);  // 금액이 다음 줄에 찍힌 영수증
    if (next && next.length) return next.at(-1);
  }
  // 2) 없으면 소수점 두 자리 금액 중 가장 큰 값(총액이 보통 가장 크다).
  const decimals = lines.filter((l) => !isDateOrTime(l) || /\.\d{2}\b/.test(l))
    .flatMap((l) => (l.match(/\d[\d,]*\.\d{2}\b/g) || []).map((m) => Number(m.replace(/,/g, ''))));
  return decimals.length ? Math.max(...decimals) : null;
}

function findDate(lines) {
  for (const line of lines) {
    let m = line.match(/(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})/);
    if (m) return iso(m[1], m[2], m[3]);
    m = line.match(/\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b/);  // 홍콩·영국식 일/월/년
    if (m) return iso(m[3], m[2], m[1]);
  }
  return null;
}

function iso(y, mo, d) {
  const month = Number(mo), day = Number(d);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${y}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function findMerchant(lines) {
  for (const line of lines.slice(0, 5)) {
    const letters = (line.match(/[A-Za-z가-힣]/g) || []).length;
    const digits = (line.match(/\d/g) || []).length;
    if (letters >= 3 && digits <= letters / 2 && !SKIP_MERCHANT_RE.test(line) && !TOTAL_RE.test(line)) {
      return line.replace(/\s+/g, ' ').slice(0, 60);
    }
  }
  return null;
}

/** @returns {{amount:number|null, date:string|null, merchant:string|null, lines:string[]}} */
export function parseReceipt(items) {
  const lines = rows(items);
  return { amount: findAmount(lines), date: findDate(lines), merchant: findMerchant(lines), lines };
}
