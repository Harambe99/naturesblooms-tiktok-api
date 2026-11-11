"""
Boot test for the single-page UI.

Why this exists: the app shipped once with a blank body. `const VIEWS={home:renderHome}`
sat in script block 1 while renderHome was declared in block 2. Separate <script>
tags run in order, so block 1 threw a ReferenceError, died, and took $, api and
route with it — the header still rendered because it is static HTML, so the page
looked fine and did nothing. Reading the code did not catch it; executing it does.

This runs the real script blocks, in order, in Node against a DOM stub. It will
not catch rendering bugs, but it catches any error thrown while the page boots.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HARNESS = r"""
// Browser semantics, reproduced faithfully: every <script> runs as its own
// script but they SHARE one script-level lexical scope, so a `const` in block 1
// is visible to block 2. node's vm with a single context does exactly that --
// plain eval() does not, which is why this harness uses vm.
const vm = require('node:vm');

// Minimal DOM stub. Enough for the boot path: element lookup, listeners,
// innerHTML assignment, dataset, classList, localStorage, matchMedia, fetch.
const made = {};
function mkEl(id){
  return made[id] = made[id] || {
    id, innerHTML:'', textContent:'', value:'', style:{}, dataset:{},
    classList:{add(){},remove(){},contains(){return false}},
    setAttribute(){}, removeAttribute(){}, getAttribute(){return ''},
    appendChild(){}, focus(){}, querySelectorAll(){return []},
    querySelector(){return null}, closest(){return null},
    addEventListener(){}, onclick:null, onchange:null, disabled:false,
  };
}
const IDS = __IDS__;
globalThis.document = {
  documentElement:{dataset:{}},
  getElementById:id => IDS.includes(id) ? mkEl(id) : null,
  querySelectorAll:()=>[],
  querySelector:()=>null,
  addEventListener(){},
  createElement:()=>mkEl('tmp'),
};
globalThis.localStorage = {
  _d:{}, getItem(k){return this._d[k] ?? null},
  setItem(k,v){this._d[k]=String(v)}, removeItem(k){delete this._d[k]},
};
globalThis.location = { search:__SEARCH__, hash:'' };
globalThis.addEventListener = ()=>{};
globalThis.matchMedia = ()=>({matches:false});
globalThis.CSS = { escape:s=>String(s) };
globalThis.alert = ()=>{};
globalThis.prompt = ()=>null;
// fetch is stubbed to a never-resolving promise: booting must not depend on a
// network round trip, and we only care about synchronous boot errors here.
globalThis.fetch = ()=>new Promise(()=>{});

const blocks = __BLOCKS__;
const errors = [];
const ctx = vm.createContext(globalThis);
for (let i = 0; i < blocks.length; i++) {
  // A browser keeps going after one script throws, so we do too -- that is how
  // the real page ended up with a dead block 1 and a header that still rendered.
  try { vm.runInContext(blocks[i], ctx, {filename:`block${i+1}.js`}); }
  catch (e) { errors.push({block:i+1, message:String(e && e.message || e)}); }
}
const probe = n => {
  try { return typeof vm.runInContext(`typeof ${n}`, ctx) === 'string'
    && vm.runInContext(`typeof ${n}`, ctx) === 'function'; }
  catch (e) { return false; }
};
const val = n => { try { return vm.runInContext(n, ctx); } catch (e) { return null; } };
console.log(JSON.stringify({
  errors,
  defined: ['renderHome','renderDaily','renderCreators','renderPnl','route','api','viewFn']
    .filter(probe),
  admin: val('ADMIN'),
  tokenbarShown: (made['tokenbar'] && made['tokenbar'].style.display) || '',
  viewHtml: (made['view'] && made['view'].innerHTML) || '',
}));
"""


def _script_blocks(token="TESTTOKEN"):
    page = ui.PAGE.replace("__ADMIN__", token)
    return re.findall(r"<script>(.*?)</script>", page, re.S)


def _element_ids():
    """Every id= in the static markup, so the DOM stub resolves what the page
    actually asks for and returns null for anything it does not."""
    page = ui.PAGE.replace("__ADMIN__", "TESTTOKEN")
    markup = re.sub(r"<script>.*?</script>", "", page, flags=re.S)
    return sorted(set(re.findall(r'id="([A-Za-z0-9_\-]+)"', markup)))


def _run(token="TESTTOKEN", search="?admin=TESTTOKEN"):
    blocks = _script_blocks(token)
    assert blocks, "no <script> blocks found in ui.PAGE"
    harness = (HARNESS
               .replace("__BLOCKS__", json.dumps(blocks))
               .replace("__SEARCH__", json.dumps(search))
               .replace("__IDS__", json.dumps(_element_ids())))
    p = subprocess.run([NODE, "-e", harness],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"node failed: {p.stderr[:2000]}"
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_every_script_block_executes_without_error():
    """This is the test that would have caught the blank page."""
    out = _run()
    assert out["errors"] == [], (
        "a script block threw while booting: "
        + "; ".join(f"block {e['block']}: {e['message']}" for e in out["errors"]))


def test_all_view_renderers_and_router_exist_after_boot():
    out = _run()
    for name in ("renderHome", "renderDaily", "renderCreators", "renderPnl",
                 "route", "api", "viewFn"):
        assert name in out["defined"], f"{name} was not defined after boot"


def test_views_are_resolved_lazily_not_in_an_early_literal():
    """Guard the specific regression: the router must not name the render
    functions in a top-level object literal in an earlier block."""
    blocks = _script_blocks()
    router_i = next(i for i, b in enumerate(blocks) if "function currentRoute" in b)
    defs = {}
    for i, b in enumerate(blocks):
        for name in re.findall(r"(?:async\s+)?function\s+(render\w+)", b):
            defs[name] = i
    later = {n for n, i in defs.items() if i > router_i}
    if not later:
        return
    # Only TOP-LEVEL code in the router block matters: a reference inside a
    # function body is resolved when that function is called, by which time the
    # later block has run. Track brace depth to tell the two apart.
    depth = 0
    for line in blocks[router_i].splitlines():
        s = line.strip()
        if not s.startswith("//"):
            for name in later:
                if depth == 0 and re.search(rf"[:=]\s*{name}\s*[,}}\s]", s):
                    pytest.fail(f"{name} is evaluated at top level in the router "
                                f"block but declared in a later <script> — this is "
                                f"the blank-page bug. Line: {s[:90]}")
        depth += line.count("{") - line.count("}")


def test_page_surfaces_a_script_error_instead_of_rendering_nothing():
    """A silent blank page is the failure we are guarding against."""
    assert "addEventListener('error'" in ui.PAGE
    assert "could not start" in ui.PAGE


def test_server_injected_token_is_used_when_the_url_has_no_param():
    """The regression this guards: __ADMIN__ is rewritten EVERYWHERE in ui.py,
    so using it as a 'missing token' sentinel made the guard compare the real
    token against itself. Result was 'Could not load. no admin token' on a page
    that had a perfectly good token."""
    out = _run(token="INJECTEDTOKEN", search="")
    assert out["errors"] == [], out["errors"]
    assert out["admin"] == "INJECTEDTOKEN", \
        f"server-injected token was not picked up (got {out['admin']!r})"
    assert out["tokenbarShown"] != "flex", \
        "token bar was shown even though a token was injected"
    assert "no admin token" not in out["viewHtml"]


def test_url_param_token_is_used():
    out = _run(token="", search="?admin=FROMURL")
    assert out["errors"] == [], out["errors"]
    assert out["admin"] == "FROMURL"


def test_token_bar_appears_only_when_there_is_genuinely_no_token():
    out = _run(token="", search="")
    assert out["errors"] == [], out["errors"]
    assert out["admin"] == ""
    assert out["tokenbarShown"] == "flex"


def test_admin_sentinel_is_never_used_in_a_comparison():
    """Static guard: __ADMIN__ may be an injection point, never a sentinel."""
    for line in ui.PAGE.splitlines():
        if "__ADMIN__" in line and ("===" in line or "!==" in line):
            pytest.fail(f"__ADMIN__ used in a comparison (it gets rewritten): {line.strip()[:100]}")


def test_money_puts_the_sign_before_the_currency_symbol():
    """$-576.72 reads like a typo on a finance page; -$576.72 is correct."""
    blocks = _script_blocks()
    fmt = next(b for b in blocks if "const m=n=>" in b)
    harness = (HARNESS.replace("__BLOCKS__", json.dumps([fmt + """
globalThis.__out = [m(-576.72), m(0), m(1234.5), m0(-7205.48), m(null),
                    num('33,33'), num('33.33'), num(''), num(null)];
"""])).replace("__SEARCH__", '""').replace("__IDS__", json.dumps(_element_ids())))
    harness = harness.replace(
        "console.log(JSON.stringify({",
        "console.log(JSON.stringify({ out: vm.runInContext('__out', ctx),")
    p = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[:1500]
    out = json.loads(p.stdout.strip().splitlines()[-1])["out"]
    assert out[0] == "-$576.72", f"negative money formatted as {out[0]!r}"
    assert out[1] == "$0.00"
    assert out[2] == "$1,234.50"
    assert out[3] == "-$7,205"
    assert out[4] == "—"
    # comma-decimal locales must not silently corrupt a rate
    assert out[5] == 33.33, f"num('33,33') -> {out[5]!r}"
    assert out[6] == 33.33
    assert out[7] is None and out[8] is None


def test_rate_fields_are_not_locale_sensitive_number_inputs():
    """type=number renders 33.33 as '33,33' in comma-decimal locales."""
    for cls in ("r_rate", "r_hourly", "a_rate", "a_hourly", "c_amt"):
        for line in ui.PAGE.splitlines():
            if cls in line and "<input" in line:
                assert 'type="number"' not in line, \
                    f"{cls} is a number input — use inputmode + num(): {line.strip()[:90]}"
