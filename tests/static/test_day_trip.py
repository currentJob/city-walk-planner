"""Trips saved with the retired Macau excursion still render their notes, escaped."""
from tests.static.test_plan_map import PROJECT_ROOT, _run_node, node_only


@node_only
def test_saved_excursion_notes_render_escaped():
    module = (PROJECT_ROOT / 'src/city_walk_planner/web/js/day-trip.js').as_uri()
    result = _run_node(f"""
      import {{excursionHtml}} from {module!r};
      const info={{title:'<script>x</script>',reason:'r',transport:['t'],fare:'f',caution:'c',tips:['tip'],
        checked_at:'2026-09-18',sources:[{{url:'https://www.gov.mo/',name:'gov.mo'}}]}};
      console.log(JSON.stringify({{
        html:excursionHtml({{excursion:info}}),
        none:excursionHtml({{}})
      }}));
    """)
    assert 'gov.mo' in result['html'] and '<script>' not in result['html']
    assert result['none'] == ''
