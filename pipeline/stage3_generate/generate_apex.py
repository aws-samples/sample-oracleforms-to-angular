"""Stage 3 (APEX) — generate modern Angular+.NET for the APEX Opportunities CRM
Account Details domain (the richest: dedup rule, tag/URL validations)."""
import json, os, re, boto3
from botocore.config import Config
REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCT   = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
GEN    = f"arn:aws:bedrock:{REGION}:{ACCT}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
brt=boto3.client("bedrock-runtime",REGION,config=Config(read_timeout=900,retries={"max_attempts":2}))
HERE=os.path.dirname(os.path.abspath(__file__))
app=json.load(open(os.path.join(HERE,"..","stage1_parse","apex_parsed","opportunities_crm.json")))
OUT=os.path.join(HERE,"apex_generated"); os.makedirs(OUT,exist_ok=True)

# gather the Account Details domain rules + processes
rules=[v for v in app["validations"] if v.get("page")=="Account Details"]
procs=[p for p in app["processes"] if p["plsql"] and not p["plsql"].startswith("-- declarative")][:8]
rules_txt="\n".join(f"- {v['name']} ({v['type']}): {v.get('error_message')}\n  ```sql\n  {v.get('condition','').strip()}\n  ```" for v in rules)
procs_txt="\n".join(f"### {p['name']} [{p['type']}]\n```plsql\n{p['plsql'].strip()}\n```" for p in procs)
tables=", ".join(app["tables"][:20])

SYS=("You are a senior engineer migrating a real Oracle APEX application to Angular + .NET. "
 "Phase 1 = replicate behaviour EXACTLY, preserving every validation and business rule. "
 "Output ONLY the raw file contents requested, no fences, no commentary.")
CTX=(f"# APEX Opportunities CRM — Account Details domain (AI-extracted)\n\n"
 f"Tables: {tables}\n\nPackages: {app['packages']}\n\n"
 f"## Validation rules to preserve exactly\n{rules_txt}\n\n"
 f"## Sample PL/SQL processes\n{procs_txt}\n")
TARGETS=[
 ("openapi/accounts.yaml","OpenAPI 3.0 contract for the Accounts (customers) domain: CRUD on accounts with the recovered validations (unique name, tag character rules, website/linkedin must start with http)."),
 ("dotnet/AccountService.cs","C# .NET 8 service (Dapper/Oracle) for accounts that enforces server-side: unique customer_name (case-insensitive, excluding self), tag character blacklist, and http-prefix URL checks. Namespace Sample.Apex.Accounts."),
 ("angular/account-form.component.ts","Angular 17 standalone AccountFormComponent with reactive-form validators mirroring the APEX rules (unique-name async check, tag pattern, url prefix). Uses an AccountService."),
]
def strip(t):
    t=t.strip(); m=re.match(r"^```[a-z]*\n(.*)\n```$",t,re.DOTALL)
    return m.group(1) if m else re.sub(r"\n```$","",re.sub(r"^```[a-z]*\n","",t))
for path,spec in TARGETS:
    print(f"[apex-gen] {path} ...",flush=True)
    r=brt.converse_stream(modelId=GEN,system=[{"text":SYS}],
      messages=[{"role":"user","content":[{"text":CTX+f"\n---\nGenerate **{path}**: {spec}\nOutput ONLY the raw file contents."}]}],
      inferenceConfig={"maxTokens":8000})
    chunks=[]
    for e in r["stream"]:
        if "contentBlockDelta" in e: chunks.append(e["contentBlockDelta"]["delta"].get("text",""))
    c=strip("".join(chunks))
    full=os.path.join(OUT,path); os.makedirs(os.path.dirname(full),exist_ok=True)
    open(full,"w").write(c); print(f"   {len(c)} bytes",flush=True)
print(f"[apex-gen] done -> {OUT}/")
