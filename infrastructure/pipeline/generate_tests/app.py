"""GenerateIntegrationTests — auto-generate integration tests from the OpenAPI
contract + validation findings, asserting the business rules from the PL/SQL.

Input : state with openapi_key, validation_report_key, plsql_corpus_key.
Output: { "integration_tests_key": "pipeline/{run_id}/generated/integration_tests.zip",
          "file_count": N }
"""
from common.aws_helpers import (
    s3_get_json, s3_get_text, s3_put_zip, converse_files, FILES_PROTOCOL,
    CLAUDE_MODEL_ID,
)

SYSTEM = (
    "You are a QA automation engineer. You write xUnit integration tests (C#) "
    "against a .NET Web API, asserting the business rules of the original Oracle "
    "PL/SQL and specifically covering the discrepancies a reviewer flagged. "
    + FILES_PROTOCOL
)


def handler(event, _context):
    run_id = event["run_id"]
    openapi = s3_get_text(event["openapi"]["openapi_key"])
    validation = s3_get_json(event["validation"]["validation_report_key"])
    plsql = s3_get_json(event["plsql"]["plsql_corpus_key"])

    import json
    user = f"""Generate xUnit integration tests for the migrated .NET API. Cover the
happy paths from the OpenAPI contract AND add explicit regression tests for each
finding in the validation report (e.g. null handling, rejected OFFLINE-pot
readings, MAINTENANCE->ONLINE transition rule).

## OpenAPI contract
{openapi[:20000]}

## Validation findings to cover
{json.dumps(validation, default=str)[:20000]}

## Original PL/SQL business rules (source of truth)
{json.dumps(plsql, default=str)[:30000]}"""

    # Delimiter file protocol (converse_files) avoids JSON-escaping fragility on
    # large multi-file generations.
    files = converse_files(
        SYSTEM, user, model_id=CLAUDE_MODEL_ID, max_tokens=40000, temperature=0.2)

    out_key = f"pipeline/{run_id}/generated/integration_tests.zip"
    s3_put_zip(out_key, files)
    return {"integration_tests_key": out_key, "file_count": len(files)}
