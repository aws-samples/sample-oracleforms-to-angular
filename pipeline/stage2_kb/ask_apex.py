import json, os, sys, textwrap, boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCT   = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
GEN    = f"arn:aws:bedrock:{REGION}:{ACCT}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# KB_ID is written to kb_ids.json by provision_kb.py; pass it as an env var
# (KB_ID=<your-kb-id>) or re-run provision_kb.py to regenerate kb_ids.json.
_ids_path = os.path.join(os.path.dirname(__file__), "kb_ids.json")
if os.path.exists(_ids_path):
    KB_ID = json.load(open(_ids_path))["kb_id"]
else:
    KB_ID = os.environ.get("KB_ID", "<YOUR_KB_ID>")

bra = boto3.client("bedrock-agent-runtime", REGION)
Q = [
 "What business rule prevents duplicate customer accounts, and what error does it show?",
 "What validation rules apply to the Account Details page (tags, website, LinkedIn)?",
 "How does the app compute the revenue-by-quarter reporting period?",
 "Which PL/SQL package handles user access control and preferences?",
 "How are new users added to the system?",
]

def ask(q):
    r = bra.retrieve_and_generate(input={"text": q},
      retrieveAndGenerateConfiguration={"type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": {
        "knowledgeBaseId": KB_ID, "modelArn": GEN,
        "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 6}}}})
    print("\n" + "=" * 76 + f"\nQ: {q}\n" + "-" * 76)
    print(r["output"]["text"])
    cites = []
    for c in r.get("citations", []):
        for ref in c.get("retrievedReferences", []):
            u = ref.get("location", {}).get("s3Location", {}).get("uri", "")
            if u and u not in cites:
                cites.append(u)
    if cites:
        print("Sources:", ", ".join(u.split("/")[-1] for u in cites))

for q in Q:
    ask(q)
