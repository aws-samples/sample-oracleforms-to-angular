"""GenerateOpenAPI — turn the analysis report + argument metadata into a clean
OpenAPI 3.1 contract for the migrated screen.

Input : state with analysis_report_key and args_metadata_key.
Output: { "openapi_key": "pipeline/{run_id}/openapi.yaml" }
"""
from common.aws_helpers import (
    s3_get_json, s3_put_text, converse, CLAUDE_MODEL_ID,
)

SYSTEM = (
    "You are an API designer. Given a migration analysis of an Oracle Forms "
    "screen and its PL/SQL signatures, you emit a single, valid OpenAPI 3.1 "
    "document in YAML. Output ONLY the YAML — no prose, no code fences."
)


def handler(event, _context):
    run_id = event["run_id"]
    analysis = s3_get_json(event["analysis"]["analysis_report_key"])
    args = s3_get_json(event["plsql"]["args_metadata_key"])

    import json
    user = f"""Produce an OpenAPI 3.1 YAML contract for this migrated screen.

## Migration analysis
{json.dumps(analysis, default=str)[:80000]}

## PL/SQL signatures (for request/response schema fidelity)
{json.dumps(args, default=str)[:20000]}

Requirements:
- One path per api_endpoint in the analysis.
- Components/schemas derived from data_models (types, required flags).
- Include realistic example values.
- info.title = the screen name, version 1.0.0.
Output ONLY the YAML document."""

    yaml_text = converse(
        SYSTEM, user, model_id=CLAUDE_MODEL_ID, max_tokens=12000, temperature=0.2)
    yaml_text = _strip_fences(yaml_text)

    out_key = f"pipeline/{run_id}/openapi.yaml"
    s3_put_text(out_key, yaml_text, content_type="application/yaml")
    return {"openapi_key": out_key, "bytes": len(yaml_text)}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("yaml"):
            t = t.lstrip()[4:]
        t = t.rsplit("```", 1)[0]
    return t.strip() + "\n"
