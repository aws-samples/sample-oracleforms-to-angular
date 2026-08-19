# Legacy Oracle → Angular/.NET Modernization with a GenAI Migration Pipeline

🇬🇧 English | 🇫🇷 [Français](README.fr.md)

A **sample** that shows how to modernize legacy Oracle applications — **Oracle Forms** and
**Oracle APEX** — into a modern **Angular + .NET** stack on AWS, using a **generative-AI
migration pipeline** built on **Amazon Bedrock**. The pipeline reads the legacy artifacts,
recovers their business rules into a **knowledge base**, generates the target code, and
**validates behavioural equivalence** before anything ships.

> **This is sample code**, published to accompany a demonstration/workshop. It is not
> production software and is provided under the [MIT-0](LICENSE) license. Review, harden, and
> cost-check before any real use. See [Security](#security).

## Overview

Organizations running Oracle Forms and Oracle APEX face end-of-life, security, and
skills-retention pressure, but hand-rewriting hundreds of PL/SQL-backed screens is slow and
risky. This sample demonstrates an **AI-assisted, evidence-based** approach:

- **Parse** the legacy Forms (`.fmb`) and APEX export to recover structure and business logic
  — no AI, fully deterministic.
- **Index** the recovered rules into an **Amazon Bedrock Knowledge Base** (RAG) so developers
  can ask questions about the legacy system in natural language.
- **Generate** the modern Angular + .NET + OpenAPI code with **Amazon Bedrock (Anthropic
  Claude)**, preserving each recovered rule.
- **Validate** the result with generated equivalence tests and an optional live **shadow
  mode** that diffs the modern app against the legacy system on identical inputs.

The legacy inputs here are **legally-clean, public stand-in applications** (see
[The sample legacy apps](#the-sample-legacy-apps)) so the whole pipeline is reproducible by
anyone.

## Architecture

**GenAI migration pipeline**

[![GenAI migration pipeline](docs/architecture-pipeline.svg)](https://raw.githubusercontent.com/bennciz/oracleforms-to-angular/main/docs/architecture-pipeline.svg)

**Target "after" architecture**

[![Target architecture](docs/architecture-target.svg)](https://raw.githubusercontent.com/bennciz/oracleforms-to-angular/main/docs/architecture-target.svg)

## How It Works

| Stage | Service(s) | What it does |
|------|------------|--------------|
| **1 · Parse** | AWS Lambda (container) | Parses Oracle Forms `.fmb` binaries and the APEX export into JSON; builds a dependency graph and recovers business rules. Pure Python — no AI, runs anywhere. |
| **2 · Knowledge Base** | Amazon Bedrock Knowledge Bases · Amazon OpenSearch Serverless · Amazon Titan Text Embeddings v2 | Turns the recovered rules into a Markdown corpus — per-form docs, **business rules (intent + PL/SQL)**, dependency map, and schema (**not** the raw `.fmb`) — embeds it with Titan v2, and indexes it in OpenSearch Serverless for RAG with citations. See [ARCHITECTURE](ARCHITECTURE.md#what-actually-goes-into-the-knowledge-base). |
| **3 · Generate** | Amazon Bedrock (Anthropic Claude) | Generates Angular components, a .NET API, an OpenAPI spec, and tests — one file per call to avoid truncation — each recovered rule traced into the output. |
| **4 · Validate** | AWS Lambda · generated `pytest` | Runs behavioural-equivalence tests. An optional **shadow mode** runs the same inputs through the legacy system and the modern API and diffs every decision. |

The stages are orchestrated by **AWS Step Functions** (STANDARD workflow — the chained
extended-thinking Bedrock calls exceed the Express 5-minute limit). Artifacts and reports are
written to **Amazon S3**; **Amazon CloudWatch** provides observability.

## Prerequisites

- An AWS account with access to **Amazon Bedrock** models (Anthropic Claude + Amazon Titan
  Embeddings) enabled in your region.
- **AWS CLI v2**, **AWS CDK CLI** (`npm i -g aws-cdk`), **Docker**, **Node.js ≥ 18**,
  **Python ≥ 3.11**, **.NET SDK 8**.
- An Oracle database for the "before"/"after" apps. This sample targets **Oracle XE** (e.g.
  the community `gvenzl/oracle-xe:21-slim` image) — **bring your own**; no Oracle binaries are
  redistributed here.

## Quick Start

```bash
cp .env.example .env          # fill in your values
./scripts/deploy-all.sh       # (Windows: ./scripts/deploy-all.ps1)
```

`deploy-all` provisions the infrastructure, builds and pushes the .NET API container, wires
the CloudFront `/api/*` proxy, then builds and ships the Angular SPA. It prints the CloudFront
URL when done.

To run the **migration pipeline** against the bundled sample inputs, see
[`pipeline/README.md`](pipeline/README.md).

## What Gets Deployed

CDK stacks in [`infrastructure/cdk`](infrastructure/cdk):

| Stack | Purpose |
|-------|---------|
| `NetworkStack` | VPC, subnets, security groups, ALB |
| `SecurityStack` | IAM roles, Secrets Manager secret for the DB credential |
| `StorageStack` | S3 (frontend + artifacts), ECR repo, CloudFront distribution + `/api/*` proxy |
| `DatabaseStack` | Oracle XE on EC2 (dev/sandbox) + schema bootstrap |
| `BedrockKBStack` | Bedrock Knowledge Base + OpenSearch Serverless collection/index |
| `PipelineStack` | Step Functions state machine + Lambda-container stages |
| `ApiStack` | ECS Fargate service (the .NET API) behind the ALB |
| `ObservabilityStack` | CloudWatch dashboards/metrics |

## The Sample Legacy Apps

The pipeline's inputs live in [`pipeline/sample-inputs/`](pipeline/sample-inputs) and are
public, permissively-licensed stand-ins — **no customer data or proprietary code**:

- **`forms/`** — an Oracle Forms retail application (6 `.fmb` modules + DDL). Source:
  [oracle-retail-management-system](https://github.com/v7med7elmy-ai/oracle-retail-management-system)
  (MIT).
- **`apex/opportunities.sql`** — an Oracle APEX "Opportunity Tracking" sample application
  (Oracle UPL v1.0).

Oracle schema owners used by the sample are `apex_sample` (APEX tables) and `app_data`
(application data). See [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES).

## Project Structure

```
pipeline/            The GenAI migration pipeline (the star of the sample)
  sample-inputs/     Public stand-in Oracle Forms + APEX apps (sanitized)
  stage1_parse/      Parse .fmb / APEX -> JSON + dependency graph  (no AI)
  stage2_kb/         Build corpus + provision Bedrock KB (RAG)
  stage3_generate/   Generate Angular/.NET/OpenAPI/tests via Bedrock
  stage4_validate/   Behavioural-equivalence pytest suites
  stage5_shadow/     Live legacy-vs-modern shadow-mode comparison
  run_pipeline.py    One-command orchestrator over sample inputs
app/
  angular_app/       Modern "after" SPA (Accounts + Reports screens)
  dotnet_api/        .NET 8 API (thin gateway over Oracle via Dapper)
infrastructure/
  cdk/               AWS CDK (Python) — all stacks above
  pipeline/          The same pipeline steps as AWS Lambda container images,
                     orchestrated by Step Functions (deployed by PipelineStack)
scripts/             deploy-all.sh / .ps1, cleanup.sh
docs/                Architecture diagrams
```

> **Two views of the pipeline.** `pipeline/` is the run-it-and-read-it version — plain Python you
> can execute stage-by-stage over `sample-inputs/` to understand each step. `infrastructure/pipeline/`
> is the *same* steps packaged as Lambda container images that AWS CDK deploys behind AWS Step
> Functions (`PipelineStack`) for the cloud-native, orchestrated run.

## Security

- **No credentials in code.** The .NET API and pipeline read connection details and secrets
  from environment variables / **AWS Secrets Manager** (`.env` is git-ignored; see
  `.env.example`).
- The Angular SPA is served over **HTTPS via CloudFront**; the API is reached **same-origin**
  through a CloudFront `/api/*` reverse-proxy (no mixed content, no CORS).
- Sample IAM is scoped for a **non-production** account. Review and tighten before real use.
- No production data is used anywhere; the legacy inputs are public stand-ins.

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for reporting security issues.

## Cost

This sample provisions billable resources: **Amazon OpenSearch Serverless** (the largest
continuous cost), **Bedrock** inference (per token), **ECS Fargate**, **EC2** (Oracle XE),
**CloudFront**, and **S3**. Run [`scripts/cleanup.sh`](scripts/cleanup.sh) when you are done.

## Cleanup

```bash
./scripts/cleanup.sh          # cdk destroy --all + empties the S3 buckets
```

## Troubleshooting

- **Bedrock "model identifier is invalid" / on-demand not supported** — use an **inference
  profile** ARN (e.g. `us.anthropic.claude-...`), not a bare model id, and enable the model in
  your region.
- **OpenSearch Serverless 401 / timeout on KB ingestion** — the collection is
  **VPC-endpoint-scoped** (public access is disabled). Verify that the AOSS **VPC endpoint**
  (`KB_VPC_ENDPOINT_ID`) exists, is listed in the collection's network-policy `SourceVPCEs`,
  and that the caller (Lambda, local script, etc.) runs inside the VPC or routes through that
  endpoint. Also confirm the data-access policy lists the correct principals (the KB IAM role
  and your caller identity). Do **not** enable public access as a workaround.
- **Angular blank page (NG0908)** — ensure `angular.json` build options include
  `"polyfills": ["zone.js"]`.
- **Mixed-content / CORS errors** — confirm CloudFront is proxying `/api/*` to the ALB and the
  SPA uses a same-origin (empty) API base URL.

## License

This sample is licensed under **MIT-0**. See [LICENSE](LICENSE). Third-party components remain
under their own licenses — see [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES).
