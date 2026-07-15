"""Async, resumable and auditable RIS screening for Lattice.

The 9Router endpoint is treated as an OpenAI-compatible chat-completions API.
When no router key is present, deterministic local screening keeps dry-runs and
development reproducible without silently pretending to be a model decision.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

try:
    import httpx
except ImportError:  # Optional for deterministic local/dry-run mode.
    httpx = None  # type: ignore[assignment]

DecisionName = Literal["include", "exclude", "review"]


@dataclass(slots=True)
class Record:
    record_id: str
    fields: dict[str, list[str]]
    raw: str

    @property
    def title(self) -> str:
        return first(self.fields, "TI", "T1", default="Untitled record")

    @property
    def abstract(self) -> str:
        return first(self.fields, "AB", "N2")


@dataclass(slots=True)
class ScreeningDecision:
    record_id: str
    title: str
    decision: DecisionName
    confidence: float
    rationale: str
    criteria_met: list[str]
    criteria_failed: list[str]
    model_votes: list[dict[str, Any]]
    router_trace_ids: list[str]
    criteria_hash: str
    source: str
    latency_ms: int
    timestamp: float


def first(fields: dict[str, list[str]], *tags: str, default: str = "") -> str:
    for tag in tags:
        values = fields.get(tag)
        if values:
            return values[0]
    return default


def parse_ris(text: str) -> list[Record]:
    records: list[Record] = []
    current: dict[str, list[str]] = {}
    raw: list[str] = []
    last_tag: str | None = None
    for line in text.replace("\ufeff", "").splitlines():
        match = re.match(r"^([A-Z0-9]{2})  - ?(.*)$", line)
        if match:
            tag, value = match.groups()
            if tag == "TY" and current:
                records.append(make_record(current, raw))
                current, raw = {}, []
            current.setdefault(tag, []).append(value.strip())
            last_tag = tag
            raw.append(line)
            if tag == "ER":
                records.append(make_record(current, raw))
                current, raw, last_tag = {}, [], None
        elif line.startswith(("  ", "\t")) and last_tag and current.get(last_tag):
            current[last_tag][-1] += " " + line.strip()
            raw.append(line)
        elif line.strip():
            raw.append(line)
    if current:
        records.append(make_record(current, raw))
    return records


def make_record(fields: dict[str, list[str]], raw: list[str]) -> Record:
    fingerprint = "|".join([first(fields, "DO"), first(fields, "TI", "T1"), first(fields, "PY", "Y1")]).lower()
    record_id = hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
    normalized_raw = "\n".join(raw)
    if "ER  -" not in normalized_raw:
        normalized_raw += "\nER  -"
    return Record(record_id=record_id, fields=fields, raw=normalized_raw)


def validate_records(records: Iterable[Record]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        if record.title == "Untitled record":
            issues.append({"record": str(index), "severity": "error", "message": "Missing TI/T1 title"})
        if "TY" not in record.fields:
            issues.append({"record": str(index), "severity": "warning", "message": "Missing TY record type"})
        if record.record_id in seen:
            issues.append({"record": str(index), "severity": "warning", "message": "Probable duplicate"})
        seen.add(record.record_id)
    return issues


def local_decision(record: Record, criteria_hash: str) -> ScreeningDecision:
    text = f"{record.title} {record.abstract}".lower()
    topic_terms = ("explain", "interpret", "transparent", "trust", "uncertainty", "decision support")
    method_terms = ("trial", "study", "experiment", "survey", "evaluation", "mixed-method", "longitudinal")
    topic = any(term in text for term in topic_terms)
    empirical = any(term in text for term in method_terms)
    if topic and empirical:
        decision, confidence = "include", 0.84
        rationale = "Deterministic development rule found both topic and empirical-method indicators."
    elif topic:
        decision, confidence = "review", 0.62
        rationale = "Topic indicators are present, but the abstract lacks clear eligible-method evidence."
    else:
        decision, confidence = "exclude", 0.82
        rationale = "No configured topic indicator is present in the title or abstract."
    return ScreeningDecision(record.record_id, record.title, decision, confidence, rationale,
                             ["topic fit"] if topic else [], ["empirical method"] if not empirical else [],
                             [], [], criteria_hash, "local-development-rule", 0, time.time())


class RouterClient:
    def __init__(self, base_url: str, api_key: str, models: list[str], timeout: float = 60):
        if httpx is None:
            raise RuntimeError("httpx is required for 9Router mode; install requirements.txt")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.models = models
        self.client = httpx.AsyncClient(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})

    async def close(self) -> None:
        await self.client.aclose()

    async def vote(self, model: str, record: Record, criteria: str, examples: str = "") -> dict[str, Any]:
        prompt = f"""You are screening titles and abstracts for a systematic review.
Apply only the written criteria. Missing information must produce `review`, not an assumption.
Return JSON only with: decision (include|exclude|review), confidence (0..1), rationale,
criteria_met (string array), criteria_failed (string array).

CRITERIA\n{criteria}\n{examples}\n
TITLE\n{record.title}\n
ABSTRACT\n{record.abstract or '[missing]'}"""
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                   "response_format": {"type": "json_object"}}
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = await self.client.post(f"{self.base_url}/chat/completions", json=payload)
                response.raise_for_status()
                body = response.json()
                result = json.loads(body["choices"][0]["message"]["content"])
                result["model"] = model
                result["trace_id"] = response.headers.get("x-request-id") or body.get("id") or str(uuid.uuid4())
                return result
            except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                await asyncio.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"9Router model {model} failed after retries: {last_error}")


def ensemble(votes: list[dict[str, Any]], record: Record, criteria_hash: str, latency_ms: int) -> ScreeningDecision:
    weight: dict[str, float] = {"include": 0, "exclude": 0, "review": 0}
    for vote in votes:
        name = vote.get("decision", "review")
        if name not in weight:
            name = "review"
        weight[name] += max(0.01, min(float(vote.get("confidence", 0.5)), 1.0))
    ordered = sorted(weight.items(), key=lambda item: item[1], reverse=True)
    total = sum(weight.values()) or 1
    agreement = ordered[0][1] / total
    decision: DecisionName = ordered[0][0]  # type: ignore[assignment]
    if agreement < 0.58:
        decision = "review"
    confidence = min(agreement, sum(float(v.get("confidence", 0.5)) for v in votes) / len(votes))
    lead = max(votes, key=lambda vote: float(vote.get("confidence", 0)))
    return ScreeningDecision(record.record_id, record.title, decision, round(confidence, 4),
                             str(lead.get("rationale", "Ensemble decision")),
                             list(lead.get("criteria_met", [])), list(lead.get("criteria_failed", [])), votes,
                             [str(v.get("trace_id", "")) for v in votes], criteria_hash, "9router-ensemble",
                             latency_ms, time.time())


async def screen_records(records: list[Record], criteria: str, output_dir: Path, *, concurrency: int = 20,
                         low_confidence: float = 0.78, feedback_path: Path | None = None) -> list[ScreeningDecision]:
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "screening.jsonl"
    existing: dict[str, ScreeningDecision] = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
                data = json.loads(line)
                existing[data["record_id"]] = ScreeningDecision(**data)
    criteria_hash = hashlib.sha256(criteria.encode()).hexdigest()
    examples = feedback_path.read_text(encoding="utf-8") if feedback_path and feedback_path.exists() else ""
    base_url, key = os.getenv("NINEROUTER_BASE_URL", ""), os.getenv("NINEROUTER_API_KEY", "")
    models = [m.strip() for m in os.getenv("NINEROUTER_MODELS", "gpt-5.4,gpt-oss-120b").split(",") if m.strip()]
    router = RouterClient(base_url, key, models) if base_url and key else None
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()

    async def one(record: Record) -> ScreeningDecision:
        saved = existing.get(record.record_id)
        if saved and saved.criteria_hash == criteria_hash:
            return saved
        async with semaphore:
            if not router:
                result = local_decision(record, criteria_hash)
            else:
                start = time.perf_counter()
                votes = await asyncio.gather(*(router.vote(model, record, criteria, examples) for model in models), return_exceptions=True)
                valid = [vote for vote in votes if isinstance(vote, dict)]
                if not valid:
                    raise RuntimeError(f"No ensemble model returned a valid vote for {record.record_id}")
                result = ensemble(valid, record, criteria_hash, int((time.perf_counter() - start) * 1000))
            if result.confidence < low_confidence:
                result.decision = "review"
            async with lock:
                with checkpoint.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            return result

    try:
        results = await asyncio.gather(*(one(record) for record in records))
    finally:
        if router:
            await router.close()
    return results


def write_ris(records: list[Record], decisions: list[ScreeningDecision], output_dir: Path) -> None:
    by_id = {decision.record_id: decision for decision in decisions}
    for name in ("include", "exclude"):
        selected = [record.raw for record in records if by_id[record.record_id].decision == name]
        (output_dir / f"{name}d.ris").write_text("\n\n".join(selected) + ("\n" if selected else ""), encoding="utf-8")
    review = [asdict(decision) for decision in decisions if decision.decision == "review"]
    (output_dir / "needs_review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"criteria_hash": decisions[0].criteria_hash if decisions else "", "records": len(records),
                "included": sum(d.decision == "include" for d in decisions),
                "excluded": sum(d.decision == "exclude" for d in decisions),
                "needs_review": len(review), "generated_at": time.time()}
    manifest["manifest_hash"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    input_path, output_dir = Path(args.input), Path(args.output)
    records = parse_ris(input_path.read_text(encoding="utf-8-sig", errors="replace"))
    issues = validate_records(records)
    print(json.dumps({"records": len(records), "issues": issues}, indent=2))
    if args.dry_run:
        return 1 if any(issue["severity"] == "error" for issue in issues) else 0
    if not records:
        raise SystemExit("No RIS records found")
    criteria = Path(args.criteria).read_text(encoding="utf-8")
    decisions = await screen_records(records, criteria, output_dir, concurrency=args.concurrency,
                                     low_confidence=args.low_confidence,
                                     feedback_path=Path(args.feedback) if args.feedback else None)
    write_ris(records, decisions, output_dir)
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Screen RIS records with an explainable 9Router ensemble")
    cli.add_argument("input", help="Input RIS file")
    cli.add_argument("--criteria", default="criteria.example.md")
    cli.add_argument("--output", default="outputs/slr_run")
    cli.add_argument("--concurrency", type=int, default=20)
    cli.add_argument("--low-confidence", type=float, default=float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.78")))
    cli.add_argument("--feedback", help="JSONL examples from reviewer feedback for active learning")
    cli.add_argument("--dry-run", action="store_true", help="Validate RIS without calling models")
    return cli


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parser().parse_args())))
