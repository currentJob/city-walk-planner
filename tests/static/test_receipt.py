"""Receipt OCR lines → expense fields: the total (not subtotal/tax/change), the date, and the shop name."""
from tests.static.test_plan_map import PROJECT_ROOT, _run_node, node_only


def _parse(lines: list) -> dict:
    module = (PROJECT_ROOT / "src/city_walk_planner/web/js/receipt.js").as_uri()
    return _run_node(f"""
      globalThis.window = {{}};
      const {{parseReceipt}} = await import({module!r});
      const box = (x, y, w = 120, h = 24) => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
      const items = {lines!r}.map(([text, x, y]) => ({{text, box: box(x, y)}}));
      const r = parseReceipt(items);
      console.log(JSON.stringify({{amount: r.amount, date: r.date, merchant: r.merchant}}));
    """)


@node_only
def test_hong_kong_receipt_read_by_the_ocr_module():
    # Layout from a real lib/korean-ocr.mjs run on a drawn receipt: TOTAL and the amount come back as separate
    # pieces on one row. (The shop name was misread in that run; it is spelled out here to test the pick.)
    lines = [["TSUI WAH RESTAURANT", 0, 46], ["Date: 2026-10-06 13:42", 0, 97], ["Milk Tea", 112, 176],
             ["28.00", 159, 170], ["16.00", 186, 197], ["Pineapple Bun", 6, 198], ["Service 10%", 10, 237],
             ["4.40", 187, 236],
             ["TOTAL", 21, 306], ["HK$ 48.40", 117, 306], ["감사합니다 Thank you", 235, 387]]
    assert _parse(lines) == {"amount": 48.4, "date": "2026-10-06", "merchant": "TSUI WAH RESTAURANT"}


@node_only
def test_korean_receipt_skips_subtotal_tax_and_card_lines():
    lines = [["영수증", 0, 0], ["을지로 국밥집", 0, 40], ["2026.09.28 12:10", 0, 80], ["국밥 2", 0, 120],
             ["18,000", 200, 120], ["소계", 0, 160], ["18,000", 200, 160], ["부가세", 0, 200], ["1,636", 200, 200],
             ["합계", 0, 240], ["18,000", 200, 240], ["카드 결제", 0, 280], ["18,000", 200, 280]]
    assert _parse(lines) == {"amount": 18000, "date": "2026-09-28", "merchant": "을지로 국밥집"}


@node_only
def test_total_on_the_next_line_and_day_first_dates():
    lines = [["MACAU CAFE", 0, 0], ["Tel 2888 1234", 0, 40], ["06/10/2026", 0, 80], ["Subtotal 90.00", 0, 120],
             ["Grand Total", 0, 160], ["99.00", 0, 200], ["Change 1.00", 0, 240]]
    assert _parse(lines) == {"amount": 99.0, "date": "2026-10-06", "merchant": "MACAU CAFE"}


@node_only
def test_without_a_total_line_the_largest_price_wins_and_nothing_is_invented():
    no_total = [["12.50", 0, 0], ["3.00", 0, 40], ["2026-13-40", 0, 80]]
    assert _parse(no_total) == {"amount": 12.5, "date": None, "merchant": None}
    assert _parse([]) == {"amount": None, "date": None, "merchant": None}
