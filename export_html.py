"""Generate a dependency-free, portable screening dashboard."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lattice screening dashboard</title><style>
body{font:14px system-ui;margin:0;background:#f7f7f5;color:#17212c}header{padding:28px 5vw;background:#202432;color:white}main{max-width:1200px;margin:auto;padding:25px 5vw}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric,.paper{background:#fff;border:1px solid #e5e6e8;border-radius:10px;padding:16px}.metric b{display:block;font-size:26px;margin-top:5px}.tools{display:flex;gap:8px;margin:20px 0}input,select{padding:10px;border:1px solid #ddd;border-radius:7px}.paper{margin:8px 0;display:grid;grid-template-columns:1fr auto;gap:15px}.paper h2{font-size:15px;margin:0}.paper p{color:#69727b;line-height:1.45}.badge{border-radius:20px;padding:6px 10px;font-weight:600;height:max-content}.include{background:#e5f5ee;color:#197958}.exclude{background:#fff0ed;color:#bd5447}.review{background:#fff3da;color:#976715}@media(max-width:650px){.metrics{grid-template-columns:1fr 1fr}.paper{grid-template-columns:1fr}}
</style></head><body><header><small>REPRODUCIBLE SLR SCREENING</small><h1>Lattice decision dashboard</h1><p>Search, filter, and inspect the evidence behind every decision.</p></header><main><section class="metrics" id="metrics"></section><div class="tools"><input id="search" placeholder="Search papers…"><select id="decision"><option value="">All decisions</option><option>include</option><option>exclude</option><option>review</option></select></div><section id="papers"></section></main><script>
const data=__DATA__;const root=document.getElementById('papers'),search=document.getElementById('search'),decision=document.getElementById('decision');function draw(){const q=search.value.toLowerCase(),d=decision.value;const rows=data.filter(x=>(!d||x.decision===d)&&(`${x.title} ${x.rationale}`.toLowerCase().includes(q)));root.innerHTML=rows.map(x=>`<article class="paper"><div><h2>${escapeHtml(x.title)}</h2><p>${escapeHtml(x.rationale)}</p><small>Confidence ${Math.round(x.confidence*100)}% · ${escapeHtml(x.source)} · trace ${escapeHtml((x.router_trace_ids||[]).join(', ')||'local')}</small></div><span class="badge ${x.decision}">${x.decision}</span></article>`).join('')||'<p>No matching records.</p>'}function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}document.getElementById('metrics').innerHTML=['all','include','exclude','review'].map(d=>`<article class="metric"><span>${d}</span><b>${d==='all'?data.length:data.filter(x=>x.decision===d).length}</b></article>`).join('');search.oninput=decision.onchange=draw;draw();
</script></body></html>"""


def export(input_path: Path, output_path: Path) -> None:
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    safe = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(TEMPLATE.replace("__DATA__", safe), encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("input")
    cli.add_argument("--output", default="outputs/slr_run/dashboard.html")
    args = cli.parse_args()
    export(Path(args.input), Path(args.output))
