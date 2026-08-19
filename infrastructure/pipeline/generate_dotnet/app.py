"""GenerateDotNet — scaffold a .NET 8 Web API for the migrated screen.

Input : state with analysis_report_key, openapi_key, plsql_corpus_key.
Output: { "dotnet_zip_key": "pipeline/{run_id}/generated/dotnet_api.zip",
          "file_count": N }

The generator is told to call the existing Oracle PL/SQL via Dapper +
Oracle.ManagedDataAccess.Core (managed driver, no native client), preserving the
business rules that live in the packages rather than reimplementing them.
"""
from common.aws_helpers import (
    s3_get_json, s3_get_text, s3_put_zip, converse_files, FILES_PROTOCOL,
    CLAUDE_MODEL_ID,
)

SYSTEM = (
    "You are a senior .NET engineer. You generate .NET 8 Web API code using "
    "Oracle.ManagedDataAccess.Core and Dapper. You call existing Oracle stored "
    "procedures/packages rather than rewriting business logic. "
    + FILES_PROTOCOL
)


def handler(event, _context):
    run_id = event["run_id"]
    analysis = s3_get_json(event["analysis"]["analysis_report_key"])
    openapi = s3_get_text(event["openapi"]["openapi_key"])
    corpus = s3_get_json(event["plsql"]["plsql_corpus_key"])

    import json
    user = f"""Generate a .NET 8 Web API implementing this OpenAPI contract for the
migrated Oracle Forms screen. Use Oracle.ManagedDataAccess.Core + Dapper. Call the
existing PL/SQL packages (e.g. APP_DATA.PKG_SAMPLE_OPS, APP_DATA.PKG_SAMPLE_LOGIC)
for writes and business logic; use direct queries for simple reads.

## Migration analysis
{json.dumps(analysis, default=str)[:50000]}

## OpenAPI contract
{openapi[:25000]}

## Backing PL/SQL (call these; do NOT reimplement the rules)
{json.dumps(corpus, default=str)[:40000]}

Rules:
- Controllers match the OpenAPI paths. Services encapsulate DB access.
- Connection string from configuration key ConnectionStrings:Oracle (built from
  ORACLE_HOST/ORACLE_PORT/ORACLE_SERVICE/ORACLE_USER/ORACLE_PASSWORD env vars).
- Include a GET /health endpoint that checks the Oracle connection.
- Provide Program.cs, controllers, services, models, and a Dockerfile that
  builds and runs on linux (dotnet publish, expose 8080)."""

    # A full .NET 8 API scaffold (Program.cs + controllers + services + models +
    # Dockerfile + csproj) is the largest generation in the pipeline. Sonnet 4.5
    # allows up to 64K output tokens; the thinking budget counts toward that, so
    # leave generous headroom. The delimiter file protocol (converse_files)
    # avoids the JSON-escaping fragility that truncated this step as JSON.
    files = converse_files(
        SYSTEM, user, model_id=CLAUDE_MODEL_ID, max_tokens=60000, thinking_budget=6000)

    out_key = f"pipeline/{run_id}/generated/dotnet_api.zip"
    s3_put_zip(out_key, files)
    return {"dotnet_zip_key": out_key, "file_count": len(files)}
