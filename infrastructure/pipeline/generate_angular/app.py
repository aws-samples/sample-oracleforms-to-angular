"""GenerateAngular — scaffold Angular components for the migrated screen.

Input : state with analysis_report_key and openapi_key.
Output: { "angular_zip_key": "pipeline/{run_id}/generated/angular_components.zip",
          "file_count": N }

Claude returns a JSON map of {relative_path: file_contents}; we zip it to S3.
Field names are instructed to match the original Forms items exactly so the
migrated UI is recognisably the same screen.
"""
from common.aws_helpers import (
    s3_get_json, s3_get_text, s3_put_zip, converse_files, FILES_PROTOCOL,
    CLAUDE_MODEL_ID,
)

SYSTEM = (
    "You are a senior Angular engineer. You generate Angular 17 standalone "
    "components using reactive forms and Angular Material. "
    + FILES_PROTOCOL
)


def handler(event, _context):
    run_id = event["run_id"]
    analysis = s3_get_json(event["analysis"]["analysis_report_key"])
    openapi = s3_get_text(event["openapi"]["openapi_key"])

    import json
    user = f"""Generate an Angular 17 feature module for this migrated Oracle Forms
master-detail screen. Use standalone components, reactive forms, Angular Material,
and a typed HttpClient service that calls the REST API described by the OpenAPI
contract.

## Migration analysis
{json.dumps(analysis, default=str)[:60000]}

## OpenAPI contract
{openapi[:30000]}

Rules:
- Field/control names MUST match the original Forms item names.
- Provide: a master list/grid component, a detail component, a data service,
  and TypeScript models. Wire the master-detail relation.
- Assume the API base URL comes from environment.apiUrl."""

    # Delimiter file protocol (converse_files) avoids JSON-escaping fragility on
    # large multi-file generations. 60K matches the .NET step's headroom.
    files = converse_files(
        SYSTEM, user, model_id=CLAUDE_MODEL_ID, max_tokens=60000, thinking_budget=6000)

    out_key = f"pipeline/{run_id}/generated/angular_components.zip"
    s3_put_zip(out_key, files)
    return {"angular_zip_key": out_key, "file_count": len(files)}
