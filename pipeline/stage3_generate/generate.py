"""
Stage 3 — Generate modern code from the legacy form  |  Oracle AI Modernization POC

Feeds Claude (Bedrock, Opus) the Stage 1 extracted logic for the ORDERS
master-detail form + the DDL schema + KB-retrieved context, and generates the
Phase-1 "replicate exactly" target stack from the deck:

  - Angular component (master-detail: order header + editable line-items grid)
  - .NET API controller + service (thin gateway over the same Oracle DB)
  - OpenAPI contract for the ORDERS domain

Every recovered business rule is passed in explicitly and the model is told to
preserve behaviour exactly (Phase 1 = replicate, not improve). Output is written
as real files under stage3_generate/generated/.

  python3 stage3_generate/generate.py [FORM_MODULE]   # default: ORDERS
"""

from __future__ import annotations
import json, os, re, sys
import boto3
from botocore.config import Config

REGION    = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT   = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
GEN_MODEL = f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PARSED = os.path.join(ROOT, "stage1_parse", "parsed")
SCHEMA = os.path.join(ROOT, "forms", "tables.SQL")
GRAPH = os.path.join(ROOT, "stage1_parse", "graph", "graph.json")
OUT = os.path.join(HERE, "generated")

brt = boto3.client("bedrock-runtime", region_name=REGION,
                   config=Config(read_timeout=900, connect_timeout=20,
                                 retries={"max_attempts": 2}))

SYSTEM = """You are a senior modernization engineer migrating a legacy Oracle Forms
application to a modern Angular + .NET stack on AWS. This is PHASE 1 — REPLICATE:
reproduce the existing screen and behaviour EXACTLY. Do not add features, do not
"improve" the UX, do not refactor the business rules. The Oracle database and its
schema are authoritative and UNCHANGED — the .NET layer is a thin gateway over the
same tables. Preserve every business rule identically, including edge-case handling
(e.g. NVL/null coalescing, sequence-based keys, master-detail referential guards).

You output the FULL contents of exactly ONE file — the one requested — and NOTHING
else: no prose, no explanation, no markdown fences. Just the raw file content.
Produce production-quality, compilable code with the idioms a staff engineer approves."""

# The Phase-1 target file set for the ORDERS master-detail screen.
TARGET_FILES = [
    ("openapi/orders.yaml",
     "an OpenAPI 3.0 contract for the ORDERS domain: GET /orders/{id} (header + "
     "items), GET /orders, POST /orders, PUT /orders/{id}, DELETE /orders/{id}, and "
     "line-item sub-resources POST/PUT/DELETE /orders/{id}/items. Model the exact "
     "ORDERS and ORDER_ITEMS columns from the DDL."),
    ("dotnet/OrderDtos.cs",
     "C# DTO records for the ORDERS domain (OrderDto with a list of OrderItemDto, "
     "plus create/update request DTOs). Namespace Sample.Orders. Match DDL columns/types."),
    ("dotnet/OrderService.cs",
     "a C# service class OrderService (namespace Sample.Orders) using Dapper over Oracle "
     "(Oracle.ManagedDataAccess.Client). It MUST enforce the recovered business rules "
     "server-side: (1) assign ORDER_ID from ORDER_SEQ.NEXTVAL on insert; (2) compute "
     "each line TOTAL_PRICE = NVL(QUANTITY,0)*NVL(UNIT_PRICE,0); (3) block deleting an "
     "order that still has ORDER_ITEMS, throwing with the exact legacy message "
     "'Cannot delete master record when matching detail records exist.'. Methods: "
     "GetById, GetAll, Create, Update, Delete, plus item add/update/delete."),
    ("dotnet/OrdersController.cs",
     "an ASP.NET Core 8 [ApiController] OrdersController (namespace Sample.Orders) that "
     "exposes the OpenAPI contract and delegates to OrderService. Map the delete-guard "
     "exception to HTTP 409 Conflict with the legacy message."),
    ("angular/orders.service.ts",
     "an Angular 17 injectable OrdersService (HttpClient) with typed models mirroring the "
     "DTOs and methods for the full CRUD + line-item operations against the .NET API."),
    ("angular/orders.component.ts",
     "an Angular 17 standalone OrdersComponent (TypeScript) implementing a master-detail "
     "data-entry screen: order header form + editable line-items grid. On quantity or "
     "unit-price change it recomputes the line total as nvl(qty,0)*nvl(price,0) (mirroring "
     "WHEN-VALIDATE-ITEM). Add/Save/Delete/Next/Prev-record actions like the Forms screen. "
     "Uses OrdersService. Include the inline template or reference orders.component.html."),
    ("angular/orders.component.html",
     "the HTML template for OrdersComponent: the order header fields and an editable "
     "ORDER_ITEMS grid with per-row quantity, unit price, and a computed read-only total, "
     "plus the record-navigation and save/delete controls."),
]

CONTEXT_TMPL = """## Legacy source context for module {module} (AI-extracted from the .fmb binary)

### Data schema (Oracle DDL — authoritative, unchanged)
```sql
{schema}
```

### Dependency facts
{deps}

### Business rules recovered from the form's triggers (PRESERVE EXACTLY)
{rules}

### Full trigger inventory with reconstructed PL/SQL
{triggers}
"""

FILE_PROMPT = """{context}

---
Generate the file **{path}**: {spec}

Output ONLY the raw contents of `{path}` — no markdown fences, no commentary."""


def load():
    ordr = json.load(open(os.path.join(PARSED, "ORDERS.json")))
    schema = open(SCHEMA, encoding="utf-8", errors="replace").read().strip()
    graph = json.load(open(GRAPH))
    return ordr, schema, graph


def fmt_rules(form):
    KEY = {"WHEN-VALIDATE-ITEM", "ON-CHECK-DELETE-MASTER", "PRE-INSERT",
           "ON-POPULATE-DETAILS"}
    out = []
    for t in form["triggers"]:
        if t["name"] in KEY and t["plsql"].strip():
            out.append(f"- **{t['name']} ({t['scope']})**\n```plsql\n{t['plsql'].strip()}\n```")
    return "\n".join(out)


def fmt_triggers(form):
    out = []
    for t in form["triggers"]:
        if t["plsql"].strip():
            out.append(f"### {t['name']} on {t['scope']}\n```plsql\n{t['plsql'].strip()}\n```")
    return "\n".join(out)


def fmt_deps(graph):
    lines = []
    for e in graph["edges"]:
        a, b = e["from"].split(":")[1], e["to"].split(":")[1]
        if e["type"] == "FK":
            lines.append(f"- FK: {a}.{e['via']} -> {b}")
        elif e["type"] == "ACCESSES" and a == "ORDERS":
            lines.append(f"- ORDERS accesses table {b}")
        elif e["type"] == "USES_SEQUENCE" and a == "ORDERS":
            lines.append(f"- ORDERS uses sequence {b}")
    return "\n".join(lines)


def strip_fences(text: str, path: str) -> str:
    """Remove a leading/trailing markdown fence if the model added one."""
    t = text.strip()
    m = re.match(r"^```[a-zA-Z0-9]*\n(.*)\n```$", t, re.DOTALL)
    if m:
        return m.group(1)
    # also handle a stray opening fence with no close
    t = re.sub(r"^```[a-zA-Z0-9]*\n", "", t)
    t = re.sub(r"\n```$", "", t)
    return t


def gen_file(context: str, path: str, spec: str) -> str:
    prompt = FILE_PROMPT.format(context=context, path=path, spec=spec)
    resp = brt.converse_stream(
        modelId=GEN_MODEL,
        system=[{"text": SYSTEM}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 8000})
    chunks, out_tok = [], None
    for event in resp["stream"]:
        if "contentBlockDelta" in event:
            chunks.append(event["contentBlockDelta"]["delta"].get("text", ""))
        elif "metadata" in event:
            out_tok = event["metadata"].get("usage", {}).get("outputTokens")
    return strip_fences("".join(chunks), path), out_tok


def main():
    module = sys.argv[1] if len(sys.argv) > 1 else "ORDERS"
    form, schema, graph = load()
    context = CONTEXT_TMPL.format(
        module=module, schema=schema,
        deps=fmt_deps(graph), rules=fmt_rules(form),
        triggers=fmt_triggers(form))

    os.makedirs(OUT, exist_ok=True)
    print(f"[generate] {GEN_MODEL.split('/')[-1]} — {len(TARGET_FILES)} files for {module}", flush=True)
    for path, spec in TARGET_FILES:
        print(f"[generate] -> {path} ...", flush=True)
        content, tok = gen_file(context, path, spec)
        full = os.path.join(OUT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(content)
        print(f"           {len(content)} bytes  ({tok} out-tokens)", flush=True)
    print(f"\n[generate] {len(TARGET_FILES)} files -> {OUT}/")


if __name__ == "__main__":
    main()
