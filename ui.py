"""
The app shell — one page, hash-routed, four views.

Design notes: the palette is drawn from the product itself (bitters: steeped
amber, dark glass green, a bruised plum for warnings) rather than a generic
dashboard blue. Tokens are defined once on :root and redefined for dark, with
[data-theme] winning over the media query in both directions. Figures use
tabular-nums so columns line up. No external assets of any kind.
"""

PAGE = r"""
<title>Nature's Blooms — operations</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --amber:#b4661a; --amber-soft:#e8a33d; --leaf:#2f5d4f; --plum:#7a2e45;
  --ink:#1c1a17; --ink-2:#4a453e; --ink-3:#7d766c;
  --bg:#faf7f2; --surface:#ffffff; --line:#e6e0d6; --line-2:#d3cabc;
  --good:#2f6f4f; --warn:#9a6400; --bad:#a3302f;
  --good-bg:#e8f2ec; --warn-bg:#fbf1dc; --bad-bg:#f8e8e7;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --serif:ui-serif,Georgia,"Iowan Old Style",serif;
  --r:10px; --sh:0 1px 2px rgba(28,26,23,.06),0 4px 14px rgba(28,26,23,.04);
}
@media (prefers-color-scheme:dark){
  :root{
    --ink:#f2ece2; --ink-2:#c3bbae; --ink-3:#8e8779;
    --bg:#15140f; --surface:#1e1c17; --line:#312d25; --line-2:#433d32;
    --amber:#e8a33d; --amber-soft:#b4661a; --leaf:#6fae96; --plum:#d98aa3;
    --good:#6fae96; --warn:#e0ad4a; --bad:#e0817f;
    --good-bg:#1a2a22; --warn-bg:#2b2316; --bad-bg:#2d1c1b;
    --sh:0 1px 2px rgba(0,0,0,.4),0 4px 14px rgba(0,0,0,.3);
  }
}
:root[data-theme="dark"]{
  --ink:#f2ece2; --ink-2:#c3bbae; --ink-3:#8e8779;
  --bg:#15140f; --surface:#1e1c17; --line:#312d25; --line-2:#433d32;
  --amber:#e8a33d; --amber-soft:#b4661a; --leaf:#6fae96; --plum:#d98aa3;
  --good:#6fae96; --warn:#e0ad4a; --bad:#e0817f;
  --good-bg:#1a2a22; --warn-bg:#2b2316; --bad-bg:#2d1c1b;
}
:root[data-theme="light"]{
  --ink:#1c1a17; --ink-2:#4a453e; --ink-3:#7d766c;
  --bg:#faf7f2; --surface:#ffffff; --line:#e6e0d6; --line-2:#d3cabc;
  --amber:#b4661a; --amber-soft:#e8a33d; --leaf:#2f5d4f; --plum:#7a2e45;
  --good:#2f6f4f; --warn:#9a6400; --bad:#a3302f;
  --good-bg:#e8f2ec; --warn-bg:#fbf1dc; --bad-bg:#f8e8e7;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:var(--amber)}
.wrap{max-width:1280px;margin:0 auto;padding:0 1.1rem 4rem}
h1,h2,h3{margin:0;font-weight:620;letter-spacing:-.01em;text-wrap:balance}
h1{font-family:var(--serif);font-size:1.5rem;font-weight:600}
h2{font-size:1.12rem;margin:1.9rem 0 .7rem}
h3{font-size:.95rem;margin:1.2rem 0 .5rem}
.n{text-align:right;font-variant-numeric:tabular-nums}
.mono{font-family:var(--mono)}
.sub{color:var(--ink-3);font-size:.84rem;margin:.3rem 0}

/* ---- top bar */
header{position:sticky;top:0;z-index:30;background:var(--bg);
  border-bottom:1px solid var(--line)}
.top{max-width:1280px;margin:0 auto;padding:.7rem 1.1rem .1rem;
  display:flex;gap:1rem;align-items:baseline;flex-wrap:wrap}
.brand{display:flex;gap:.55rem;align-items:baseline}
.dot{width:9px;height:9px;border-radius:50%;background:var(--amber);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--amber) 22%,transparent)}
.stamp{margin-left:auto;display:flex;gap:.9rem;align-items:center;
  font-size:.76rem;color:var(--ink-3);flex-wrap:wrap}
.stamp b{color:var(--ink-2);font-weight:600}
nav{max-width:1280px;margin:0 auto;padding:0 1.1rem;display:flex;gap:.15rem;
  overflow-x:auto}
nav a{padding:.6rem .85rem;font-size:.88rem;font-weight:550;color:var(--ink-3);
  text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap}
nav a:hover{color:var(--ink)}
nav a[aria-current="page"]{color:var(--ink);border-bottom-color:var(--amber)}
.subnav{display:flex;gap:.15rem;margin:.9rem 0 .2rem;border-bottom:1px solid var(--line)}
.subnav button{background:none;border:0;border-bottom:2px solid transparent;
  padding:.45rem .8rem;font:inherit;font-size:.86rem;font-weight:550;
  color:var(--ink-3);cursor:pointer}
.subnav button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--leaf)}

/* ---- controls */
button,select,input{font:inherit;color:var(--ink)}
.btn{background:var(--ink);color:var(--bg);border:0;border-radius:8px;
  padding:.44rem .9rem;font-size:.86rem;font-weight:560;cursor:pointer}
.btn:hover{opacity:.88}
.btn.ghost{background:transparent;color:var(--ink-2);border:1px solid var(--line-2)}
.btn:disabled{opacity:.5;cursor:default}
input,select{background:var(--surface);border:1px solid var(--line-2);
  border-radius:7px;padding:.35rem .5rem;font-size:.86rem}
input:focus-visible,select:focus-visible,button:focus-visible,a:focus-visible{
  outline:2px solid var(--amber);outline-offset:2px}
label{display:block;font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;
  color:var(--ink-3);margin-bottom:.18rem;font-weight:600}
.bar{display:flex;gap:.7rem;flex-wrap:wrap;align-items:flex-end;
  background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  padding:.75rem .85rem;margin:.9rem 0}

/* ---- cards */
.cards{display:grid;gap:.7rem;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
  margin:.9rem 0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  padding:.75rem .85rem;box-shadow:var(--sh);position:relative;overflow:hidden}
.card h4{margin:0 0 .3rem;font-size:.7rem;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-3);font-weight:650}
.card .v{font-size:1.4rem;font-weight:620;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em;line-height:1.15}
.card .g{font-size:.74rem;color:var(--ink-3);margin-top:.2rem}
.card.link{cursor:pointer}.card.link:hover{border-color:var(--line-2)}
.card .rail{position:absolute;left:0;top:0;bottom:0;width:3px}
.rail.ok{background:var(--good)}.rail.mid{background:var(--warn)}.rail.no{background:var(--bad)}

/* ---- tables */
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r);
  background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:.5rem .6rem;border-bottom:1px solid var(--line);text-align:left;
  vertical-align:top}
th{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-3);font-weight:650;background:var(--bg);position:sticky;top:0;
  white-space:nowrap}
th[data-k]{cursor:pointer}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:color-mix(in srgb,var(--amber) 4%,transparent)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.off{opacity:.45}
.tiny{font-size:.74rem;color:var(--ink-3)}

/* ---- pills + notes */
.pill{display:inline-block;padding:.07rem .42rem;border-radius:99px;
  font-size:.68rem;font-weight:650;letter-spacing:.02em;white-space:nowrap}
.pill.ok{background:var(--good-bg);color:var(--good)}
.pill.mid{background:var(--warn-bg);color:var(--warn)}
.pill.no{background:var(--bad-bg);color:var(--bad)}
.pill.flat{background:var(--bg);color:var(--ink-3);border:1px solid var(--line)}
.note{background:var(--surface);border:1px solid var(--line);
  border-left:3px solid var(--amber);border-radius:var(--r);
  padding:.6rem .8rem;margin:.8rem 0;font-size:.82rem;color:var(--ink-2)}
.note.warn{border-left-color:var(--warn)}
.note.bad{border-left-color:var(--bad)}
.locked{background:color-mix(in srgb,var(--ink-3) 7%,transparent)}
.empty{color:var(--ink-3);font-style:italic}
.ovr{text-decoration:underline dotted var(--amber);text-underline-offset:3px}
.msg{font-size:.82rem;padding:.4rem 0}
.grid2{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.hero{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  padding:1.1rem;box-shadow:var(--sh);margin:1rem 0}
.hero .big{font-family:var(--serif);font-size:2.1rem;font-weight:600;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em}
@media (prefers-reduced-motion:no-preference){
  .card,.hero{transition:border-color .15s ease}
}
.spin{display:inline-block;width:11px;height:11px;border:2px solid var(--line-2);
  border-top-color:var(--amber);border-radius:50%}
@media (prefers-reduced-motion:no-preference){
  .spin{animation:sp .7s linear infinite}@keyframes sp{to{transform:rotate(360deg)}}
}
</style>

<header>
  <div class="top">
    <div class="brand"><span class="dot"></span><h1>Nature's Blooms</h1></div>
    <div class="stamp">
      <span id="freshness"></span>
      <button class="btn ghost" id="refresh" title="Re-pull from TikTok">Refresh</button>
      <button class="btn ghost" id="theme" title="Light / dark">◐</button>
    </div>
  </div>
  <nav>
    <a href="#/home">Home</a>
    <a href="#/daily">Daily overview</a>
    <a href="#/creators">Creator performance</a>
    <a href="#/pnl">P&amp;L</a>
  </nav>
</header>

<div class="wrap">
  <div id="tokenbar" style="display:none" class="bar">
    <div style="flex:1"><label>admin token</label>
      <input id="adm" size="44" placeholder="paste admin token" value="__ADMIN__"></div>
    <button class="btn" id="saveadm">Save</button>
  </div>
  <div id="view"></div>
</div>

<script>
const $=i=>document.getElementById(i);
const ADMIN_KEY='nb_admin';
let ADMIN=(new URLSearchParams(location.search).get('admin')||localStorage.getItem(ADMIN_KEY)||'__ADMIN__').trim();
if(ADMIN && ADMIN!=='__ADMIN__') localStorage.setItem(ADMIN_KEY,ADMIN);
let D={};                       // cached payloads per view
let BUSY=false;

const m=n=>(n==null?'—':'$'+Number(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}));
const m0=n=>(n==null?'—':'$'+Math.round(Number(n)).toLocaleString());
const n0=n=>(n==null?'—':Number(n).toLocaleString());
const pct=n=>(n==null?'—':(Number(n)*100).toFixed(1)+'%');
const esc=s=>String(s??'').replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));

/* ---------- theme ---------- */
(function(){const t=localStorage.getItem('nb_theme');if(t)document.documentElement.dataset.theme=t;})();
$('theme').onclick=()=>{
  const cur=document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  const next=cur==='dark'?'light':'dark';
  document.documentElement.dataset.theme=next; localStorage.setItem('nb_theme',next);
};

/* ---------- fetch helpers ---------- */
async function api(path,opts){
  if(!ADMIN||ADMIN==='__ADMIN__'){ $('tokenbar').style.display='flex'; throw new Error('no admin token'); }
  const sep=path.includes('?')?'&':'?';
  const r=await fetch(path+sep+'admin='+encodeURIComponent(ADMIN),opts);
  if(!r.ok){ throw new Error('HTTP '+r.status+' — '+(await r.text()).slice(0,300)); }
  return r.json();
}
async function post(path,body){
  return api(path,{method:'POST',headers:{'Content-Type':'application/json'},
                   body:JSON.stringify(body||{})});
}
$('saveadm').onclick=()=>{ADMIN=$('adm').value.trim();localStorage.setItem(ADMIN_KEY,ADMIN);
  $('tokenbar').style.display='none';route(true);};

/* ---------- freshness stamp (EST) ---------- */
function setFresh(meta){
  if(!meta){$('freshness').innerHTML='';return;}
  const s=meta.pulled_at||{}, thru=meta.data_through;
  const age=s.age_seconds==null?'':(s.age_seconds<90?'just now':Math.round(s.age_seconds/60)+'m ago');
  $('freshness').innerHTML=
    `data through <b>${esc(thru||'—')}</b> &nbsp;·&nbsp; pulled <b>${esc(s.display||'—')} ${esc(s.zone||'')}</b>`
    +(age?` <span class="tiny">(${age})</span>`:'');
}

/* ---------- router ---------- */
// Resolved LAZILY on purpose. The render functions live in later <script> blocks,
// and those run after this one — naming them in an object literal here would throw
// a ReferenceError and kill this whole block (which is exactly what it did).
const VIEW_NAMES=['home','daily','creators','pnl'];
function viewFn(v){
  return {home:renderHome,daily:renderDaily,creators:renderCreators,pnl:renderPnl}[v];
}
function currentRoute(){
  const h=(location.hash||'#/home').replace(/^#\//,'');
  const [v,sub]=h.split('/');
  return {view:VIEW_NAMES.includes(v)?v:'home', sub:sub||''};
}
async function route(force){
  const {view}=currentRoute();
  document.querySelectorAll('nav a').forEach(a=>{
    const t=a.getAttribute('href').replace('#/','');
    if(t===view) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
  });
  try{ await viewFn(view)(force); }
  catch(e){ $('view').innerHTML=`<div class="note bad"><b>Could not load.</b> ${esc(e.message)}</div>`; }
}
// A blank page with no explanation is the worst failure mode — if any script
// block dies, say so on screen instead of rendering nothing.
addEventListener('error',e=>{
  const v=document.getElementById('view');
  if(v && !v.innerHTML.trim())
    v.innerHTML='<div class="note bad"><b>Script error — the page could not start.</b> '
      +String(e.message||e.error||'').replace(/[<>&]/g,'')+'</div>';
});
addEventListener('hashchange',()=>route(false));
$('refresh').onclick=()=>route(true);

function loading(label){
  $('view').innerHTML=`<p class="sub"><span class="spin"></span> ${esc(label)}</p>`;
}
function rag(cur,goal,higherBetter=true){
  if(goal==null||goal===0) return '';
  const r=cur/goal;
  if(higherBetter) return r>=1?'ok':(r>=.7?'mid':'no');
  return r<=1?'ok':(r<=1.3?'mid':'no');
}
function goalLine(cur,goal,fmt){
  if(goal==null) return `<div class="g">no goal set</div>`;
  const k=rag(cur,goal);
  const dot=k==='ok'?'●':(k==='mid'?'●':'●');
  return `<div class="g"><span style="color:var(--${k==='ok'?'good':k==='mid'?'warn':'bad'})">${dot}</span>
    goal ${fmt(goal)} · ${pct(goal?cur/goal:null)}</div>`;
}
</script>
<script>
/* ======================= HOME ======================= */
async function renderHome(force){
  loading('Loading summary…');
  const d=await api('/api/summary'+(force?'?force=1':''));
  D.summary=d; setFresh(d.meta);
  const s=d.day, mtd=d.mtd, r=d.retainers, p=d.pnl;
  const gGmv=d.goals?.gmv_day;
  $('view').innerHTML=`
   <div class="hero">
     <div class="sub" style="margin:0">Yesterday &middot; ${esc(d.meta.data_through||'')} &middot; order basis</div>
     <div class="big">${m(s.gmv)}</div>
     ${gGmv!=null?`<div class="sub">against a ${m0(gGmv)} daily goal — ${pct(s.gmv/gGmv)} of target</div>`
       :`<div class="sub">no daily GMV goal set yet — set one on the Daily overview</div>`}
   </div>
   <div class="cards">
     ${[
       ['Units yesterday',n0(s.units),'daily',null],
       ['Orders yesterday',n0(s.orders),'daily',null],
       ['GMV month to date',m0(mtd.gmv),'daily',null],
       ['Units month to date',n0(mtd.units),'daily',null],
       ['Posts delivered MTD',`${n0(r.posts_delivered_mtd)} <span class="tiny">/ ${n0(r.posts_committed)}</span>`,'creators',null],
       ['Retainer earned MTD',m(r.earned_to_date),'creators',null],
       ['Retainer committed',m0(r.total_committed),'creators',null],
       ['LIVE hours MTD',(r.live_hours_mtd??0).toFixed(1),'creators',null],
       ['P&L net MTD',m(p.net),'pnl',p.net>=0?'ok':'no'],
       ['Creators on retainer',n0(r.creators_on_retainer),'creators',null],
     ].map(([k,v,go,kind])=>`<div class="card link" data-go="${go}">
        ${kind?`<span class="rail ${kind}"></span>`:''}
        <h4>${k}</h4><div class="v">${v}</div></div>`).join('')}
   </div>
   <div class="note"><b>What this is.</b> One place for the numbers that drive daily
     decisions — trading yesterday, what creators delivered this month, and where the
     month's P&L stands. Each card opens the tab that owns it. Everything on this
     screen is <b>order basis</b>; the P&L's settlement rows are a different basis and
     are labelled there.</div>
   ${d.alerts?.length?`<div class="note warn"><b>Needs your attention.</b><ul style="margin:.4rem 0 0;padding-left:1.1rem">
     ${d.alerts.map(a=>`<li>${esc(a)}</li>`).join('')}</ul></div>`:''}`;
  document.querySelectorAll('.card.link').forEach(c=>c.onclick=()=>location.hash='#/'+c.dataset.go);
}
</script>
<script>
/* ======================= DAILY OVERVIEW ======================= */
async function renderDaily(force){
  loading('Pulling yesterday…');
  const d=await api('/api/daily'+(force?'?force=1':'')); D.daily=d; setFresh(d.meta);
  const g=d.goals, sd=d.shop_day, sk=d.skus_day, vo=d.video_output, r=d.retainers;
  const dayGmv=sk.gmv;
  $('view').innerHTML=`
   <h2>Business performance — ${esc(d.day)}</h2>
   <p class="sub">${esc(d.basis)}. Goals are yours to set and are saved on the server.</p>
   <div class="cards">
     <div class="card"><span class="rail ${rag(dayGmv,g.gmv_day)}"></span><h4>GMV</h4>
       <div class="v">${m(dayGmv)}</div>${goalLine(dayGmv,g.gmv_day,m0)}</div>
     <div class="card"><span class="rail ${rag(sk.units,g.units_day)}"></span><h4>Units sold</h4>
       <div class="v">${n0(sk.units)}</div>${goalLine(sk.units,g.units_day,n0)}</div>
     <div class="card"><h4>Orders</h4><div class="v">${n0(sk.orders)}</div>
       <div class="g">AOV ${m(sd.aov)}</div></div>
     <div class="card"><h4>Buyers</h4><div class="v">${n0(sd.buyers)}</div>
       <div class="g">${n0(sd.visitors)} visitors · conv ${pct(sd.conversion)}</div></div>
     <div class="card"><h4>GMV month to date</h4><div class="v">${m0(d.skus_mtd.gmv)}</div>
       ${goalLine(d.skus_mtd.gmv,g.gmv_month,m0)}</div>
     <div class="card"><h4>Units MTD</h4><div class="v">${n0(d.skus_mtd.units)}</div>
       <div class="g">COGS ${m0(d.skus_mtd.cogs)}</div></div>
   </div>

   <h3>GMV by SKU — ${esc(d.day)}</h3>
   <div class="scroll"><table><thead><tr><th>SKU</th><th class="n">GMV</th>
     <th class="n">Units</th><th class="n">Orders</th><th class="n">AOV</th>
     <th class="n">COGS each</th><th class="n">COGS</th></tr></thead><tbody>
     ${sk.rows.map(s=>`<tr${s.gmv?'':' class="off"'}>
       <td><b>${esc(s.short)}</b>${s.known?'':' <span class="pill no">unmapped</span>'}
         <br><span class="tiny">${esc(s.name)}</span></td>
       <td class="n">${m(s.gmv)}</td><td class="n">${n0(s.units)}</td>
       <td class="n">${n0(s.orders)}</td><td class="n">${m(s.aov)}</td>
       <td class="n tiny">${s.cogs_each==null?'—':m(s.cogs_each)}</td>
       <td class="n">${s.cogs_total==null?'—':m(s.cogs_total)}</td></tr>`).join('')}
     <tr><td><b>Total</b></td><td class="n"><b>${m(sk.gmv)}</b></td>
       <td class="n"><b>${n0(sk.units)}</b></td><td class="n"><b>${n0(sk.orders)}</b></td>
       <td class="n">—</td><td class="n">—</td><td class="n"><b>${m(sk.cogs)}</b></td></tr>
     </tbody></table></div>
   ${sd.buyers_by_channel&&Object.keys(sd.buyers_by_channel).length?`
   <h3>Where the buyers came from</h3>
   <div class="cards">${Object.entries(sd.buyers_by_channel).map(([k,v])=>
     `<div class="card"><h4>${esc(k.replace('_',' '))}</h4><div class="v">${n0(v)}</div>
      <div class="g">buyers</div></div>`).join('')}</div>`:''}

   <h2>Content &amp; creator performance</h2>
   <div class="cards">
     <div class="card"><h4>Creators on retainer</h4><div class="v">${n0(r.creators_on_retainer)}</div></div>
     <div class="card"><h4>Total retainers closed</h4><div class="v">${m0(r.total_committed)}</div></div>
     <div class="card"><h4>Avg cost per creator</h4><div class="v">${m(r.avg_cost_per_creator)}</div></div>
     <div class="card"><span class="rail ${rag(vo.active_retainer_creators,g.active_retainer_creators)}"></span>
       <h4>Active retainer creators</h4><div class="v">${n0(vo.active_retainer_creators)}</div>
       ${goalLine(vo.active_retainer_creators,g.active_retainer_creators,n0)}</div>
     <div class="card"><h4>Active affiliate creators</h4><div class="v">${n0(vo.active_affiliate_creators)}</div></div>
     <div class="card"><span class="rail ${rag(vo.total,g.videos_day)}"></span><h4>Videos posted</h4>
       <div class="v">${n0(vo.total)}</div>${goalLine(vo.total,g.videos_day,n0)}</div>
   </div>

   <h3>Video output — ${esc(d.day)}</h3>
   <p class="sub">Retainer ${vo.retainer_count} &middot; affiliate ${vo.affiliate_count}.
      Counted on post date, not on activity.</p>
   ${vo.total?`<div class="scroll"><table><thead><tr><th>Creator</th><th>Video</th>
     <th class="n">Views</th><th class="n">GMV</th><th>Link</th></tr></thead><tbody>
     ${[...vo.retainer,...vo.affiliate].map(v=>`<tr>
       <td><b>${esc(v.creator)}</b>${v.creator==='External Creator'?'':' <span class="pill ok">retainer</span>'}
         <br><span class="tiny">@${esc(v.handle)}</span></td>
       <td>${esc(v.title)||'<i class="empty">no title</i>'}</td>
       <td class="n">${n0(v.views)}</td><td class="n">${m(v.gmv)}</td>
       <td><a href="${esc(v.url)}" target="_blank" rel="noopener">open</a></td></tr>`).join('')}
     </tbody></table></div>`:`<p class="empty">No videos posted on ${esc(d.day)}.</p>`}

   <h2>Onboarding</h2>
   <div class="bar">
     <div><label>creators waiting for product</label>
       <input id="ob_w" type="number" min="0" style="width:7rem" value="${d.onboarding.waiting??0}"></div>
     <div><label>new creators onboarded</label>
       <input id="ob_o" type="number" min="0" style="width:7rem" value="${d.onboarding.onboarded??0}"></div>
     <button class="btn" id="ob_save">Save</button>
     <span class="msg" id="ob_msg"></span>
   </div>
   <div class="note warn">${esc(d.onboarding_note)}</div>

   <h2>Goals</h2>
   <div class="bar">
     ${[['gmv_day','GMV / day'],['units_day','units / day'],['videos_day','videos / day'],
        ['active_retainer_creators','active retainer creators'],['active_creators','active creators'],
        ['gmv_month','GMV / month']].map(([k,l])=>
       `<div><label>${l}</label><input class="goal" data-k="${k}" type="number" step="any"
         style="width:8rem" value="${g[k]??''}" placeholder="none"></div>`).join('')}
     <button class="btn" id="g_save">Save goals</button>
     <span class="msg" id="g_msg"></span>
   </div>`;

  $('ob_save').onclick=async()=>{
    $('ob_msg').textContent='saving…';
    await post('/api/store/onboarding',{waiting:$('ob_w').value,onboarded:$('ob_o').value});
    $('ob_msg').innerHTML='<span class="pill ok">saved</span>';
  };
  $('g_save').onclick=async()=>{
    const goals={}; document.querySelectorAll('.goal').forEach(i=>goals[i.dataset.k]=i.value);
    $('g_msg').textContent='saving…';
    await post('/api/store/goals',goals);
    $('g_msg').innerHTML='<span class="pill ok">saved</span>';
    setTimeout(()=>route(false),500);
  };
}
</script>
<script>
/* ======================= CREATOR PERFORMANCE ======================= */
let CSORT={k:'gmv',d:-1};
async function renderCreators(force){
  const {sub}=currentRoute();
  loading('Pulling the creator feed (this takes ~30s on a cold pull)…');
  const d=await api('/api/creators2'+(force?'?force=1':'')); D.cr=d; setFresh(d.meta);
  const tabs=`<div class="subnav">
    <button ${sub!=='roster'?'aria-selected="true"':''} data-sub="">Performance</button>
    <button ${sub==='roster'?'aria-selected="true"':''} data-sub="roster">Retainer roster</button>
  </div>`;
  $('view').innerHTML=tabs+'<div id="csub"></div>';
  document.querySelectorAll('.subnav button').forEach(b=>b.onclick=()=>{
    location.hash='#/creators'+(b.dataset.sub?'/'+b.dataset.sub:'');
  });
  if(sub==='roster') rosterTab(d); else perfTab(d);
}

function statusPill(c){
  if(!c.resolved) return '<span class="pill no" title="handle unconfirmed — reads zero, not &quot;posted nothing&quot;">unmatched</span>';
  const s=c.eff_status;
  if(s==='Inactive') return '<span class="pill no">inactive</span>';
  if(s==='Ended') return `<span class="pill mid">ended ${esc(c.end_date||'')}</span>`;
  if(s==='Paused') return '<span class="pill mid">paused</span>';
  if(c.type==='live') return c.sessions?'<span class="pill ok">live</span>':'<span class="pill flat">no lives</span>';
  if(!c.posted) return '<span class="pill flat">no posts</span>';
  if(c.pace>=.9) return '<span class="pill ok">on pace</span>';
  if(c.pace>=.4) return '<span class="pill mid">behind</span>';
  return '<span class="pill no">well behind</span>';
}

function perfTab(d){
  const all=[...d.creators,...d.live_creators];
  const t=d.totals_effective;
  const sorted=[...all].sort((a,b)=>((a[CSORT.k]??-1)-(b[CSORT.k]??-1))*CSORT.d);
  $('csub').innerHTML=`
   <p class="sub">${esc(d.window.start)} → ${esc(d.window.end)} (end exclusive) ·
     ${t.total} creators, ${t.counted} counted${t.ended?`, ${t.ended} ended`:''}${t.paused?`, ${t.paused} paused`:''}.</p>
   <div class="cards">
     <div class="card"><h4>Posts delivered</h4><div class="v">${n0(t.videos_posted)}
       <span class="tiny">/ ${n0(t.videos_committed)}</span></div></div>
     <div class="card"><h4>Retainer cost — video</h4><div class="v">${m(t.retainer_cost_video)}</div>
       <div class="g">committed ${m0(t.committed)}</div></div>
     <div class="card"><h4>LIVE hours</h4><div class="v">${(t.live_hours||0).toFixed(1)}</div>
       <div class="g">cost ${m(t.retainer_cost_live)}</div></div>
     <div class="card"><h4>Total retainer cost</h4>
       <div class="v">${m((t.retainer_cost_video||0)+(t.retainer_cost_live||0))}</div>
       <div class="g">of ${m0((t.committed||0)+(t.live_committed||0))} committed</div></div>
     <div class="card"><h4>Roster GMV</h4><div class="v">${m0(d.totals.roster_gmv+d.totals.live_gmv)}</div>
       <div class="g">off-roster ${m0(d.totals.offroster_gmv)}</div></div>
     <div class="card"><h4>GMV per $1 paid</h4>
       <div class="v">${((t.retainer_cost_video+t.retainer_cost_live)?((d.totals.roster_gmv+d.totals.live_gmv)/(t.retainer_cost_video+t.retainer_cost_live)).toFixed(2):'—')}</div></div>
   </div>
   <div class="scroll"><table><thead><tr>
     <th data-k="name">Creator</th><th>Type</th>
     <th data-k="posted" class="n">Posts</th><th class="n">Committed</th>
     <th data-k="active_videos" class="n">Still earning</th>
     <th data-k="hours" class="n">LIVE hrs</th>
     <th data-k="retainer_cost" class="n">Cost</th><th data-k="gmv" class="n">GMV</th>
     <th data-k="roi" class="n">GMV/$1</th><th>Status</th><th>Set status</th></tr></thead><tbody>
     ${sorted.map(c=>`<tr data-k="${esc(c.key)}" class="${c.eff_status==='Inactive'?'off':''}">
       <td><b>${esc(c.name)}</b>
         ${c.attribution==='owned'?' <span class="pill mid" title="brand-owned account — invisible to the affiliate export">brand</span>':''}
         ${c.source==='custom'?' <span class="pill flat">added</span>':''}
         ${c.overridden_fields?.length?` <span class="pill flat" title="overridden: ${esc(c.overridden_fields.join(', '))}">edited</span>`:''}
         <br><span class="tiny">${c.handle?'@'+esc(c.handle):'<i>no handle</i>'}</span>
         ${c.handle_note?`<br><span class="tiny" style="color:var(--warn)">⚠ see roster</span>`:''}</td>
       <td class="tiny">${c.type==='live'?'Lives':'Video'}</td>
       <td class="n">${c.type==='live'?'—':n0(c.posted)}</td>
       <td class="n tiny">${c.type==='live'?(c.hours_cap?c.hours_cap+'h':'—'):n0(c.committed_videos)}</td>
       <td class="n tiny">${c.type==='live'?'—':n0(c.active_videos)}</td>
       <td class="n">${c.type==='live'?(c.hours||0).toFixed(2):'—'}</td>
       <td class="n">${m(c.retainer_cost)}${c.prorata?` <span class="pill mid" title="pro-rated: ${c.prorata.days_engaged}/${c.prorata.days_in_month} days of ${m(c.prorata.full_committed)}">pro-rata</span>`:''}</td>
       <td class="n">${m(c.gmv)}</td>
       <td class="n">${c.roi==null?'—':c.roi.toFixed(2)}</td>
       <td>${statusPill(c)}</td>
       <td>${statusControl(c)}</td></tr>`).join('')}
   </tbody></table></div>
   <div class="note"><b>How posts are counted.</b> ${esc(d.basis_note)}</div>
   <div class="note"><b>Paused.</b> ${esc(d.status_rules.paused)}</div>
   <div class="note"><b>Ended.</b> ${esc(d.status_rules.ended)}</div>
   ${d.off_roster?.length?`<h3>Off-roster creators driving GMV</h3>
   <div class="scroll"><table><thead><tr><th>Handle</th><th class="n">Posted</th>
     <th class="n">GMV</th><th class="n">Views</th></tr></thead><tbody>
     ${d.off_roster.slice(0,15).map(o=>`<tr><td>@${esc(o.handle)}</td>
       <td class="n">${n0(o.videos)}</td><td class="n">${m(o.gmv)}</td>
       <td class="n">${n0(o.views)}</td></tr>`).join('')}</tbody></table></div>`:''}`;

  document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; CSORT=CSORT.k===k?{k,d:-CSORT.d}:{k,d:-1}; perfTab(d);});
  wireStatusControls(all);
}

function statusControl(c){
  return `<select class="st" data-k="${esc(c.key)}">
    ${['Active','Paused','Ended','Inactive'].map(s=>
      `<option ${c.eff_status===s?'selected':''}>${s}</option>`).join('')}
  </select>
  <input class="ed" data-k="${esc(c.key)}" type="date" value="${esc(c.end_date||'')}"
    style="width:8.6rem;margin-top:.25rem;display:${c.eff_status==='Ended'?'block':'none'}"
    title="date the deal ended">
  ${c.status_overridden?'<br><span class="tiny">changed here</span>':''}`;
}
function wireStatusControls(all){
  document.querySelectorAll('select.st').forEach(sel=>{
    sel.onchange=async()=>{
      const k=sel.dataset.k;
      const ed=document.querySelector(`input.ed[data-k="${CSS.escape(k)}"]`);
      ed.style.display = sel.value==='Ended' ? 'block':'none';
      if(sel.value==='Ended' && !ed.value){ ed.focus(); return; }   // wait for the date
      await saveStatus(k,sel.value,ed.value);
    };
  });
  document.querySelectorAll('input.ed').forEach(inp=>{
    inp.onchange=async()=>{
      const k=inp.dataset.k;
      const sel=document.querySelector(`select.st[data-k="${CSS.escape(k)}"]`);
      if(sel.value==='Ended' && inp.value) await saveStatus(k,'Ended',inp.value);
    };
  });
}
async function saveStatus(key,status,end_date){
  try{
    await post('/api/store/status',{key,status,end_date:end_date||null});
    route(false);
  }catch(e){ alert('Could not save status: '+e.message); }
}
</script>
<script>
/* ======================= RETAINER ROSTER ======================= */
function rosterTab(d){
  const all=[...d.creators,...d.live_creators];
  $('csub').innerHTML=`
   <p class="sub">The roster behind Creator performance. The tracker sheet seeds it;
     edits and additions here layer on top and are saved on the server.
     Handles are checked against the live TikTok feed.</p>
   <div class="scroll"><table><thead><tr>
     <th>Creator</th><th>Handle &amp; check</th><th>Type</th>
     <th class="n">Videos / cap</th><th class="n">Rate</th><th>Commission</th>
     <th>Status</th><th></th></tr></thead><tbody>
     ${all.map(c=>rosterRow(c)).join('')}
   </tbody></table></div>
   ${all.some(c=>c.handle_note)?`<div class="note warn"><b>Handle notes.</b><ul style="margin:.4rem 0 0;padding-left:1.1rem">
     ${all.filter(c=>c.handle_note).map(c=>`<li><b>${esc(c.name)}</b> — ${esc(c.handle_note)}</li>`).join('')}
   </ul></div>`:''}

   <h3>Add a retainer creator</h3>
   <div class="bar">
     <div><label>name</label><input id="a_name" size="16" placeholder="Jane Doe"></div>
     <div><label>handle</label><input id="a_handle" size="16" placeholder="janedoe"></div>
     <div><label>type</label><select id="a_type"><option value="video">Video</option>
       <option value="live">Lives</option></select></div>
     <div><label>videos / month</label><input id="a_videos" type="number" min="0" style="width:6.5rem"></div>
     <div><label>rate per video</label><input id="a_rate" type="number" step="any" style="width:7rem"></div>
     <div><label>hourly</label><input id="a_hourly" type="number" step="any" style="width:6rem"></div>
     <div><label>hours cap</label><input id="a_cap" type="number" min="0" style="width:6rem"></div>
     <div><label>commission</label><input id="a_comm" size="8" placeholder="20%"></div>
     <div><label>status</label><select id="a_status">
       <option value="">(blank — counts)</option><option>Active</option>
       <option>Paused</option><option>Inactive</option></select></div>
     <button class="btn ghost" id="a_check">Check handle</button>
     <button class="btn" id="a_add">Add creator</button>
   </div>
   <div id="a_msg"></div>`;

  document.querySelectorAll('button.hcheck').forEach(b=>b.onclick=()=>checkRow(b.dataset.k));
  document.querySelectorAll('button.hsave').forEach(b=>b.onclick=()=>saveRow(b.dataset.k));
  $('a_check').onclick=()=>checkNew();
  $('a_add').onclick=()=>addNew();
}

function rosterRow(c){
  const k=esc(c.key);
  return `<tr data-k="${k}">
    <td><input class="r_name" data-k="${k}" value="${esc(c.name)}" size="18">
      ${c.source==='custom'?'<br><span class="pill flat">added here</span>':''}
      ${c.attribution==='owned'?'<br><span class="pill mid">brand acct</span>':''}</td>
    <td><input class="r_handle" data-k="${k}" value="${esc(c.handle||'')}" size="18"
          placeholder="no handle">
      <div class="hres tiny" data-k="${k}">${handleVerdictHtml(c)}</div></td>
    <td class="tiny">${c.type==='live'?'Lives':'Video'}</td>
    <td class="n">${c.type==='live'
      ? `<input class="r_cap" data-k="${k}" type="number" min="0" value="${c.hours_cap??''}" style="width:5rem">`
      : `<input class="r_videos" data-k="${k}" type="number" min="0" value="${c.committed_videos??''}" style="width:5rem">`}</td>
    <td class="n">${c.type==='live'
      ? `<input class="r_hourly" data-k="${k}" type="number" step="any" value="${c.hourly??''}" style="width:5.5rem">`
      : `<input class="r_rate" data-k="${k}" type="number" step="any" value="${c.rate??''}" style="width:5.5rem">`}</td>
    <td><input class="r_comm" data-k="${k}" value="${esc(c.commission||'')}" size="8"></td>
    <td class="tiny">${statusPill(c)}</td>
    <td style="white-space:nowrap">
      <button class="btn ghost hcheck" data-k="${k}">Check</button>
      <button class="btn hsave" data-k="${k}">Update</button></td></tr>`;
}

function handleVerdictHtml(c){
  if(!c.handle) return '<span class="pill no">no handle</span>';
  const v=c.handle_check;
  if(!v) return '<span class="pill flat">not checked</span>';
  return verdictHtml(v);
}
function verdictHtml(v){
  if(v.status==='ok') return `<span class="pill ok">found</span>
    ${v.videos?`${v.videos} videos · ${m(v.video_gmv)}`:''}
    ${v.live_sessions?` · ${v.live_sessions} lives · ${m(v.live_gmv)}`:''}`;
  if(v.status==='no_data') return '<span class="pill mid">exists, no data in window</span>';
  if(v.status==='empty') return '<span class="pill no">no handle</span>';
  let h=`<span class="pill no">no data — check spelling</span>`;
  if(v.suggestions?.length){
    h+=`<div style="margin-top:.2rem">did you mean: `+v.suggestions.map(s=>
      `<button class="btn ghost sug" data-h="${esc(s.handle)}" style="padding:.1rem .4rem;font-size:.72rem">
        @${esc(s.handle)} <span class="tiny">(${s.videos}v${s.live_sessions?'/'+s.live_sessions+'L':''})</span></button>`
      ).join(' ')+`</div>`;
  }
  return h;
}

async function checkRow(k){
  const inp=document.querySelector(`input.r_handle[data-k="${CSS.escape(k)}"]`);
  const box=document.querySelector(`.hres[data-k="${CSS.escape(k)}"]`);
  box.innerHTML='<span class="spin"></span> checking…';
  try{
    const v=await api('/api/validate-handle?handle='+encodeURIComponent(inp.value.trim()));
    box.innerHTML=verdictHtml(v);
    box.querySelectorAll('button.sug').forEach(b=>b.onclick=()=>{
      inp.value=b.dataset.h; checkRow(k);});
  }catch(e){ box.innerHTML=`<span class="pill no">check failed</span> ${esc(e.message)}`; }
}
async function saveRow(k){
  const get=(cls)=>{const el=document.querySelector(`input.${cls}[data-k="${CSS.escape(k)}"]`);return el?el.value:undefined;};
  const fields={name:get('r_name'),handle:get('r_handle'),commission:get('r_comm')};
  const v=get('r_videos'); if(v!==undefined) fields.videos=Number(v||0);
  const r=get('r_rate');   if(r!==undefined) fields.rate=Number(r||0);
  const ho=get('r_hourly');if(ho!==undefined) fields.hourly=ho===''?null:Number(ho);
  const cp=get('r_cap');   if(cp!==undefined) fields.hours_cap=cp===''?null:Number(cp);
  const box=document.querySelector(`.hres[data-k="${CSS.escape(k)}"]`);
  box.innerHTML='<span class="spin"></span> saving…';
  try{
    await post('/api/store/roster-override',{key:k,fields});
    route(false);
  }catch(e){ box.innerHTML=`<span class="pill no">save failed</span> ${esc(e.message)}`; }
}
async function checkNew(){
  const h=$('a_handle').value.trim();
  $('a_msg').innerHTML='<span class="spin"></span> checking…';
  try{
    const v=await api('/api/validate-handle?handle='+encodeURIComponent(h));
    $('a_msg').innerHTML='<div class="note">'+verdictHtml(v)+'</div>';
    $('a_msg').querySelectorAll('button.sug').forEach(b=>b.onclick=()=>{
      $('a_handle').value=b.dataset.h; checkNew();});
  }catch(e){ $('a_msg').innerHTML=`<div class="note bad">${esc(e.message)}</div>`; }
}
async function addNew(){
  const body={
    name:$('a_name').value, handle:$('a_handle').value, type:$('a_type').value,
    videos:$('a_videos').value, rate:$('a_rate').value,
    hourly:$('a_hourly').value, hours_cap:$('a_cap').value,
    commission:$('a_comm').value, status:$('a_status').value,
  };
  $('a_msg').innerHTML='<span class="spin"></span> adding…';
  try{
    await post('/api/store/roster-add',body);
    location.hash='#/creators/roster'; route(true);
  }catch(e){ $('a_msg').innerHTML=`<div class="note bad">${esc(e.message)}</div>`; }
}
</script>
<script>
/* ======================= P&L ======================= */
async function renderPnl(force){
  loading('Building the P&L…');
  const d=await api('/api/pnl'+(force?'?force=1':'')); D.pnl=d; setFresh(d.meta);
  const pr=d.prorata;
  const byGroup={};
  d.rows.forEach(r=>{(byGroup[r.group]=byGroup[r.group]||[]).push(r)});
  $('view').innerHTML=`
   <h2>P&amp;L — ${esc(d.month)}</h2>
   <p class="sub">Month to date, through <b>${esc(pr.through)}</b>. ${esc(pr.explain)}.</p>
   <div class="note bad"><b>Read this before using the net.</b> ${esc(d.net_caveat)}</div>
   <div class="cards">
     <div class="card"><span class="rail mid"></span><h4>${esc(d.net_label||'Net')}</h4>
       <div class="v">${m(d.net)}</div>
       <div class="g">margin ${pct(d.margin)} · <b>excludes ad spend</b></div></div>
     <div class="card"><h4>GMV</h4><div class="v">${m0(d.rows.find(r=>r.id==='gmv')?.value)}</div></div>
     <div class="card"><h4>Days of data</h4><div class="v">${pr.days}
       <span class="tiny">/ ${pr.days_in_month}</span></div>
       <div class="g">${pct(pr.fraction)} of the month</div></div>
     <div class="card"><h4>Est. fee rate</h4>
       <div class="v">${d.fee_rate==null?'—':pct(d.fee_rate)}</div>
       <div class="g">${d.settlement_count?`from ${d.settlement_count} settled statements`:'no settled data yet'}</div></div>
     <div class="card"><h4>Settled net</h4>
       <div class="v">${m0(d.rows.find(r=>r.id==='settled_net')?.value)}</div>
       <div class="g">finance basis, ~6d behind</div></div>
   </div>
   <div class="note warn"><b>Bases on this page.</b> ${esc(d.basis_warning)}</div>

   ${d.groups.filter(g=>byGroup[g]).map(g=>`
     <h3>${esc(g)}</h3>
     <div class="scroll"><table><thead><tr><th>Line</th><th class="n">Value</th>
       <th>Basis</th><th>Notes</th><th></th></tr></thead><tbody>
       ${byGroup[g].map(r=>`<tr>
         <td><b>${esc(r.label)}</b>${r.overridden?' <span class="pill mid">overridden</span>':''}</td>
         <td class="n ${r.overridden?'ovr':''}">${r.kind==='count'?n0(r.value):m(r.value)}
           ${r.overridden?`<br><span class="tiny">was ${r.kind==='count'?n0(r.original_value):m(r.original_value)}</span>`:''}</td>
         <td class="tiny">${esc(r.basis)}</td>
         <td class="tiny">${esc(r.note||'')}${r.override_note?`<br><i>${esc(r.override_note)}</i>`:''}</td>
         <td style="white-space:nowrap">${r.editable?`
           <button class="btn ghost ed" data-id="${esc(r.id)}" data-v="${r.value}">Edit</button>
           ${r.overridden?`<button class="btn ghost clr" data-id="${esc(r.id)}">Reset</button>`:''}`:''}</td>
       </tr>`).join('')}
     </tbody></table></div>`).join('')}

   <h3>Locked — needs authorisation</h3>
   <div class="scroll"><table><thead><tr><th>Line</th><th>Why it is empty</th>
     <th>What it would unlock</th></tr></thead><tbody>
     ${d.locked.map(l=>`<tr class="locked"><td><b>${esc(l.label)}</b>
       <br><span class="pill no">locked</span></td>
       <td class="tiny">${esc(l.reason)}</td><td class="tiny">${esc(l.unlocks)}</td></tr>`).join('')}
   </tbody></table></div>

   <h3>External costs (manual)</h3>
   <p class="sub">Anything not coming from TikTok Shop. Pro-rata applies ${esc(pr.explain)}.</p>
   ${d.external_items.length?`<div class="scroll"><table><thead><tr><th>Description</th>
     <th>Category</th><th class="n">Full</th><th>Pro-rata</th><th class="n">Applied</th>
     <th></th></tr></thead><tbody>
     ${d.external_items.map(x=>`<tr><td><b>${esc(x.description)}</b>
       ${x.date?`<br><span class="tiny">${esc(x.date)}</span>`:''}</td>
       <td class="tiny">${esc(x.category)}</td><td class="n">${m(x.full_amount)}</td>
       <td class="tiny">${x.pro_rata?'<span class="pill ok">on</span>':'<span class="pill flat">off</span>'}
         <br>${esc(x.explain)}</td>
       <td class="n">${m(x.applied)}</td>
       <td><button class="btn ghost delc" data-id="${esc(x.id)}">Delete</button></td></tr>`).join('')}
     </tbody></table></div>`:'<p class="empty">No manual costs for this month yet.</p>'}
   <div class="bar">
     <div><label>description</label><input id="c_desc" size="22" placeholder="Team spend — Nov"></div>
     <div><label>category</label><input id="c_cat" size="12" placeholder="Team"></div>
     <div><label>amount</label><input id="c_amt" type="number" step="any" style="width:8rem"></div>
     <div><label>date (optional)</label><input id="c_date" type="date"></div>
     <div><label>pro-rata</label><select id="c_pr"><option value="1">on</option>
       <option value="0">off — charge in full</option></select></div>
     <button class="btn" id="c_add">Add cost</button>
     <span class="msg" id="c_msg"></span>
   </div>`;

  document.querySelectorAll('button.ed').forEach(b=>b.onclick=async()=>{
    const v=prompt('Override "'+b.closest('tr').querySelector('b').textContent+'" with:',b.dataset.v);
    if(v===null) return;
    const note=prompt('Why? (optional)','')||'';
    await post('/api/store/pnl-cell',{month:d.month,row_id:b.dataset.id,value:Number(v),note});
    route(false);
  });
  document.querySelectorAll('button.clr').forEach(b=>b.onclick=async()=>{
    await post('/api/store/pnl-cell-clear',{month:d.month,row_id:b.dataset.id}); route(false);
  });
  document.querySelectorAll('button.delc').forEach(b=>b.onclick=async()=>{
    await post('/api/store/cost-delete',{id:b.dataset.id}); route(false);
  });
  $('c_add').onclick=async()=>{
    $('c_msg').textContent='saving…';
    try{
      await post('/api/store/cost',{month:d.month,description:$('c_desc').value,
        category:$('c_cat').value,amount:$('c_amt').value,date:$('c_date').value,
        pro_rata:$('c_pr').value==='1'});
      route(false);
    }catch(e){ $('c_msg').innerHTML=`<span class="pill no">${esc(e.message)}</span>`; }
  };
}

/* ---------- boot ---------- */
if(!ADMIN||ADMIN==='__ADMIN__') $('tokenbar').style.display='flex';
if(!location.hash) location.hash='#/home';
route(false);
</script>
"""
