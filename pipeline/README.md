# GenAI Migration Pipeline

Parse → Knowledge Base → Generate → Validate, over the bundled sample legacy apps. See the
repo [ARCHITECTURE.md](../ARCHITECTURE.md) for the design rationale.

## Layout

```
sample-inputs/     Public stand-in legacy apps (Oracle Forms retail + APEX opportunities)
stage1_parse/      .fmb / APEX -> JSON + dependency graph   (deterministic, no AI)
stage2_kb/         Build corpus + provision Bedrock Knowledge Base (RAG)
stage3_generate/   Generate Angular / .NET / OpenAPI / tests via Amazon Bedrock
stage4_validate/   Behavioural-equivalence pytest suites (+ acceptance criteria)
stage5_shadow/     Optional: live legacy-vs-modern shadow comparison
run_pipeline.py    One-command orchestrator over the sample inputs
```

## Prerequisites

- Python ≥ 3.11 with `boto3` (`pip install boto3`); Graphviz `dot` for the graph image.
- AWS credentials with **Amazon Bedrock** access (Claude inference profile + Titan
  Embeddings) for stages 2–4. Stage 1 needs no AWS/AI.
- Copy [`../.env.example`](../.env.example) to `../.env` and set the values (region, KB ids, …).

## Run it

**Stage 1 — parse (offline, no AWS):**

```bash
python stage1_parse/fmb_parser.py  sample-inputs/forms   -o stage1_parse/parsed
python stage1_parse/build_graph.py stage1_parse/parsed sample-inputs/forms/tables.SQL
python stage1_parse/apex_parser.py sample-inputs/apex/opportunities.sql -o stage1_parse/apex_parsed
```

Outputs land in `stage1_parse/parsed/`, `stage1_parse/graph/`, `stage1_parse/apex_parsed/`.
Example outputs are committed so you can inspect them without running anything.

**Stage 2 — knowledge base (provisions AWS resources):**

```bash
python stage2_kb/build_corpus.py       # -> corpus/*.md
python stage2_kb/provision_kb.py       # creates S3 + OpenSearch Serverless + Bedrock KB; prints KB_ID
python stage2_kb/ask_kb.py "what is the order line-total formula?"
```

Put the printed `KB_ID` in your `.env`.

**Stage 3 — generate (Amazon Bedrock):**

```bash
python stage3_generate/generate.py         # retail Orders -> generated/
python stage3_generate/generate_apex.py    # APEX Account Details -> apex_generated/
```

**Stage 4 — validate:**

```bash
pytest stage4_validate/tests               # retail Orders equivalence
pytest stage4_validate/apex_tests          # APEX Account Details equivalence
```

**Optional Stage 5 — shadow mode** (requires a running legacy environment + the modern API):
see the scripts in `stage5_shadow/`.

## Notes

- Amazon Bedrock requires an **inference-profile** ARN (e.g. `us.anthropic.claude-...`), not a
  bare model id.
- Generation is **one file per model call** (verbatim source, not JSON) to avoid truncation —
  see ARCHITECTURE.md.
- No credentials are hardcoded; scripts read ids/secrets from environment variables.
