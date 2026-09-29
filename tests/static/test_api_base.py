"""The backend address comes only from the build config (or same origin); nothing on the page can redirect it."""
from tests.static.test_plan_map import PROJECT_ROOT, _run_node, node_only

SCRIPT = """
  globalThis.window={{CWP_CONFIG:{{apiBase:{baked!r}}}}};
  const store={{hl_api_base:'https://old.example.com'}};
  globalThis.localStorage={{getItem:k=>store[k]??null,setItem:(k,v)=>store[k]=v,removeItem:k=>delete store[k]}};
  globalThis.location={{search:'?api=https://evil.example.com'}};
  const m=await import({module!r});
  console.log(JSON.stringify({{base:m.apiBase(),stored:store.hl_api_base??null,setter:typeof m.setApiBase}}));
"""


def _resolve(baked: str, tag: str) -> dict:
    module = (PROJECT_ROOT / "src/city_walk_planner/web/js/api.js").as_uri() + f"?{tag}"
    return _run_node(SCRIPT.format(baked=baked, module=module))


@node_only
def test_only_the_baked_config_sets_the_backend():
    worker = "https://city-walk-planner-api.example.workers.dev/"
    # ?api= and a previously remembered address are ignored; the remembered one is cleared.
    assert _resolve(worker, "a") == {"base": worker.rstrip("/"), "stored": None, "setter": "undefined"}
    # No baked address = same origin (Docker, self-host).
    assert _resolve("", "b")["base"] == ""
