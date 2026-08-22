# The Oracle Forms "before" environment

This sample migrates an Oracle Forms application to Angular + .NET on AWS. The
repository deploys the modern **"after"** app end-to-end; this guide stands up
the legacy **"before"** — a live Oracle Forms 12c service running the very
`ORDERS.fmb` the pipeline parses — against the **same Oracle schema** the
modern API uses, so you can demo a true before/after on one dataset:

```
Forms client ──> WebLogic 12.2.1.4 + Forms Services ──┐
                 (this guide, EC2, BYO binaries)      ├──> application Oracle DB
Browser      ──> CloudFront -> ALB -> ECS (.NET API) ──┘    (sample DatabaseStack,
                 (deploy-all.sh)                            pkg_pricing / pkg_orders)
```

`scripts/forms-setup.sh` codifies the build. It is phase-gated — run
`forms-setup.sh all` or individual phases (`db rcu domain component config
compile start`) — and each phase mirrors commands proven on a live EC2 build
of this environment. Expect to adapt paths/versions to your installation.

## Licensing — read this first

**This repository ships no Oracle software.** You need:

- A **licensed** Oracle Fusion Middleware 12.2.1.4 installation (Infrastructure
  + Forms & Reports) in `MW_HOME`, and an Oracle JDK 8 in `JDK_HOME`.
- Oracle XE 21c (the free `gvenzl/oracle-xe` container) is used **only** as the
  WebLogic repository database (RCU/OPSS schemas), subject to the OTN license.
- A Forms client for rendering: the **Forms Standalone Launcher** (`frmsal.jar`,
  from your FMW installation at `$MW_HOME/forms/java/frmsal.jar`) plus a local
  JRE 8.

## Host

A `t3.xlarge`-class **x86_64** EC2 instance (FMW 12c has no arm64 build) with
~60 GB disk, in a subnet that can reach the sample's database (same VPC, or
VPC peering + a security-group rule allowing 1521 from this host). No inbound
ports are needed if you use SSM port-forwarding for the client.

## Environment variables

Secrets have **no defaults** — export them per shell, and read the application
password from Secrets Manager (`oracle-modernization/oracle/admin` if you used
`deploy-all.sh`), never from a file:

```bash
export MW_HOME=/u01/app/oracle/product/fmw
export JDK_HOME=/u01/jdk
export DOMAIN_HOME=/u01/app/oracle/config/domains/forms_domain
export REPO_DB_PASSWORD=...        # local XE (repository only)
export RCU_SCHEMA_PASSWORD=...
export WLS_ADMIN_PASSWORD=...
export APP_DB_HOST=<DatabaseStack EC2 private IP>
export APP_DB_SERVICE=XEPDB1
export APP_DB_USER=app_data
export APP_DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id oracle-modernization/oracle/admin \
  --query SecretString --output text | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')
bash scripts/forms-setup.sh all
```

Prerequisite: the application schema must already carry the ORDERS tables and
the `pkg_pricing`/`pkg_orders` packages — `deploy-all.sh` seeds them via
`infrastructure/seed-sql/app_data_packages.sql`.

## Rendering the form

The served page is the legacy applet bootstrap; modern browsers cannot run it.
Use the Forms Standalone Launcher from your workstation over an SSM tunnel:

```bash
aws ssm start-session --target <forms-instance-id> --region <region> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["9001"],"localPortNumber":["9101"]}'
java -jar frmsal.jar -url "http://localhost:9101/forms/frmservlet?config=orders"
```

At the logon prompt enter the application schema credentials (database =
`APPDB`). Press F8 to query; the same orders appear in the modern app.

## Gotcha catalog

Every one of these was hit while building this environment. They are encoded
in `forms-setup.sh`, and listed here for when you deviate from it.

| Symptom | Cause / fix |
|---|---|
| `FRM-91500: Unable to start/complete the build` from `frmcmp_batch` | `FORMS_INSTANCE` and/or `TERM` not set. Export `FORMS_INSTANCE=<domain>/config/fmwconfig/components/FORMS/forms1` and `TERM=vt220` (template domains ship no per-component `bin/` wrapper that would do this for you). |
| `FRM-93131: Cannot find base HTML file` | `baseHTML`/`baseHTMLjpi` in `formsweb.cfg` must be **absolute paths** — the servlet's relative search directory is not the config directory. |
| `FRM-93136: no base TXT file` (standalone launcher only) | Add `baseSAAfile=<absolute>/basesaa.txt` to the config section. |
| Oracle*Terminal error mentioning `fmrweb` at runtime | Add `term=$MW_HOME/forms/fmrweb.res` to the config section. |
| Servlet 404 / missing component files on a fresh template domain | A template-built domain ships an **incomplete FORMS component instance**. Copy `$MW_HOME/forms/templates/config/*` into `.../FORMS/forms1/server/` and fix `default.env` (`components/FORMS/instances/forms1` → `components/FORMS/forms1`). |
| `Error: No domain has been read` at `writeDomain` in WLST | Benign JRF post-step message — the domain **was** written. |
| RCU rejects the password flag | The flag is `-useSamePasswordForAllSchemaUsers` (…Users, not …Schemas). |
| AdminServer of a **cloned/moved** domain never boots (JPS/OPSS errors) | A JRF domain's OPSS security store lives in its repository DB. If that DB is gone the domain is unrecoverable — build a **fresh** domain (it self-initializes an empty OPSS store on first boot). Never separate a JRF domain from its RCU database. |
| `frmf2xml`/`frmxml2f` (XML round-trip dev tools) fail to load | Export `FORMS_API_TK_BYPASS=TRUE`; on minimal hosts the JDAPI also needs Motif libraries (`libXm.so.4`, `libXp.so.6`) on the library path. |
| Pipeline mis-parses a round-tripped `.fmb` | Feed the pipeline **source** fmbs (Forms Builder- or `frmxml2f`-written). An `.fmb` re-saved by `frmcmp_batch compile_all=yes` moves trigger sources into a compiled-unit region and is not a valid pipeline input. |
| Config edits don't take effect | `formsweb.cfg`/`tnsnames.ora` are read per Forms session (no restart needed), but changes under the FORMS component directory need a WLS_FORMS restart. |
| Logon dialog appears despite `userid=` in the config | Forms deliberately does not auto-forward the password to the client logon — expected behaviour. |

## What this gives the demo

- The **same business rules** run on both sides: the form's triggers call
  `pkg_orders.set_status` / `pkg_pricing.order_totals` /
  `pkg_pricing.line_unit_price`, exactly the packages the modern API gateways
  to — and exactly the calls stage 1 of the pipeline recovers from the `.fmb`.
- Legacy error behaviour (`ORA-20001..-20006`, hardcoded English) surfaces in
  the Forms status bar; the modern app localizes the same codes.
- Data written in the form appears in the modern app on refresh, and vice
  versa (re-query with F8 on the Forms side).
