# Lattice

Lattice is an explainable, collaborative Systematic Literature Review workspace. It combines a browser-based reviewer console, a Python/FastAPI automation pipeline, a reproducible audit format, and integration adapters for 9Router, Google Drive, Zotero, and VOSviewer.

## What is implemented

### Full-featured mode

- RIS parsing, validation-only dry runs, duplicate warnings, and deterministic record IDs.
- Async bounded-concurrency screening with 9Router retries, ensemble voting, confidence thresholds, and resumable JSONL checkpoints.
- Explainable `include`, `exclude`, and `review` decisions with criteria evidence, model votes, trace IDs, latency, criteria hashes, and immutable reviewer-override events.
- `included.ris`, `excluded.ris`, `needs_review.json`, `manifest.json`, `hasil_screening.xlsx`, `dashboard.html`, `prisma_flow.png`, and `prisma_report.docx` exports.
- A responsive review queue with RIS upload, real-time progress, filtering, human overrides, PRISMA reporting, and reproducibility views.

### Frontier mode

- Multi-model routing through an OpenAI-compatible 9Router endpoint.
- Feedback examples injected into subsequent screening prompts for auditable active learning; the source criteria are never silently rewritten.
- Baseline TF-IDF topic signals, evidence-similarity network export, transparent methodology quality signals, VOSviewer-compatible GML, and LaTeX tables.
- Interactive topic clusters, research-frontier signals, topic evolution, and citation-network views in the web workspace.

### Collaboration and integrations

- Durable D1 schema for projects, papers, versioned decisions, comments, and audit events; R2 is declared for RIS inputs and generated artifacts.
- Workspace identity is designed to use the platform-authenticated user headers. Roles belong in project membership policy, not in client-side claims.
- Adapters for Zotero tagging, Google Drive artifact upload, and VOSviewer GML export.
- Integration surfaces for Slack/Teams notifications and future plugin adapters such as Mendeley and EndNote.

## Local web workspace

```bash
npm install
npm run dev
```

The UI works immediately with realistic review data. Uploading a `.ris` file validates and screens it locally in the browser so the review interactions can be evaluated without credentials.

## Python pipeline

Use Python 3.10 or newer.

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python -m backend.slr_screening records.ris --criteria criteria.example.md --dry-run
python -m backend.slr_screening records.ris --criteria criteria.example.md --output outputs/slr_run
python -m backend.export_excel outputs/slr_run/screening.jsonl
python -m backend.export_html outputs/slr_run/screening.jsonl
python -m backend.export_prisma outputs/slr_run/manifest.json
python -m backend.frontier_engine outputs/slr_run/included.ris
```

Without `NINEROUTER_API_KEY`, the screening command labels its decisions as `local-development-rule`. It never misrepresents those decisions as model output.

Run the API with:

```bash
uvicorn backend.api:app --reload --port 8000
```

API documentation is exposed at `/backend/docs`. Screening jobs publish progress through Server-Sent Events and preserve resumable checkpoints in their job directory.

## 9Router contract

Lattice expects an OpenAI-compatible `POST {NINEROUTER_BASE_URL}/chat/completions` endpoint. Configure models with a comma-separated `NINEROUTER_MODELS` value. Each model is called concurrently with deterministic temperature, structured JSON output, exponential retry, and trace capture. Ensemble disagreement or confidence below `LOW_CONFIDENCE_THRESHOLD` is routed to human review.

Router logs should retain only operational metadata and record IDs. Do not place full abstracts in external telemetry. The Lattice audit event stores router trace IDs so an authorized operator can reconcile a decision with the router dashboard.

## Deployment

The repository is ready for both the bundled Sites runtime and Vercel. For Vercel, connect the repository, add the keys from `.env.example`, and deploy. `vercel.json` routes `/backend/*` to the FastAPI function in `api/index.py`. For large reviews, move FastAPI workers to a long-running container or job service and keep Vercel as the web/control plane; serverless request limits are not appropriate for multi-hour batch jobs.

Google and Zotero credentials must be configured as hosted secrets. Never commit them. Slack and Teams notification delivery should also use hosted secret values and explicit team-admin consent.

## Reproducibility rules

1. Criteria text is immutable within a run and identified by SHA-256.
2. Resume accepts a cached decision only when its criteria hash matches.
3. Low-confidence and ensemble-disagreement cases become `review`.
4. Reviewer changes append a new decision that supersedes, but does not delete, the previous decision.
5. Each manifest records counts, generation time, and its own checksum.
6. AI quality scores are transparent signals for reviewer assessment, not replacements for validated risk-of-bias instruments.

## Important production boundaries

- Bibliographic RIS exports usually do not contain reference lists. Citation graphs are therefore evidence-similarity networks until Crossref/OpenAlex citation enrichment is connected.
- The provided active-learning loop uses reviewer examples in subsequent prompts. Any trainable open-source classifier should be versioned separately with frozen datasets and benchmark reports.
- Meta-analysis requires effect sizes, sampling errors, and compatible outcomes extracted from full texts. Lattice exposes the reporting surface, but it does not fabricate pooled estimates from abstracts.
