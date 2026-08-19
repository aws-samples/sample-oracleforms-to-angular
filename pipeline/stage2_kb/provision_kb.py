"""
Stage 2 (part 2) — Provision the Bedrock Knowledge Base on OpenSearch Serverless.

Creates, idempotently and in the correct dependency order:
  1. IAM role for the KB (trust bedrock.amazonaws.com; S3 read + Titan embed + AOSS)
  2. OpenSearch Serverless: encryption policy, network policy, data-access policy
  3. OpenSearch Serverless VECTORSEARCH collection
  4. The vector index (via the AOSS data-plane, SigV4-signed)
  5. Bedrock Knowledge Base + S3 data source, then starts an ingestion job

Region from AWS_REGION (default us-east-1), account from CDK_DEFAULT_ACCOUNT. Titan Embed v2 (1024-dim).
Writes stage2_kb/kb_ids.json for the query tool.

Run:  python3 stage2_kb/provision_kb.py
"""

from __future__ import annotations
import json, os, sys, time
import boto3
from botocore.exceptions import ClientError

REGION  = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT = os.environ["CDK_DEFAULT_ACCOUNT"]          # required — set before running
# The AOSS collection is reachable ONLY via this VPC endpoint — public access is disabled.
# The endpoint is provisioned by BedrockKbStack (CDK) and must be supplied here before
# running this script.  Failing without it is intentional (fail-closed security posture).
VPCE = os.environ.get("KB_VPC_ENDPOINT_ID")
if not VPCE:
    raise SystemExit(
        "Set KB_VPC_ENDPOINT_ID to an OpenSearch Serverless VPC endpoint id; "
        "public access is intentionally not supported."
    )
# Bucket name pattern: oracle-modernization-kb-<account>-<region>
# The bucket is created by StorageStack; set it explicitly via env var if needed.
BUCKET  = os.environ.get("KB_BUCKET", f"oracle-modernization-kb-{ACCOUNT}-{REGION}")
PREFIX = "corpus/"

NAME = "oracle-modernization-kb"
COLL = "oracle-modernization"               # <=32 chars, aoss collection name
INDEX = "oracle-kb-index"
EMBED_MODEL = f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
EMBED_DIM = 1024
ROLE_NAME = "oracle-modernization-kb-role"
HERE = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(HERE, "kb_ids.json")

iam = boto3.client("iam", region_name=REGION)
aoss = boto3.client("opensearchserverless", region_name=REGION)
bar = boto3.client("bedrock-agent", region_name=REGION)
sts = boto3.client("sts", region_name=REGION)

ids = {}
if os.path.exists(IDS_PATH):
    ids = json.load(open(IDS_PATH))

def save():
    json.dump(ids, open(IDS_PATH, "w"), indent=2)

def log(m): print(f"[provision] {m}", flush=True)


# ---- 1. IAM role -------------------------------------------------------------
def ensure_role() -> str:
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}},
    }]}
    try:
        r = iam.create_role(RoleName=ROLE_NAME,
                            AssumeRolePolicyDocument=json.dumps(trust),
                            Description="Bedrock KB role for Oracle modernization POC")
        arn = r["Role"]["Arn"]
        log(f"created role {arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        log(f"role exists {arn}")

    policy = {"Version": "2012-10-17", "Statement": [
        {"Sid": "S3Read", "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]},
        {"Sid": "Embed", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel"], "Resource": [EMBED_MODEL]},
        # Interim scope: account+region-bounded until the collection ARN is
        # known.  main() calls _patch_role_aoss_scope() to tighten this to
        # the specific collection ARN once ensure_collection() has run.
        {"Sid": "AOSS", "Effect": "Allow",
         "Action": ["aoss:APIAccessAll"],
         "Resource": [f"arn:aws:aoss:{REGION}:{ACCOUNT}:collection/*"]},
    ]}
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="kb-access",
                        PolicyDocument=json.dumps(policy))
    ids["role_arn"] = arn; save()
    return arn


def _patch_role_aoss_scope(collection_arn: str):
    """Re-apply the inline policy with AOSS resource pinned to the specific collection ARN."""
    policy = {"Version": "2012-10-17", "Statement": [
        {"Sid": "S3Read", "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]},
        {"Sid": "Embed", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel"], "Resource": [EMBED_MODEL]},
        # Scoped to the specific collection ARN now that it is known.
        {"Sid": "AOSS", "Effect": "Allow",
         "Action": ["aoss:APIAccessAll"], "Resource": [collection_arn]},
    ]}
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="kb-access",
                        PolicyDocument=json.dumps(policy))
    log(f"patched role AOSS resource scope to {collection_arn}")


# ---- 2. AOSS policies --------------------------------------------------------
def ensure_aoss_policies(role_arn: str):
    caller = sts.get_caller_identity()["Arn"]
    # assumed-role arn -> role arn for data-access principal
    admin_role = caller.replace(":sts:", ":iam:").split("/")
    admin_principal = f"arn:aws:iam::{ACCOUNT}:role/{admin_role[1]}" if len(admin_role) > 1 else caller

    enc = {"Rules": [{"ResourceType": "collection",
                      "Resource": [f"collection/{COLL}"]}],
           "AWSOwnedKey": True}
    _put_aoss("encryption", enc)

    # Collection is reachable only via the VPC endpoint — AllowFromPublic is False.
    # SourceVPCEs restricts access to the endpoint provisioned by BedrockKbStack.
    net = [{"Rules": [{"ResourceType": "collection", "Resource": [f"collection/{COLL}"]},
                      {"ResourceType": "dashboard", "Resource": [f"collection/{COLL}"]}],
            "AllowFromPublic": False,
            "SourceVPCEs": [VPCE]}]
    _put_aoss("network", net)

    access = [{"Rules": [
        {"ResourceType": "index", "Resource": [f"index/{COLL}/*"],
         "Permission": ["aoss:*"]},
        {"ResourceType": "collection", "Resource": [f"collection/{COLL}"],
         "Permission": ["aoss:*"]}],
        "Principal": [role_arn, admin_principal, caller]}]
    _put_aoss("data", access)

def _put_aoss(kind: str, policy):
    name = f"{COLL}-{kind}"[:32]
    typ = {"encryption": "encryption", "network": "network", "data": "data"}[kind]
    body = json.dumps(policy)
    try:
        if typ == "encryption":
            aoss.create_security_policy(name=name, type="encryption", policy=body)
        elif typ == "network":
            aoss.create_security_policy(name=name, type="network", policy=body)
        else:
            aoss.create_access_policy(name=name, type="data", policy=body)
        log(f"created {kind} policy {name}")
    except ClientError as e:
        if "ConflictException" in str(e):
            log(f"{kind} policy exists {name}")
        else:
            raise


# ---- 3. Collection -----------------------------------------------------------
def ensure_collection() -> tuple[str, str]:
    try:
        r = aoss.create_collection(name=COLL, type="VECTORSEARCH",
                                   description="Oracle modernization KB vectors")
        log("creating collection...")
    except ClientError as e:
        if "ConflictException" not in str(e):
            raise
        log("collection exists")
    # wait for ACTIVE
    for _ in range(60):
        cs = aoss.batch_get_collection(names=[COLL])["collectionDetails"]
        if cs and cs[0]["status"] == "ACTIVE":
            c = cs[0]
            log(f"collection ACTIVE: {c['collectionEndpoint']}")
            ids["collection_arn"] = c["arn"]
            ids["collection_endpoint"] = c["collectionEndpoint"]
            ids["collection_id"] = c["id"]; save()
            return c["arn"], c["collectionEndpoint"]
        time.sleep(10)
    sys.exit("collection did not become ACTIVE in time")


# ---- 4. Vector index (AOSS data plane) --------------------------------------
def ensure_index(endpoint: str):
    from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
    host = endpoint.replace("https://", "")
    creds = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(creds, REGION, "aoss")
    client = OpenSearch(hosts=[{"host": host, "port": 443}], http_auth=auth,
                        use_ssl=True, verify_certs=True,
                        connection_class=RequestsHttpConnection, timeout=60)
    body = {"settings": {"index": {"knn": True}},
            "mappings": {"properties": {
                "vector": {"type": "knn_vector", "dimension": EMBED_DIM,
                           "method": {"name": "hnsw", "engine": "faiss",
                                      "space_type": "l2"}},
                "text": {"type": "text"},
                "metadata": {"type": "text", "index": False}}}}
    if client.indices.exists(index=INDEX):
        log(f"index exists {INDEX}")
    else:
        client.indices.create(index=INDEX, body=body)
        log(f"created index {INDEX}")
    time.sleep(45)  # index must be queryable before KB creation


# ---- 5. Knowledge Base + data source ----------------------------------------
def ensure_kb(role_arn: str, coll_arn: str) -> str:
    if ids.get("kb_id"):
        try:
            bar.get_knowledge_base(knowledgeBaseId=ids["kb_id"])
            log(f"KB exists {ids['kb_id']}")
            return ids["kb_id"]
        except ClientError:
            pass
    r = bar.create_knowledge_base(
        name=NAME, roleArn=role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {"embeddingModelArn": EMBED_MODEL}},
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": coll_arn, "vectorIndexName": INDEX,
                "fieldMapping": {"vectorField": "vector", "textField": "text",
                                 "metadataField": "metadata"}}})
    kb_id = r["knowledgeBase"]["knowledgeBaseId"]
    ids["kb_id"] = kb_id; save()
    log(f"created KB {kb_id}")

    ds = bar.create_data_source(
        knowledgeBaseId=kb_id, name="oracle-corpus",
        dataSourceConfiguration={"type": "S3",
            "s3Configuration": {"bucketArn": f"arn:aws:s3:::{BUCKET}",
                                "inclusionPrefixes": [PREFIX]}})
    ds_id = ds["dataSource"]["dataSourceId"]
    ids["data_source_id"] = ds_id; save()
    log(f"created data source {ds_id}")
    return kb_id


def ingest(kb_id: str, ds_id: str):
    job = bar.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    jid = job["ingestionJob"]["ingestionJobId"]
    log(f"ingestion job {jid} started")
    for _ in range(60):
        st = bar.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id,
                                   ingestionJobId=jid)["ingestionJob"]
        if st["status"] in ("COMPLETE", "FAILED"):
            log(f"ingestion {st['status']}: {st.get('statistics', {})}")
            return st["status"]
        time.sleep(10)
    log("ingestion still running")


def main():
    role_arn = ensure_role()
    log("waiting 12s for IAM propagation..."); time.sleep(12)
    ensure_aoss_policies(role_arn)
    coll_arn, endpoint = ensure_collection()
    # Now that the collection ARN is known, tighten the role policy to the
    # specific collection ARN (least-privilege upgrade from collection/*).
    _patch_role_aoss_scope(coll_arn)
    ensure_index(endpoint)
    kb_id = ensure_kb(role_arn, coll_arn)
    ingest(kb_id, ids["data_source_id"])
    log(f"DONE. ids -> {IDS_PATH}")
    print(json.dumps(ids, indent=2))


if __name__ == "__main__":
    main()
