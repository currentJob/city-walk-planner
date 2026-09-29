"""A remembered quick-tunnel address must not shadow the fixed backend baked into the Pages build."""
from tests.static.test_plan_map import PROJECT_ROOT, _run_node, node_only

SCRIPT = """
  globalThis.window={{CWP_CONFIG:{{apiBase:{baked!r}}}}};
  const store={{hl_api_base:{stored!r}}};
  globalThis.localStorage={{getItem:k=>store[k]??null,setItem:(k,v)=>store[k]=v,removeItem:k=>delete store[k]}};
  globalThis.location={{search:''}};
  const m=await import({module!r});
  console.log(JSON.stringify({{base:m.apiBase(),stored:store.hl_api_base??null}}));
"""


def _resolve(baked: str, stored: str, tag: str) -> dict:
    module = (PROJECT_ROOT / "src/city_walk_planner/web/js/api.js").as_uri() + f"?{tag}"
    return _run_node(SCRIPT.format(baked=baked, stored=stored, module=module))


@node_only
def test_dead_tunnel_is_dropped_but_custom_backend_is_kept():
    worker = "https://city-walk-planner-api.example.workers.dev"
    assert _resolve(worker, "https://old-words.trycloudflare.com", "a") == {"base": worker, "stored": None}
    assert _resolve(worker, "https://my-server.example.com", "b")["base"] == "https://my-server.example.com"
    # Without a fixed backend baked in, a remembered tunnel is still the only option — keep it.
    tunnel = "https://old-words.trycloudflare.com"
    assert _resolve("", tunnel, "c") == {"base": tunnel, "stored": tunnel}
