"""
Stage 4 (APEX variant) — Validate: behavioural-equivalence tests  |  Oracle Modernization POC

Same "validate" stage as the retail ORDERS suite (see generate_tests.py), but for
the APEX Opportunities CRM "Account Details" domain. Feeds Claude (Opus 4.8) the
LEGACY validation rules recovered from the APEX export plus the GENERATED .NET
AccountService, and asks for a self-contained pytest suite asserting the modern
code reproduces the legacy behaviour exactly — plus an acceptance-criteria matrix.

Output: stage4_validate/apex_tests/  (pytest suite + acceptance doc)

  python3 stage4_validate/generate_apex_tests.py
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
RULES_DOC = os.path.join(ROOT, "stage2_kb", "apex_corpus", "apex_business_rules.md")
GEN = os.path.join(ROOT, "stage3_generate", "apex_generated")
OUT = os.path.join(HERE, "apex_tests")

brt = boto3.client("bedrock-runtime", region_name=REGION,
                   config=Config(read_timeout=900, connect_timeout=20,
                                 retries={"max_attempts": 2}))

SYSTEM = """You are a senior QA engineer proving that a modernized Angular+.NET
application reproduces the behaviour of a legacy Oracle APEX application EXACTLY.
You write executable, self-contained pytest tests. Each test encodes a validation
rule recovered from the legacy APEX page processes/validations and asserts the
modern behaviour matches, including edge cases (null/empty passes the validation
in APEX; case-insensitive duplicate check; the regexp character class as written
in the legacy rule INCLUDING '#'). The tests must be runnable with plain `pytest`
and NO external services or DB — model each rule as a small pure-Python reference
implementation (mirroring the generated .NET logic) and assert against
legacy-derived expected values and exact legacy error strings. Output ONLY the raw
file contents requested — no markdown fences, no commentary."""

FILE_PROMPT = """## Legacy validation rules recovered from the APEX "Account Details" page

Only the Account Details (P3_*) rules are in scope for this suite:

- **P3_CUSTOMER_NAME not duplicated (NOT_EXISTS)** — error: "An account with that name already exists."
  ```sql
  select null from eba_sales_customers
  where (:P3_ID is null or :P3_ID != id)
    and upper(customer_name) = upper(:P3_CUSTOMER_NAME)
  ```
- **Valid Tag Characters (EXPRESSION)** — error: Tags may not contain the following characters: : ; \\ / ? &
  ```sql
  not regexp_like( :P3_TAGS, '[:;#\\/\\\\\\?\\&]' )
  ```
- **Website / LinkedIn / Facebook / Twitter must start with http (EXPRESSION)** — error: Please provide a URL that begins with, "http".
  ```sql
  substr(:P3_CUSTOMER_WEB_SITE, 1, 4) = 'http'
  ```
  (APEX EXPRESSION validations only fire when the item HAS a value; null/empty passes.)

## The modern implementation that must be proven equivalent

### .NET AccountService (excerpt)
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
    ("test_accounts_equivalence.py",
     "a self-contained pytest suite proving behavioural equivalence for the APEX "
     "Account Details validations. Include a small pure-Python reference module INLINE "
     "that mirrors the generated .NET AccountService: "
     "has_invalid_tag_chars(tags) using the legacy regex class [:;#/\\\\?&] (INCLUDING '#'); "
     "starts_with_http(value) where None/empty returns True (passes, matching APEX); "
     "customer_name_is_duplicate(name, existing_rows, exclude_id) doing a case-insensitive "
     "match excluding self; and validate_account(account, existing_rows) that returns the "
     "ordered list of legacy error strings. Then write tests: "
     "(1) duplicate name (case-insensitive) yields exactly 'An account with that name already "
     "exists.' and a differently-cased existing name still collides, and excluding self (same id) "
     "does NOT collide; "
     "(2) tags containing any of : ; # \\ / ? & are rejected with the exact legacy message, and "
     "clean tags pass — use @pytest.mark.parametrize covering each forbidden character incl '#'; "
     "(3) each URL field (website/linkedin/facebook/twitter) must start with 'http'; a non-http "
     "value yields the exact 'Please provide a URL that begins with, \\\"http\\\".' message, "
     "while null/empty passes (APEX only validates when a value is present); "
     "(4) a fully-valid account yields zero errors. "
     "All tests must PASS when run with `pytest`, encoding the LEGACY-correct behaviour as the "
     "oracle. Note explicitly in a comment that the legacy regex rejects '#' even though the "
     "error message text does not list it — the modern code preserves the legacy behaviour, not "
     "the message wording."),
    ("ACCEPTANCE_CRITERIA.md",
     "a concise behavioural-equivalence acceptance-criteria document for the APEX Account Details "
     "domain, mapping each recovered legacy validation (with its APEX validation type and source "
     "item) to the modern .NET implementation location (AccountService.ValidateAsync) and the "
     "pytest test that proves it. Format as a traceability table plus a short 'Definition of Done' "
     "section mirroring the deck's shadow-mode criteria. Call out the '#'-in-regex vs error-text "
     "discrepancy as a preserved legacy quirk."),
]


def strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```[a-zA-Z0-9]*\n(.*)\n```$", t, re.DOTALL)
    if m:
        return m.group(1)
    t = re.sub(r"^```[a-zA-Z0-9]*\n", "", t)
    return re.sub(r"\n```$", "", t)


def excerpt(path, maxlen=6000):
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
    ctx = {"dotnet": excerpt("dotnet/AccountService.cs"),
           "angular": excerpt("angular/account-form.component.ts")}
    os.makedirs(OUT, exist_ok=True)
    print(f"[validate-apex] {GEN_MODEL.split('/')[-1]} — {len(TARGETS)} files", flush=True)
    for path, spec in TARGETS:
        print(f"[validate-apex] -> {path} ...", flush=True)
        content, tok = gen(path, spec, ctx)
        open(os.path.join(OUT, path), "w").write(content)
        print(f"               {len(content)} bytes ({tok} out-tokens)", flush=True)
    print(f"\n[validate-apex] done -> {OUT}/")


if __name__ == "__main__":
    main()
