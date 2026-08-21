# Deployment guide

The README's Quick Start (`./scripts/deploy-all.sh`) is the whole deploy — this
page documents the decisions the script asks you to make, the switches it
honors, what a successful run looks like, and how to verify and clean up.

## Before you start

1. **Region + Bedrock access.** Set `AWS_REGION`, and enable the Anthropic
   Claude and Amazon Titan Embeddings models in that region (Bedrock console →
   Model access). Only needed for the Knowledge Base / pipeline stacks — the
   app path (`APP_ONLY=1`) deploys without it.
2. **Bootstrap-ready credentials.** The script runs `cdk bootstrap` on first
   use; your credentials must be able to create the CDK toolkit stack.
3. **TLS decision (required — the deploy stops without one).** The ALB in
   front of the API is HTTPS-only by design:
   - Production-like: pass an ACM certificate —
     `CDK_CONTEXT="-c acm_cert_arn=arn:aws:acm:..."` (or add `acm_cert_arn`
     to `cdk.json`). HTTP :80 exists only to redirect to :443.
   - Sandbox: `ENABLE_HTTP_SANDBOX=1` deploys a plain-HTTP listener. Never use
     this outside a disposable sandbox account.
   Either value must reach **every** cdk invocation — `deploy-all.sh` does
   this for you; if you run `cdk` by hand, pass the same `-c` flags every
   time (the app synthesizes all stacks on every call).

## Switches

All optional, environment-variable driven:

| Variable | Effect |
|---|---|
| `APP_ONLY=1` | Deploy only the app path (network, security, storage, database, API, frontend); skip BedrockKB, Pipeline, and Observability stacks. Fastest path to the running before/after demo. |
| `ENABLE_HTTP_SANDBOX=1` | Plain-HTTP ALB listener instead of requiring an ACM cert (sandbox only). |
| `ARCH=amd64\|arm64` | Container + Fargate CPU architecture. Defaults to the build host's architecture so the Docker build is always native; the same value drives the task definition, so image and service can never diverge. |

## What a successful run does (in order)

1. `cdk bootstrap` (idempotent), then Network, Security, Storage stacks.
2. **Uploads the seed SQL** (`infrastructure/seed-sql/*.sql`) to the artifacts
   bucket — the DatabaseStack instance pulls these at first boot to create:
   - `app_data` — the ORDERS retail schema, seed dataset, and the Tier-1
     business rules (`pkg_pricing`, `pkg_orders`, stock/freeze triggers);
   - `apex_sample` (a **locked** account; the API reaches it via grants) —
     the EBA sales tables behind the Accounts screen;
   - `app_data.report_registry` — the config-driven Reports catalog.
3. DatabaseStack (Oracle XE on EC2 — dev/sandbox posture), then the .NET API
   image (build → ECR → ApiStack ECS Fargate behind the ALB), and waits for
   `/health` to report `oracle: true`.
4. Unless `APP_ONLY=1`: BedrockKB, Pipeline, and Observability stacks. The
   OpenSearch Serverless collection is **VPC-endpoint-only** (no public
   access); `.env`'s `KB_VPC_ENDPOINT_ID` must point at the created endpoint
   for stage-2 ingestion (fail-closed if unset).
5. Redeploys StorageStack with the ALB DNS to wire the CloudFront `/api/*`
   proxy, builds the Angular SPA, syncs it to S3, invalidates CloudFront, and
   prints the CloudFront URL.

## Verify

```bash
CF=https://<your-cloudfront-domain>
curl $CF/api/orders | head -c 300        # ORDERS rows from the seed
curl $CF/api/orders/1/totals             # pkg_pricing.order_totals via the API
curl $CF/api/accounts | head -c 300      # EBA accounts (39-digit string ids)
curl $CF/api/reports                     # report catalog: accounts, countries
```

Then open the CloudFront URL: `/orders` (lifecycle panel: COMPUTE TOTALS,
CONFIRM, MARK READY, PAY, CANCEL), `/accounts`, `/reports/countries`. The
EN/FR toggle localizes the chrome and the legacy `ORA-2000x` error codes.

Deeper checks, both included in the repo:

- **Shadow harness** — `pipeline/stage5_shadow/shadow_orders.py` replays the
  legacy PL/SQL and the live API side by side (see
  `SHADOW_RESULTS_ORDERS.md` for the battery and the latest 31/31 run).
- **Pipeline** — `pipeline/README.md` covers running the five stages against
  the bundled sample inputs.

## The legacy "before" apps (optional, bring-your-own)

The deployable sample is the modern "after". To run the legacy side against
the same database:

- **Oracle Forms** — `docs/FORMS_BEFORE_ENV.md` + `scripts/forms-setup.sh`
  stand up WebLogic + Forms Services serving the sample's `ORDERS.fmb`
  (licensed Oracle FMW 12.2.1.4 binaries required).
- **Oracle APEX** — the Accounts/Reports data is seeded by
  `apex_sample_seed.sql`, but the APEX runtime and the app-100 import
  (`pipeline/sample-inputs/apex/opportunities.sql`) are not automated; import
  them into your own APEX/ORDS environment if you want the APEX "before" live.

## Costs and cleanup

The deployed footprint runs continuously (EC2 Oracle XE, ECS Fargate, ALB,
CloudFront, and — without `APP_ONLY=1` — an OpenSearch Serverless collection,
which bills by OCU and dominates the cost). Tear everything down with:

```bash
./scripts/cleanup.sh
```

which empties the buckets and destroys the stacks in reverse order.
