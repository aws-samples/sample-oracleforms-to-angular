"""
Stage 2 (part 3) — Query the Knowledge Base (RAG).

Uses Bedrock RetrieveAndGenerate: retrieves the most relevant chunks from the
OpenSearch Serverless vector index and has Claude answer with citations.
This demonstrates the "every developer gets a senior engineer who has read every
line of legacy code" capability from the deck.

  python3 stage2_kb/ask_kb.py                       # run the demo questions
  python3 stage2_kb/ask_kb.py "your question here"  # ad-hoc
"""

from __future__ import annotations
import json, os, sys, textwrap
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
# Sonnet 4.5 requires an inference profile (cross-region), not the bare model id.
ACCOUNT   = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
GEN_MODEL = f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
HERE      = os.path.dirname(os.path.abspath(__file__))

# KB_ID is written to kb_ids.json by provision_kb.py; pass it as an env var
# (KB_ID=<your-kb-id>) or re-run provision_kb.py to regenerate kb_ids.json.
_ids_path = os.path.join(HERE, "kb_ids.json")
if os.path.exists(_ids_path):
    _ids = json.load(open(_ids_path))
    KB_ID = _ids["kb_id"]
else:
    KB_ID = os.environ.get("KB_ID", "<YOUR_KB_ID>")

bra = boto3.client("bedrock-agent-runtime", region_name=REGION)

DEMO_QUESTIONS = [
    "Which forms open or navigate to the ORDERS form?",
    "What business rule governs the order line total price, and what is the exact formula?",
    "What happens if someone tries to delete an order that still has order items?",
    "How is the primary key for a new order assigned?",
    "Which tables does the ORDERS form read or write, and how do they relate by foreign key?",
    "I'm new to this system — give me an onboarding overview of what each form does.",
]


def ask(q: str) -> None:
    resp = bra.retrieve_and_generate(
        input={"text": q},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": KB_ID,
                "modelArn": GEN_MODEL,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {"numberOfResults": 6}},
            }})
    answer = resp["output"]["text"]
    cites = []
    for c in resp.get("citations", []):
        for ref in c.get("retrievedReferences", []):
            uri = ref.get("location", {}).get("s3Location", {}).get("uri", "")
            if uri and uri not in cites:
                cites.append(uri)

    print("\n" + "=" * 78)
    print("Q:", q)
    print("-" * 78)
    print("\n".join(textwrap.wrap(answer, 76,
          replace_whitespace=False)) if "\n" not in answer else answer)
    if cites:
        print("\nSources:")
        for u in cites:
            print("  -", u.split("/")[-1])


def main():
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
    else:
        print(f"Knowledge Base  (KB {KB_ID})  —  demo questions")
        for q in DEMO_QUESTIONS:
            ask(q)


if __name__ == "__main__":
    main()
