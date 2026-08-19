"""ValidateBehavioural — Claude compares the generated .NET against the original
PL/SQL and flags behavioural discrepancies.

Input : state with dotnet_zip_key (in $.generated) and plsql_corpus_key.
Output: { "validation_report_key": "pipeline/{run_id}/validation_report.json",
          "finding_count": N, "high_severity_count": N }

This is the "prove equivalence" stage. It reads the generated .NET back out of
the zip and asks Claude, with extended thinking, to find places where the port
drifts from the PL/SQL business rules.
"""
import io
import zipfile

import boto3

from common.aws_helpers import (
    s3_get_json, s3_put_json, converse_json, CLAUDE_MODEL_ID, ARTIFACTS_BUCKET,
)

_s3 = boto3.client("s3")

SYSTEM = (
    "You are a meticulous code reviewer verifying that a migrated .NET Web API "
    "faithfully reproduces the behaviour of the original Oracle PL/SQL. You look "
    "for missing null checks, dropped error handling, incomplete business rules, "
    "and parameter-validation gaps. You answer with STRICT JSON only."
)


def _read_zip_text(key: str, limit: int = 60000) -> str:
    obj = _s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    out = []
    with zipfile.ZipFile(buf) as zf:
        for name in zf.namelist():
            if name.endswith((".cs",)):
                out.append(f"// FILE: {name}\n" + zf.read(name).decode("utf-8", "replace"))
    return "\n\n".join(out)[:limit]


def handler(event, _context):
    run_id = event["run_id"]

    # The parallel Generate stage nests results under $.generated as a list
    # [angularResult, dotnetResult]; locate the dotnet zip robustly.
    dotnet_zip_key = _find_key(event, "dotnet_zip_key")
    plsql = s3_get_json(event["plsql"]["plsql_corpus_key"])

    dotnet_src = _read_zip_text(dotnet_zip_key)

    import json
    user = f"""Compare the migrated .NET implementation against the original PL/SQL
and report behavioural discrepancies.

## Original PL/SQL (authoritative business logic)
{json.dumps(plsql, default=str)[:60000]}

## Generated .NET source
{dotnet_src}

Return STRICT JSON:
{{ "findings": [ {{ "severity": "HIGH|MEDIUM|LOW",
                    "procedure": string,
                    "description": string,
                    "recommendation": string }} ],
   "overall_assessment": string }}"""

    report = converse_json(
        SYSTEM, user, model_id=CLAUDE_MODEL_ID,
        max_tokens=12000, thinking_budget=8192)
    findings = report.get("findings", [])
    report["run_id"] = run_id

    out_key = f"pipeline/{run_id}/validation_report.json"
    s3_put_json(out_key, report)
    return {
        "validation_report_key": out_key,
        "finding_count": len(findings),
        "high_severity_count": sum(
            1 for f in findings if f.get("severity") == "HIGH"),
    }


def _find_key(event, field):
    """Search the (possibly nested/parallel) state for a given result key.

    The Parallel Generate stage returns an ARRAY under $.generated, one entry
    per branch. Each branch also applied its own result_path ($.angular /
    $.dotnet), so the branch output nests the actual result one level deeper:
    $.generated[i].dotnet.dotnet_zip_key. Recurse so we find the key wherever
    the state-machine wrapping placed it.
    """
    def _search(node):
        if isinstance(node, dict):
            if field in node:
                return node[field]
            for v in node.values():
                found = _search(v)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = _search(item)
                if found is not None:
                    return found
        return None

    found = _search(event.get("generated"))
    if found is None:
        raise KeyError(f"{field} not found in pipeline state")
    return found
