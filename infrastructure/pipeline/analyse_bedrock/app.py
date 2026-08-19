"""AnalyseWithBedrock — Claude reads the Forms structure + PL/SQL and produces a
structured migration analysis (components, API endpoints, data models, PL/SQL
mappings).

Input : state carrying forms_structure_key, plsql_corpus_key,
        dependency_graph_key, args_metadata_key.
Output: { "analysis_report_key": "pipeline/{run_id}/analysis_report.json" }

Uses extended thinking (budget_tokens) — temperature is intentionally omitted.
To respect the context window, the PL/SQL corpus is ranked by in-degree from the
dependency graph and only the most-referenced objects' full source is inlined.
"""
from common.aws_helpers import (
    s3_get_json, s3_put_json, converse_json, CLAUDE_MODEL_ID,
)

SYSTEM = (
    "You are a senior Oracle Forms modernization architect. You migrate legacy "
    "Oracle Forms + PL/SQL applications to Angular front ends backed by .NET Web "
    "APIs. You reason precisely about data blocks, triggers, master-detail "
    "relations and the PL/SQL business logic behind them. You always answer with "
    "STRICT JSON matching the requested schema and nothing else."
)

TOP_N_SOURCE = 20  # inline full source for the N most-referenced objects


def _rank_objects(corpus, edges):
    """Rank corpus objects by how often they are referenced (in-degree)."""
    indeg = {}
    for e in edges:
        ref = f"{e['ref_owner']}.{e['ref_name']}"
        indeg[ref] = indeg.get(ref, 0) + 1
    def score(obj):
        return indeg.get(f"{obj['owner']}.{obj['name']}", 0)
    return sorted(corpus, key=score, reverse=True)


def handler(event, _context):
    run_id = event["run_id"]
    forms = s3_get_json(event["forms"]["forms_structure_key"])
    corpus = s3_get_json(event["plsql"]["plsql_corpus_key"])
    edges = s3_get_json(event["plsql"]["dependency_graph_key"])
    args = s3_get_json(event["plsql"]["args_metadata_key"])

    ranked = _rank_objects(corpus, edges)[:TOP_N_SOURCE]

    user = f"""Analyse this legacy Oracle Forms screen and its backing PL/SQL, then
produce a migration plan to Angular + .NET.

## Forms structure (from frmf2xml)
{_compact(forms)}

## Most-referenced PL/SQL objects (full source)
{_compact(ranked)}

## Procedure/function signatures (ALL_ARGUMENTS)
{_compact(args)}

Return STRICT JSON with this schema:
{{
  "screen_name": string,
  "summary": string,
  "components": [ {{ "name": string, "type": "master-grid|detail-grid|form|lov",
                     "source_block": string, "fields": [string] }} ],
  "api_endpoints": [ {{ "method": "GET|POST|PUT|DELETE", "path": string,
                        "purpose": string, "backing_plsql": string }} ],
  "data_models": [ {{ "name": string, "table": string,
                      "fields": [ {{ "name": string, "type": string,
                                     "required": boolean }} ] }} ],
  "plsql_mappings": [ {{ "plsql_object": string, "maps_to": string,
                         "business_rules": [string] }} ]
}}"""

    report = converse_json(
        SYSTEM, user, model_id=CLAUDE_MODEL_ID,
        max_tokens=16000, thinking_budget=8192)
    report["run_id"] = run_id

    out_key = f"pipeline/{run_id}/analysis_report.json"
    s3_put_json(out_key, report)
    return {
        "analysis_report_key": out_key,
        "component_count": len(report.get("components", [])),
        "endpoint_count": len(report.get("api_endpoints", [])),
    }


def _compact(obj) -> str:
    import json
    return json.dumps(obj, default=str)[:120000]  # guard the prompt size
