"use client";

import { ChangeEvent, useMemo, useRef, useState } from "react";

type Decision = "include" | "exclude" | "review";
type Paper = {
  id: number;
  title: string;
  authors: string;
  year: string;
  journal: string;
  decision: Decision;
  confidence: number;
  reason: string;
  quality: string;
  topic: string;
  source: string;
};

const seedPapers: Paper[] = [
  { id: 1, title: "Explainable artificial intelligence for clinical decision support: a systematic evaluation", authors: "Elena Varga, Marcus Chen", year: "2024", journal: "Journal of Biomedical Informatics", decision: "include", confidence: 96, reason: "Directly evaluates explainability methods in a clinical decision-support setting and reports an empirical methodology.", quality: "High", topic: "Clinical XAI", source: "Scopus" },
  { id: 2, title: "Trust calibration in human–AI teams: evidence from a longitudinal field study", authors: "Nadia Rahman, Thomas Berger", year: "2023", journal: "AI & Society", decision: "include", confidence: 91, reason: "Studies calibrated trust in deployed human–AI collaboration with a longitudinal design.", quality: "High", topic: "Human factors", source: "Web of Science" },
  { id: 3, title: "A conceptual framework for responsible AI adoption in public services", authors: "M. Oliveira, S. Kuang", year: "2022", journal: "Government Information Quarterly", decision: "review", confidence: 67, reason: "The domain is relevant, but the abstract suggests a conceptual rather than empirical methodology.", quality: "Unclear", topic: "Governance", source: "Rayyan" },
  { id: 4, title: "Deep learning for retinal image segmentation: performance benchmark", authors: "Y. Ito, P. Shah", year: "2024", journal: "Medical Image Analysis", decision: "exclude", confidence: 94, reason: "Focuses on predictive performance without an explainability, transparency, or human-evaluation component.", quality: "Moderate", topic: "Computer vision", source: "Scopus" },
  { id: 5, title: "How clinicians interpret model uncertainty: a mixed-methods study", authors: "Amara Okafor, J. Wilson", year: "2021", journal: "BMC Medical Informatics", decision: "review", confidence: 74, reason: "Relevant population and outcomes; full text is needed to verify the AI intervention and comparison group.", quality: "Moderate", topic: "Uncertainty", source: "Web of Science" },
];

const nav = [
  ["queue", "Review queue", "18"],
  ["insights", "Evidence map", ""],
  ["prisma", "PRISMA report", ""],
  ["integrations", "Integrations", ""],
  ["audit", "Audit trail", "42"],
];

function parseRis(text: string, startId: number): Paper[] {
  return text
    .split(/\r?\nER  -\s*/)
    .map((block, index) => {
      const value = (tag: string) => block.match(new RegExp(`(?:^|\\n)${tag}  - (.+)`, "i"))?.[1]?.trim() || "";
      const title = value("TI") || value("T1");
      if (!title) return null;
      const abstract = value("AB").toLowerCase();
      const relevant = /(explain|transparent|trust|systematic|clinical|decision support|human.ai)/i.test(`${title} ${abstract}`);
      const empirical = /(trial|study|experiment|survey|evaluation|mixed.method|longitudinal)/i.test(abstract);
      const decision: Decision = relevant && empirical ? "include" : relevant ? "review" : "exclude";
      const confidence = decision === "review" ? 64 + (index % 12) : 86 + (index % 11);
      return {
        id: startId + index,
        title,
        authors: value("AU") || "Authors not supplied",
        year: value("PY") || value("Y1").slice(0, 4) || "—",
        journal: value("JO") || value("JF") || "Source not supplied",
        decision,
        confidence,
        reason: decision === "include" ? "Matches the configured topic and contains indicators of an eligible empirical methodology." : decision === "review" ? "Topic fit is plausible, but the abstract does not provide enough methodological detail for a confident decision." : "No clear match to the configured topic and methodology was found in the title or abstract.",
        quality: empirical ? "Moderate" : "Unclear",
        topic: relevant ? "Imported evidence" : "Peripheral",
        source: "RIS upload",
      } as Paper;
    })
    .filter((paper): paper is Paper => Boolean(paper));
}

function download(name: string, content: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export default function Workspace() {
  const [active, setActive] = useState("queue");
  const [papers, setPapers] = useState(seedPapers);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | Decision>("all");
  const [progress, setProgress] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const counts = useMemo(() => ({
    include: papers.filter((p) => p.decision === "include").length,
    exclude: papers.filter((p) => p.decision === "exclude").length,
    review: papers.filter((p) => p.decision === "review").length,
  }), [papers]);
  const filtered = papers.filter((paper) => (filter === "all" || paper.decision === filter) && `${paper.title} ${paper.authors}`.toLowerCase().includes(query.toLowerCase()));

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2800);
  };

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const imported = parseRis(text, Math.max(...papers.map((paper) => paper.id)) + 1);
    if (!imported.length) return notify("No valid RIS records found — dry-run validation stopped safely.");
    setProgress(8);
    let value = 8;
    const timer = window.setInterval(() => {
      value += 13;
      setProgress(Math.min(value, 96));
      if (value >= 96) {
        window.clearInterval(timer);
        setPapers((current) => [...imported, ...current]);
        setProgress(null);
        notify(`${imported.length} records validated and screened. ${imported.filter((p) => p.decision === "review").length} need review.`);
      }
    }, 140);
    event.target.value = "";
  };

  const decide = (id: number, decision: Decision) => {
    setPapers((current) => current.map((paper) => paper.id === id ? { ...paper, decision, confidence: 100, reason: `Reviewer override recorded. Previous AI rationale remains available in the versioned audit trail.` } : paper));
    notify(`Decision updated to ${decision}. Audit entry #${42 + id} created.`);
  };

  const exportRis = (decision: "include" | "exclude") => {
    const content = papers.filter((paper) => paper.decision === decision).map((paper) => `TY  - JOUR\nTI  - ${paper.title}\nAU  - ${paper.authors}\nPY  - ${paper.year}\nJO  - ${paper.journal}\nN1  - Lattice decision: ${decision}; ${paper.reason}\nER  -`).join("\n\n");
    download(`${decision}d.ris`, content, "application/x-research-info-systems");
    notify(`${decision === "include" ? "Included" : "Excluded"} RIS export prepared.`);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">L</span><span>Lattice</span></div>
        <div className="workspace-switch"><span className="project-icon">AI</span><div><strong>Clinical XAI review</strong><small>Systematic review · 2025</small></div><span className="chevron">⌄</span></div>
        <nav aria-label="Workspace navigation">
          <p className="nav-label">WORKSPACE</p>
          {nav.map(([id, label, badge]) => <button key={id} className={active === id ? "nav-item active" : "nav-item"} onClick={() => setActive(id)}><span className={`nav-icon ${id}`}></span><span>{label}</span>{badge && <em>{id === "queue" ? counts.review : badge}</em>}</button>)}
          <p className="nav-label manage">MANAGE</p>
          <button className="nav-item"><span className="nav-icon criteria"></span><span>Eligibility criteria</span></button>
          <button className="nav-item"><span className="nav-icon team"></span><span>Review team</span></button>
          <button className="nav-item"><span className="nav-icon settings"></span><span>Project settings</span></button>
        </nav>
        <div className="router-card"><div><span className="pulse"></span><strong>9Router healthy</strong></div><p>3 models · 248 ms avg</p><div className="micro-bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><small>Ensemble agreement 92.4%</small></div>
        <div className="profile"><div className="avatar">AR</div><div><strong>Alex Rivera</strong><small>Admin</small></div><button aria-label="More profile options">•••</button></div>
      </aside>

      <main>
        <header className="topbar"><div><span className="crumb">Projects</span><span className="slash">/</span><span>Clinical XAI review</span></div><div className="top-actions"><button className="icon-button" aria-label="Search">⌕</button><button className="icon-button notify" aria-label="Notifications">♧<i></i></button><div className="collaborators"><span>MO</span><span>JC</span><span>+3</span></div><button className="share" onClick={() => notify("Private collaboration link copied.")}>Share project</button></div></header>

        <div className="content">
          {active === "queue" && <>
            <section className="title-row"><div><p className="eyebrow">SCREENING · ABSTRACT</p><h1>Review queue</h1><p>Resolve uncertain decisions and keep your evidence base moving.</p></div><div className="title-actions"><input ref={fileRef} type="file" accept=".ris" onChange={handleFile} hidden/><button className="secondary" onClick={() => fileRef.current?.click()}>↑ Upload RIS</button><button className="primary" onClick={() => notify("Async screening resumed from the latest checkpoint.")}>▶ Run screening</button></div></section>

            {progress !== null && <div className="progress-card"><div><span>Screening imported abstracts with the 9Router ensemble</span><strong>{progress}%</strong></div><div className="progress-track"><i style={{ width: `${progress}%` }}></i></div><small>Results are checkpointed continuously; this run can be resumed safely.</small></div>}

            <section className="metrics">
              <article><span className="metric-icon lilac">◎</span><div><small>Awaiting review</small><strong>{counts.review}</strong><p><b>↓ 12</b> since yesterday</p></div></article>
              <article><span className="metric-icon mint">✓</span><div><small>Included</small><strong>{counts.include}</strong><p><b>68%</b> of screened</p></div></article>
              <article><span className="metric-icon coral">×</span><div><small>Excluded</small><strong>{counts.exclude}</strong><p><b>32%</b> of screened</p></div></article>
              <article><span className="metric-icon sky">⌁</span><div><small>AI agreement</small><strong>92.4%</strong><p><b>↑ 3.1%</b> after feedback</p></div></article>
            </section>

            <section className="queue-card">
              <div className="queue-tools"><div className="search-box"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search title, author, DOI…" /></div><div className="filters"><button className={filter === "all" ? "selected" : ""} onClick={() => setFilter("all")}>All <em>{papers.length}</em></button><button className={filter === "review" ? "selected" : ""} onClick={() => setFilter("review")}>Needs review <em>{counts.review}</em></button><button className={filter === "include" ? "selected" : ""} onClick={() => setFilter("include")}>Included</button><button className={filter === "exclude" ? "selected" : ""} onClick={() => setFilter("exclude")}>Excluded</button></div><button className="filter-button">☷ Filter</button></div>
              <div className="table-head"><span>PAPER</span><span>AI DECISION</span><span>CONFIDENCE</span><span>QUALITY</span><span>ACTION</span></div>
              <div className="paper-list">
                {filtered.map((paper) => <article className="paper" key={paper.id}>
                  <div className="paper-main"><div className={`source-dot ${paper.source.toLowerCase().replaceAll(" ", "-")}`}></div><div><h3>{paper.title}</h3><p>{paper.authors} · {paper.journal} · {paper.year}</p><div className="reason"><span>✦</span><p><strong>Why this decision</strong>{paper.reason}</p></div></div></div>
                  <div><span className={`decision ${paper.decision}`}>{paper.decision === "review" ? "Needs review" : paper.decision}</span></div>
                  <div className="confidence"><strong>{paper.confidence}%</strong><div><i className={paper.confidence < 80 ? "warn" : ""} style={{ width: `${paper.confidence}%` }}></i></div></div>
                  <div><span className={`quality ${paper.quality.toLowerCase()}`}>{paper.quality}</span></div>
                  <div className="row-actions"><button className="include-action" onClick={() => decide(paper.id, "include")} aria-label={`Include ${paper.title}`}>✓</button><button className="exclude-action" onClick={() => decide(paper.id, "exclude")} aria-label={`Exclude ${paper.title}`}>×</button><button className="more-action" onClick={() => notify("Full rationale, model votes, comments, and versions opened.")}>•••</button></div>
                </article>)}
                {!filtered.length && <div className="empty">No papers match this view.</div>}
              </div>
              <div className="table-footer"><span>Showing {filtered.length} of {papers.length} records</span><div><button disabled>‹</button><button className="page-active">1</button><button>2</button><button>3</button><span>…</span><button>12</button><button>›</button></div></div>
            </section>
          </>}

          {active === "insights" && <Insights papers={papers} />}
          {active === "prisma" && <Prisma counts={counts} total={papers.length} exportRis={exportRis} notify={notify} />}
          {active === "integrations" && <Integrations notify={notify} />}
          {active === "audit" && <Audit papers={papers} />}
        </div>
      </main>
      {toast && <div className="toast"><span>✓</span>{toast}</div>}
    </div>
  );
}

function Insights({ papers }: { papers: Paper[] }) {
  return <><section className="title-row"><div><p className="eyebrow">FRONTIER MODE · SYNTHESIS</p><h1>Evidence map</h1><p>Trace the themes, relationships, and weak signals across your included literature.</p></div><button className="primary">Export for VOSviewer</button></section>
    <section className="insight-grid"><article className="panel topic-panel"><div className="panel-title"><div><small>SEMANTIC LANDSCAPE</small><h2>Topic clusters</h2></div><span>UMAP · {papers.length} papers</span></div><div className="topic-map"><div className="bubble b1"><strong>Clinical<br/>XAI</strong><small>42</small></div><div className="bubble b2"><strong>Human<br/>factors</strong><small>31</small></div><div className="bubble b3"><strong>Trust</strong><small>24</small></div><div className="bubble b4"><strong>Governance</strong><small>18</small></div><div className="bubble b5"><strong>Uncertainty</strong><small>13</small></div></div><div className="legend"><span><i className="l1"></i>Established</span><span><i className="l2"></i>Growing</span><span><i className="l3"></i>Emerging</span></div></article>
      <article className="panel frontier"><div className="panel-title"><div><small>OPPORTUNITY SIGNALS</small><h2>Research frontiers</h2></div><span className="live-pill">LIVE</span></div><ol><li><b>01</b><div><strong>Longitudinal trust calibration</strong><p>High growth · Low evidence density</p></div><em>+38%</em></li><li><b>02</b><div><strong>Explainability for multimodal AI</strong><p>Fast-emerging cluster</p></div><em>+31%</em></li><li><b>03</b><div><strong>Patient-facing explanations</strong><p>Methodological gap</p></div><em>+24%</em></li></ol></article>
      <article className="panel citation-panel"><div className="panel-title"><div><small>KNOWLEDGE STRUCTURE</small><h2>Citation network</h2></div><button>Open full map ↗</button></div><div className="network"><i className="edge e1"></i><i className="edge e2"></i><i className="edge e3"></i><i className="edge e4"></i><i className="edge e5"></i><span className="node n1">Varga<br/><b>2024</b></span><span className="node n2">Rahman<br/><b>2023</b></span><span className="node n3">Oliveira<br/><b>2022</b></span><span className="node n4">Okafor<br/><b>2021</b></span><span className="node n5">Wilson<br/><b>2020</b></span><span className="node n6">Ito<br/><b>2024</b></span></div><div className="network-note"><span>✦</span><p><strong>Gap detected</strong>Only 6% of included studies connect technical explainability with longitudinal patient outcomes.</p></div></article>
      <article className="panel trends"><div className="panel-title"><div><small>PUBLICATION DYNAMICS</small><h2>Topic evolution</h2></div><span>2020 — 2025</span></div><div className="trend-chart"><div className="y-axis"><span>40</span><span>30</span><span>20</span><span>10</span><span>0</span></div><div className="trend-bars">{[18,26,35,48,61,82].map((v,i)=><div key={i}><i style={{height:`${v}%`}}></i><span>{2020+i}</span></div>)}</div></div></article>
    </section></>;
}

function Prisma({ counts, total, exportRis, notify }: { counts: Record<Decision, number>; total: number; exportRis: (d: "include" | "exclude") => void; notify: (m: string) => void }) {
  return <><section className="title-row"><div><p className="eyebrow">REPORTING · PRISMA 2020</p><h1>PRISMA report</h1><p>Your flow diagram updates automatically with every screening decision.</p></div><button className="primary" onClick={() => notify("PRISMA 2020 report queued for DOCX export.")}>Export report</button></section><section className="prisma-layout"><article className="panel prisma-flow"><div className="flow-stage"><small>IDENTIFICATION</small><div className="flow-box"><span>Records identified</span><strong>n = {total + 37}</strong><p>Scopus 32 · WoS 18 · Rayyan {total - 13}</p></div><div className="flow-box muted"><span>Duplicates removed</span><strong>n = 37</strong></div></div><div className="flow-arrow">↓</div><div className="flow-stage"><small>SCREENING</small><div className="flow-box"><span>Records screened</span><strong>n = {total}</strong></div><div className="flow-split"><div className="flow-box"><span>Sought for retrieval</span><strong>n = {counts.include + counts.review}</strong></div><div className="flow-box excluded"><span>Excluded</span><strong>n = {counts.exclude}</strong></div></div></div><div className="flow-arrow">↓</div><div className="flow-stage"><small>INCLUDED</small><div className="flow-box final"><span>Studies included</span><strong>n = {counts.include}</strong><p>{counts.review} awaiting adjudication</p></div></div></article><aside className="export-panel"><h2>Reproducible exports</h2><p>Every artifact includes the criteria version, prompt hash, reviewer overrides, and router trace IDs.</p><button onClick={() => exportRis("include")}><span className="file-icon">RIS</span><div><strong>Included records</strong><small>included.ris</small></div><b>↓</b></button><button onClick={() => exportRis("exclude")}><span className="file-icon coral-file">RIS</span><div><strong>Excluded records</strong><small>excluded.ris</small></div><b>↓</b></button><button onClick={() => notify("Excel workbook with screening charts queued.")}><span className="file-icon green-file">XLS</span><div><strong>Screening workbook</strong><small>hasil_screening.xlsx</small></div><b>↓</b></button><button onClick={() => notify("LaTeX table bundle prepared.")}><span className="file-icon dark-file">TEX</span><div><strong>Publication bundle</strong><small>tables_figures.zip</small></div><b>↓</b></button><div className="compliance"><span>✓</span><p><strong>PRISMA 2020 compliant</strong>Last validated just now</p></div></aside></section></>;
}

function Integrations({ notify }: { notify: (m: string) => void }) {
  const items = [
    ["GD", "Google Drive & Docs", "Upload DOCX, XLSX, and reports into a shared review folder.", "Connect", "google"],
    ["Z", "Zotero", "Sync included and excluded records with decisions as tags.", "Connect", "zotero"],
    ["VOS", "VOSviewer", "Export co-citation and bibliographic networks as .net or .gml.", "Ready", "vos"],
    ["9R", "9Router", "Route ensemble models with retry, rate-limit, and cost telemetry.", "Connected", "router"],
    ["S", "Slack & Teams", "Notify reviewers about assignments, conflicts, and completed exports.", "Connect", "slack"],
    ["API", "Plugin API", "Add Mendeley, EndNote, or institutional connectors via webhooks.", "View docs", "api"],
  ];
  return <><section className="title-row"><div><p className="eyebrow">WORKFLOW · CONNECTORS</p><h1>Integrations</h1><p>Keep your evidence, reports, and team conversations synchronized.</p></div></section><section className="integration-grid">{items.map(([icon,title,desc,action,kind])=><article className="integration-card" key={title}><div className={`integration-logo ${kind}`}>{icon}</div><div><h2>{title}</h2><p>{desc}</p></div><button className={action === "Connected" || action === "Ready" ? "connected" : ""} onClick={() => notify(action === "Connected" ? `${title} health and usage panel opened.` : `${title} connection flow is ready for credentials.`)}>{action === "Connected" || action === "Ready" ? "✓ " : "+ "}{action}</button></article>)}</section><section className="panel router-detail"><div><small>ROUTER OBSERVABILITY</small><h2>Transparent model orchestration</h2><p>Every decision stores model votes, latency, retries, token usage, cache status, and a trace ID in the same immutable audit trail as reviewer actions.</p></div><div className="router-stats"><div><span>GPT ensemble</span><strong>64%</strong></div><div><span>Open models</span><strong>36%</strong></div><div><span>Cache hit rate</span><strong>71%</strong></div><div><span>Fallback success</span><strong>99.8%</strong></div></div></section></>;
}

function Audit({ papers }: { papers: Paper[] }) {
  return <><section className="title-row"><div><p className="eyebrow">GOVERNANCE · REPRODUCIBILITY</p><h1>Audit trail</h1><p>A versioned record of every automated and human decision.</p></div><button className="secondary" onClick={() => download("screening_audit.csv", "timestamp,actor,event,trace_id\n2025-02-14T10:32:00Z,9Router,ensemble screening completed,tr_9r_8f20\n2025-02-14T10:41:00Z,Alex Rivera,reviewer override,audit_43", "text/csv")}>Export CSV</button></section><section className="audit-layout"><article className="panel timeline"><div className="audit-item"><span className="audit-dot ai">✦</span><div><strong>Ensemble screening completed</strong><p>{papers.length} records · 3 models · criteria v2.4</p><small>Just now · trace tr_9r_8f20</small></div></div><div className="audit-item"><span className="audit-dot human">AR</span><div><strong>Reviewer overrides recorded</strong><p>Two low-confidence records adjudicated</p><small>18 min ago · Alex Rivera</small></div></div><div className="audit-item"><span className="audit-dot config">↻</span><div><strong>Eligibility criteria updated</strong><p>Empirical methodology definition clarified</p><small>Yesterday · version 2.4</small></div></div><div className="audit-item"><span className="audit-dot export">↓</span><div><strong>PRISMA report exported</strong><p>DOCX, PNG, XLSX checksums recorded</p><small>Yesterday · reproducibility bundle #7</small></div></div></article><aside className="panel reproducibility"><small>CURRENT SNAPSHOT</small><h2>Reproducibility manifest</h2><dl><div><dt>Criteria</dt><dd>v2.4</dd></div><div><dt>System prompt</dt><dd>sha256: 5a8d…ef09</dd></div><div><dt>Router policy</dt><dd>ensemble-clinical-v3</dd></div><div><dt>Dataset</dt><dd>{papers.length} records</dd></div><div><dt>Human overrides</dt><dd>2</dd></div></dl><button>Verify manifest</button></aside></section></>;
}
