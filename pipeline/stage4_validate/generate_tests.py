"""
Stage 4 — Validate: generate behavioural-equivalence tests  |  Oracle Modernization POC

The deck's Slide 10: "Claude reads each PL/SQL procedure and generates unit tests
asserting the business rules — these become acceptance criteria." This stage feeds
Claude both the LEGACY rule (extracted PL/SQL) and the GENERATED implementation
(.NET service + Angular), and asks it to emit executable tests that assert the
modern code reproduces the legacy behaviour exactly.

We generate two runnable, dependency-free suites so the proof runs anywhere:
  - xUnit-style C# is described in the OpenAPI/acceptance doc, but for an
    executable POC we generate a self-contained **Python pytest** suite that
    re-implements each rule the way the .NET/Angular code does and asserts the
    legacy behaviour — including the edge cases (null coalescing, delete guard).

Output: stage4_validate/tests/  (pytest suite + an acceptance-criteria doc)

  python3 stage4_validate/generate_tests.py
"""

from __future__ import annotations
import json, os, re
import boto3
from botocore.config import Config

REGION    = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT   = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
GEN_MODEL = f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PARSED = os.path.join(ROOT, "stage1_parse", "parsed")
GEN = os.path.join(ROOT, "stage3_generate", "generated")
OUT = os.path.join(HERE, "tests")

brt = boto3.client("bedrock-runtime", region_name=REGION,
                   config=Config(read_timeout=900, connect_timeout=20,
                                 retries={"max_attempts": 2}))

SYSTEM = """You are a senior QA engineer proving that a modernized Angular+.NET
application reproduces the behaviour of a legacy Oracle Forms application EXACTLY.
You write executable, self-contained pytest tests. Each test encodes a business
rule recovered from the legacy PL/SQL and asserts the modern behaviour matches,
including edge cases (null handling, sequence keys, referential guards). The tests
must be runnable with plain `pytest` and NO external services or DB — model the
rule as a small pure-Python reference implementation (mirroring the generated .NET/
Angular logic) and assert against legacy-derived expected values. Output ONLY the
raw file contents requested — no markdown fences, no commentary."""

FILE_PROMPT = """## Legacy business rules recovered from the ORDERS Oracle Form (.fmb)

{rules}

## The modern implementations that must be proven equivalent

### .NET OrderService (excerpt)
```csharp
{dotnet}
```

### Angular component logic (excerpt)
```typescript
{angular}
```

---
Generate the file **{path}**: {spec}

Output ONLY the raw contents of `{path}`."""

TARGETS = [
    ("test_orders_equivalence.py",
     "a self-contained pytest suite proving behavioural equivalence for the ORDERS "
     "form. Include a small pure-Python reference module INLINE (functions "
     "compute_line_total(qty, unit_price), next_order_id(seq_state), and "
     "check_delete_master(order_items) that raises with the exact legacy message). "
     "Then write tests: (1) line total = nvl(qty,0)*nvl(price,0) incl. None/null "
     "inputs and zero cases; (2) PK is assigned from the sequence and increments; "
     "(3) deleting an order WITH items raises the exact legacy message, deleting one "
     "WITHOUT items succeeds. Use @pytest.mark.parametrize for the arithmetic edge "
     "cases. All tests must PASS when run with `pytest`, encoding the LEGACY-correct "
     "behaviour as the oracle."),
    ("ACCEPTANCE_CRITERIA.md",
     "a concise behavioural-equivalence acceptance-criteria document mapping each "
     "recovered legacy rule (with its source trigger) to the modern implementation "
     "location and the test that proves it. Format as a table plus a short "
     "'Definition of Done' section mirroring the deck's shadow-mode criteria."),
]


def strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```[a-zA-Z0-9]*\n(.*)\n```$", t, re.DOTALL)
    if m:
        return m.group(1)
    t = re.sub(r"^```[a-zA-Z0-9]*\n", "", t)
    return re.sub(r"\n```$", "", t)


def fmt_rules():
    form = json.load(open(os.path.join(PARSED, "ORDERS.json")))
    KEY = {"WHEN-VALIDATE-ITEM", "ON-CHECK-DELETE-MASTER", "PRE-INSERT"}
    out = []
    for t in form["triggers"]:
        if t["name"] in KEY and t["plsql"].strip():
            out.append(f"- **{t['name']} ({t['scope']})**\n```plsql\n{t['plsql'].strip()}\n```")
    return "\n".join(out)


def excerpt(path, maxlen=3500):
    p = os.path.join(GEN, path)
    return open(p).read()[:maxlen] if os.path.exists(p) else "(not found)"


def gen(path, spec, ctx):
    prompt = FILE_PROMPT.format(path=path, spec=spec, **ctx)
    resp = brt.converse_stream(
        modelId=GEN_MODEL, system=[{"text": SYSTEM}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 8000})
    chunks, tok = [], None
    for e in resp["stream"]:
        if "contentBlockDelta" in e:
            chunks.append(e["contentBlockDelta"]["delta"].get("text", ""))
        elif "metadata" in e:
            tok = e["metadata"].get("usage", {}).get("outputTokens")
    return strip_fences("".join(chunks)), tok


def main():
    ctx = {"rules": fmt_rules(),
           "dotnet": excerpt("dotnet/OrderService.cs"),
           "angular": excerpt("angular/orders.component.ts")}
    os.makedirs(OUT, exist_ok=True)
    print(f"[validate] {GEN_MODEL.split('/')[-1]} — {len(TARGETS)} files", flush=True)
    for path, spec in TARGETS:
        print(f"[validate] -> {path} ...", flush=True)
        content, tok = gen(path, spec, ctx)
        open(os.path.join(OUT, path), "w").write(content)
        print(f"           {len(content)} bytes ({tok} out-tokens)", flush=True)
    print(f"\n[validate] done -> {OUT}/")


if __name__ == "__main__":
    main()
