"""Frontier-mode topic, citation, quality, and LaTeX exports.

The baseline stays reproducible and dependency-light. Production deployments can
replace keyword vectors with router embeddings without changing the export shape.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .integrations import write_vosviewer_gml
from .slr_screening import Record, parse_ris

STOP = {"the", "and", "for", "with", "from", "that", "this", "using", "study", "analysis", "artificial", "intelligence"}


def tokens(record: Record) -> list[str]:
    return [word for word in re.findall(r"[a-z][a-z-]{3,}", f"{record.title} {record.abstract}".lower()) if word not in STOP]


def quality_score(record: Record) -> tuple[int, str, list[str]]:
    text = f"{record.title} {record.abstract}".lower()
    score, reasons = 35, []
    for term, points, reason in [("randomized", 22, "random allocation reported"), ("control", 12, "comparison group reported"),
                                 ("longitudinal", 12, "longitudinal design"), ("mixed-method", 10, "method triangulation"),
                                 ("sample", 7, "sample information reported"), ("confidence interval", 6, "uncertainty reported")]:
        if term in text:
            score += points
            reasons.append(reason)
    if any(term in text for term in ("protocol", "editorial", "conceptual")):
        score -= 20
        reasons.append("non-empirical design indicator")
    score = max(0, min(score, 100))
    return score, "high" if score >= 75 else "moderate" if score >= 50 else "low", reasons


def analyze(ris_path: Path, output_dir: Path) -> None:
    records = parse_ris(ris_path.read_text(encoding="utf-8-sig", errors="replace"))
    output_dir.mkdir(parents=True, exist_ok=True)
    document_frequency: Counter[str] = Counter()
    per_record: dict[str, Counter[str]] = {}
    for record in records:
        counts = Counter(tokens(record))
        per_record[record.record_id] = counts
        document_frequency.update(counts.keys())
    topics = []
    for record in records:
        scored = sorted(((term, count * math.log((len(records) + 1) / (document_frequency[term] + 1))) for term, count in per_record[record.record_id].items()), key=lambda x: x[1], reverse=True)
        topics.append({"record_id": record.record_id, "title": record.title, "keywords": [term for term, _ in scored[:6]]})
    (output_dir / "topic_map.json").write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes = [{"label": record.title[:80]} for record in records]
    edges = []
    for left in range(len(records)):
        left_terms = set(per_record[records[left].record_id])
        for right in range(left + 1, len(records)):
            overlap = len(left_terms & set(per_record[records[right].record_id]))
            if overlap >= 2:
                edges.append({"source": left, "target": right, "weight": overlap})
    write_vosviewer_gml(nodes, edges, output_dir / "citation_graph.gml")

    with (output_dir / "quality_scores.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "title", "score", "rating", "signals"])
        for record in records:
            score, rating, reasons = quality_score(record)
            writer.writerow([record.record_id, record.title, score, rating, "; ".join(reasons)])

    latex_rows = []
    for record in records:
        title = record.title.replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")
        author = record.fields.get("AU", ["Not reported"])[0].replace("&", "\\&")
        year = record.fields.get("PY", record.fields.get("Y1", ["--"]))[0][:4]
        _, rating, _ = quality_score(record)
        latex_rows.append(f"{author} & {year} & {title} & {rating.title()} \\\\")
    latex = """\\begin{table}[htbp]\n\\centering\n\\caption{Characteristics and automated methodological quality signals of included studies.}\n\\label{tab:included-studies}\n\\begin{tabular}{llll}\n\\toprule\nStudy & Year & Title & Quality \\\\\n+\\midrule\n""" + "\n".join(latex_rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    (output_dir / "included_studies.tex").write_text(latex, encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("ris")
    cli.add_argument("--output", default="outputs/slr_run/frontier")
    args = cli.parse_args()
    analyze(Path(args.ris), Path(args.output))
