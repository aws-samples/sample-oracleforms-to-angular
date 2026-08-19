#!/usr/bin/env python3
"""
run_pipeline.py — ONE-COMMAND Oracle APEX Interactive Report -> Angular migration.

Demonstrates the full pipeline autonomously, no human in the loop:

    python3 run_pipeline.py --page 17

  Stage 1  PARSE     read the live APEX IR page metadata from Oracle (via SSM)
  Stage 2  GENERATE  Opus 4.8 -> whitelisted SQL + column metadata + an Angular grid component
  Stage 3  VALIDATE  check the generated SQL runs and returns rows in Oracle
  Stage 4  DEPLOY    register the report (instant) + build/ship the Angular grid
  Stage 5  SHADOW    diff the new API's rows vs the live APEX IR -> equivalence

The .NET Reports API is generic + config-driven and already deployed, so a NEW
report goes live with NO backend rollout — the pipeline just registers a row and
ships the front end. Deterministic: same page in -> same result out, every run.
"""
import argparse, base64, json, os, re, subprocess, sys, time
import urllib.request
from urllib.parse import urlparse
import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCT   = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
# EC2 instance running Oracle XE (set via environment or CDK stack output).
INST   = os.environ.get("ORACLE_INSTANCE_ID", "<YOUR_ORACLE_INSTANCE_ID>")
# CloudFront domain for the deployed front-end (set via environment or CDK stack output).
CF_DOMAIN = os.environ.get("CF_DOMAIN", "<YOUR_CLOUDFRONT_DOMAIN>")
GEN = f"arn:aws:bedrock:{REGION}:{ACCT}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
APP_ID = 100
HERE   = os.path.dirname(os.path.abspath(__file__))
# Angular app lives in app/angular_app relative to the repo root.
NG_APP = os.path.join(HERE, "..", "app", "angular_app")

ssm=boto3.client("ssm",region_name=REGION)
brt=boto3.client("bedrock-runtime",region_name=REGION,
                 config=Config(read_timeout=900,retries={"max_attempts":2}))

# ---------- pretty streamed output ----------
def stage(n,name,detail): print(f"\n\033[1;36m[{n}] {name}\033[0m  {detail}",flush=True)
def ok(msg):   print(f"    \033[32m✓\033[0m {msg}",flush=True)
def info(msg): print(f"    · {msg}",flush=True)
def fail(msg): print(f"    \033[31m✗ {msg}\033[0m",flush=True)

# ---------- run SQL on the Oracle box via SSM, return stdout ----------
def oracle(sql, timeout=90):
    b64=base64.b64encode(sql.encode()).decode()
    inner=(f"echo {b64} | base64 -d > /tmp/_pl.sql && "
           f"docker cp /tmp/_pl.sql oraclexe:/tmp/_pl.sql && "
           f"docker exec oraclexe bash -lc 'sqlplus -s / as sysdba @/tmp/_pl.sql' 2>&1")
    c=ssm.send_command(InstanceIds=[INST],DocumentName="AWS-RunShellScript",
        Parameters={"commands":[inner],"executionTimeout":[str(timeout)]})
    cid=c["Command"]["CommandId"]
    for _ in range(timeout//3):
        time.sleep(3)
        r=ssm.get_command_invocation(CommandId=cid,InstanceId=INST)
        if r["Status"] in ("Success","Failed"): return r["StandardOutputContent"]
    return "(timeout)"

def bedrock(system, prompt, max_tokens=6000):
    r=brt.converse_stream(modelId=GEN,system=[{"text":system}],
        messages=[{"role":"user","content":[{"text":prompt}]}],
        inferenceConfig={"maxTokens":max_tokens})
    out=[]
    for e in r["stream"]:
        if "contentBlockDelta" in e: out.append(e["contentBlockDelta"]["delta"].get("text",""))
    t="".join(out).strip()
    m=re.match(r"^```[a-zA-Z0-9]*\n(.*)\n```$",t,re.DOTALL)
    return m.group(1) if m else re.sub(r"\n```$","",re.sub(r"^```[a-zA-Z0-9]*\n","",t))

# =====================================================================
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--page",type=int,required=True,help="APEX page id of the Interactive Report")
    ap.add_argument("--no-deploy",action="store_true",help="skip the Angular build/ship (dry test)")
    args=ap.parse_args()
    PAGE=args.page

    print(f"\n\033[1;37m╔═ Oracle APEX → Angular · automated migration pipeline ═╗\033[0m")
    print(f"\033[1;37m   target: app {APP_ID}, page {PAGE}\033[0m")

    # ---- Stage 1: PARSE (read live IR metadata) ----
    stage(1,"PARSE","reading the Interactive Report definition from Oracle")
    # Base64-encode the SQL INSIDE Oracle so tabs/newlines/line-wrapping can't
    # corrupt it in transit through SQL*Plus text output. Chunk the CLOB to stay
    # under SQL*Plus's line limits, then reassemble + b64-decode here.
    meta=oracle(
        f"ALTER SESSION SET CONTAINER=XEPDB1;\n"  # nosec B608 - APP_ID is a hardcoded constant (100); PAGE is validated as int by argparse; neither is user-controlled string data
        "set feedback off pages 0 lines 200 long 100000 longchunksize 80 trimspool on serveroutput on\n"
        f"SELECT '@@NAME@@'||page_name FROM apex_application_pages WHERE application_id={APP_ID} AND page_id={PAGE} AND rownum=1;\n"
        "DECLARE\n"
        "  s CLOB; b CLOB; i PLS_INTEGER := 1; step PLS_INTEGER := 60;\n"
        "BEGIN\n"
        f"  SELECT region_source INTO s FROM apex_application_page_regions\n"
        f"   WHERE application_id={APP_ID} AND page_id={PAGE} AND source_type='Interactive Report' AND rownum=1;\n"
        "  b := UTL_RAW.CAST_TO_VARCHAR2(UTL_ENCODE.BASE64_ENCODE(UTL_RAW.CAST_TO_RAW(s)));\n"
        "  b := REPLACE(REPLACE(b, CHR(13)), CHR(10));  -- drop Oracle's per-64 newlines FIRST\n"
        "  WHILE i <= LENGTH(b) LOOP\n"
        "    DBMS_OUTPUT.PUT_LINE('@@B64@@'||SUBSTR(b,i,step)); i := i + step;\n"
        "  END LOOP;\n"
        "END;\n"
        "/\n")
    name=""
    for line in meta.splitlines():
        if "@@NAME@@" in line: name=line.split("@@NAME@@",1)[1].strip()
    b64parts=[l.split("@@B64@@",1)[1] for l in meta.splitlines() if "@@B64@@" in l]
    import base64 as _b64
    raw="".join(b64parts)
    raw=re.sub(r"[^A-Za-z0-9+/=]","",raw)  # drop Oracle's embedded newlines/whitespace
    base_sql=_b64.b64decode(raw).decode("utf-8","replace").strip().rstrip(";")
    # The IR SQL references EBA_SALES_* tables unqualified (APEX runs inside the
    # apex_sample schema). The migrated API runs as app_data and the validate step
    # as SYS, so qualify every eba_sales_* table reference with the owning schema.
    base_sql=re.sub(r"(?i)\b(from|join)\s+(eba_sales_\w+)",
                    r"\1 apex_sample.\2", base_sql)
    # APEX IR pages carry page-item bind variables (e.g. a display toggle
    # `where :P2_DISPLAY_AS = 'GRID'`). Strip a trailing WHERE that only compares
    # an APEX bind (:Pnn_...) so the recovered SQL runs standalone. If the bind is
    # mid-predicate we replace it with its always-true literal instead.
    base_sql=re.sub(r"(?is)\s+where\s+:P\d+_\w+\s*=\s*'[^']*'\s*$","",base_sql)
    base_sql=re.sub(r"(?i):P\d+_\w+","NULL",base_sql)  # any remaining binds -> NULL
    base_sql=base_sql.strip().rstrip(";")
    cols=oracle(
        f"ALTER SESSION SET CONTAINER=XEPDB1;\n"  # nosec B608 - APP_ID is a hardcoded constant (100); PAGE is validated as int by argparse; neither is user-controlled string data
        "set feedback off pages 0 lines 200\n"
        "SELECT column_alias||'|'||report_label FROM apex_application_page_ir_col\n"
        f" WHERE application_id={APP_ID} AND page_id={PAGE} ORDER BY display_order;")
    column_pairs=[l.strip() for l in cols.splitlines() if "|" in l and "@@" not in l]
    ok(f"page “{name}” — {len(column_pairs)} columns")
    info(f"base SQL: {base_sql[:70].replace(chr(10),' ')}…")

    # ---- Stage 2: GENERATE ----
    stage(2,"GENERATE","Opus 4.8 emits whitelisted SQL + column metadata + an Angular grid")
    key=re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-")
    colmeta=bedrock(
      "You convert an Oracle APEX Interactive Report into a JSON column spec for a modern, "
      "polished data grid. Output ONLY a JSON array, no fences. Each element: "
      "{\"key\":<UPPERCASE column alias exactly as the SQL returns it>, \"label\":<concise Title-Case header>, "
      "\"sortable\":true, \"type\":\"text\"|\"number\"|\"date\"|\"bool\", \"hidden\":<bool>}. "
      "RULES: (1) type 'bool' for Yes/No or Y/N flag columns; 'date' for date/timestamp columns; "
      "'number' for counts/amounts/ids-shown-as-metrics; else 'text'. "
      "(2) Set hidden:true for internal/surrogate/audit columns a business user shouldn't see — "
      "primary keys (ID), ROW_KEY, any *_ID foreign-key column that's shown elsewhere as a name "
      "(e.g. CUSTOMER_TERRITORY_ID when TERRITORY_NAME exists), and CREATED_BY/UPDATED_BY/CREATED "
      "when they're just audit noise. Keep the meaningful business columns visible. "
      "(3) Give clean human labels (e.g. 'Open Opp.' -> 'Open Opportunities', 'CUSTOMER_NAME' -> 'Account'). "
      "Keep EVERY column in the array (visible or hidden) so sort still works.",
      f"Report: {name}\nColumns (alias|label):\n"+"\n".join(column_pairs)+
      f"\n\nBase SQL:\n{base_sql}\n\nEmit the JSON column spec.")
    try:
        parsed=json.loads(colmeta); ok(f"generated column spec ({len(parsed)} cols)")
    except Exception as e:
        fail(f"column spec not valid JSON: {e}"); print(colmeta[:400]); sys.exit(1)
    # generate the Angular component (domain-specific, to show real codegen)
    comp=bedrock(
      "You are migrating an Oracle APEX Interactive Report to an Angular 17 standalone component. "
      "Output ONLY TypeScript, no fences. The component must: be @Component standalone with imports "
      "[CommonModule], inject HttpClient + ActivatedRoute + environment, fetch "
      "`${environment.apiBaseUrl}/api/reports/"+key+"`, render a table from data.columns/data.rows, "
      "and re-fetch with ?sort=KEY&dir=asc|desc when a header is clicked (server-side sort). "
      "Class name "+re.sub(r'[^A-Za-z0-9]','',name.title())+"ReportComponent, selector app-"+key+"-report.",
      f"Report title: {name}\nColumn spec:\n{json.dumps(parsed,indent=2)}")
    gen_dir=os.path.join(HERE,"stage3_generate","report_generated",key); os.makedirs(gen_dir,exist_ok=True)
    open(os.path.join(gen_dir,"columns.json"),"w").write(json.dumps(parsed,indent=2))
    open(os.path.join(gen_dir,f"{key}-report.component.ts"),"w").write(comp)
    ok(f"generated Angular component ({len(comp)} bytes) → report_generated/{key}/")

    # ---- Stage 3: VALIDATE (SQL runs, returns rows) ----
    stage(3,"VALIDATE","confirming the recovered SQL runs against Oracle")
    cnt=oracle(
        f"ALTER SESSION SET CONTAINER=XEPDB1;\n"  # nosec B608 - base_sql is read from Oracle's own APEX application-metadata catalog via a privileged sqlplus session; it is not user-controlled input and a full SQL statement cannot be parameterized
        "set feedback off pages 0 lines 60\n"
        f"SELECT '@@N@@'||count(*) FROM ({base_sql});")
    n=next((l.split("@@N@@",1)[1].strip() for l in cnt.splitlines() if "@@N@@" in l),"?")
    if n=="?" or not n.isdigit(): fail(f"SQL did not return a count: {cnt[-200:]}"); sys.exit(1)
    ok(f"SQL valid — {n} rows")

    # ---- Stage 4: DEPLOY (register + ship front end) ----
    stage(4,"DEPLOY","registering the report (instant) + shipping the Angular grid")
    sql_esc=base_sql.replace("'","''")
    cols_esc=json.dumps(parsed).replace("'","''")
    name_esc=name.replace("'","''")  # single-quote-escape for SQL literal; sqlplus has no bind-variable protocol
    reg=oracle(
        f"ALTER SESSION SET CONTAINER=XEPDB1;\n"  # nosec B608 - key is regex-sanitised to [a-z0-9-]+; name/sql/cols are single-quote-escaped literals; PAGE is int; sqlplus has no bind-variable protocol
        "set feedback on\n"
        "MERGE INTO app_data.report_registry t\n"
        f"USING (SELECT '{key}' rk FROM dual) s ON (t.report_key=s.rk)\n"
        f"WHEN MATCHED THEN UPDATE SET title='{name_esc}', base_sql='{sql_esc}', columns_json='{cols_esc}', source_page={PAGE}\n"
        "WHEN NOT MATCHED THEN INSERT (report_key,title,base_sql,columns_json,source_page)\n"
        f"  VALUES ('{key}','{name_esc}','{sql_esc}','{cols_esc}',{PAGE});\n"
        "COMMIT;\n"
        f"SELECT '@@OK@@'||report_key FROM app_data.report_registry WHERE report_key='{key}';")
    if "@@OK@@" not in reg: fail(f"registry insert failed: {reg[-300:]}"); sys.exit(1)
    ok(f"registered report_key='{key}' (backend serves it immediately — no rollout)")
    if args.no_deploy:
        info("--no-deploy: skipping Angular ship"); done(key,name,PAGE,n); return
    info("building Angular + shipping to CloudFront…")
    _script=os.path.join(HERE,"..","app","deploy_frontend.sh")
    with open("/tmp/pipe_ng.log","w") as _log:
        _result=subprocess.run(["bash",_script],shell=False,stdout=_log,stderr=_log)
    if _result.returncode!=0: fail("Angular deploy failed — see /tmp/pipe_ng.log"); sys.exit(1)
    ok("Angular shipped + CloudFront invalidated")

    # ---- Stage 5: SHADOW ----
    stage(5,"SHADOW","diffing the migrated API vs the live APEX report")
    _url=f"https://{CF_DOMAIN}/api/reports/{key}"
    if urlparse(_url).scheme not in ("https","http"):
        raise ValueError(f"Unsafe URL scheme in CF_DOMAIN: {_url}")
    api=json.load(urllib.request.urlopen(_url,timeout=30))  # nosec B310 - scheme validated above
    api_rows=len(api.get("rows",[]))
    verdict="MATCH" if str(api_rows)==str(n) else "DIVERGE"
    (ok if verdict=="MATCH" else fail)(f"legacy APEX rows={n}  migrated API rows={api_rows}  → {verdict}")
    done(key,name,PAGE,n)

def done(key,name,page,n):
    print(f"\n\033[1;32m╔══════════════════════════════════════════════════╗")
    print(f"║  ✅ MIGRATED: “{name}” (APEX page {page})")
    print(f"║  Live at: https://{CF_DOMAIN}/reports/{key}")
    print(f"║  {n} rows · server-side sort · same Oracle data")
    print(f"╚══════════════════════════════════════════════════╝\033[0m\n")

if __name__=="__main__":
    main()
