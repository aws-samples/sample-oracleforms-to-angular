"""CloudFormation custom resource: create the OpenSearch Serverless vector
index that a Bedrock Knowledge Base requires to pre-exist.

CfnKnowledgeBase validates the target index at create time, so the index must
be present *before* the KB resource. CDK cannot create an AOSS index natively,
so this Lambda does it against the collection data-plane endpoint using SigV4.

Create : create the k-NN index (idempotent — ignores "already exists").
Update : ensure the index exists (no destructive remap).
Delete : drop the index (best-effort; never blocks stack deletion).
"""
import json
import time
import urllib.parse
import urllib.request

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth


def _client(host, region):
    creds = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(creds, region, "aoss")
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
        timeout=60,
    )


def _index_body(vector_field, text_field, metadata_field, dimension):
    # FAISS/HNSW k-NN index matching the Bedrock KB field mapping. AOSS requires
    # knn enabled at index-settings level.
    return {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                vector_field: {
                    "type": "knn_vector",
                    "dimension": int(dimension),
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "l2",
                        "parameters": {"ef_construction": 512, "m": 16},
                    },
                },
                text_field: {"type": "text"},
                metadata_field: {"type": "text"},
            }
        },
    }


def _send(event, context, status, reason=""):
    body = json.dumps({
        "Status": status,
        "Reason": (reason or f"See CloudWatch log stream {context.log_stream_name}")[:1024],
        "PhysicalResourceId": event.get("PhysicalResourceId") or event["LogicalResourceId"],
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": {},
    }).encode("utf-8")
    resp_url = event["ResponseURL"]
    if urllib.parse.urlparse(resp_url).scheme not in ("https", "http"):
        raise ValueError(f"Unsafe ResponseURL scheme: {resp_url}")
    req = urllib.request.Request(
        resp_url, data=body, method="PUT",
        headers={"content-type": "", "content-length": str(len(body))},
    )
    urllib.request.urlopen(req)  # nosec B310 - scheme validated above; ResponseURL is always an S3 presigned https URL provided by CloudFormation


def handler(event, context):
    print(json.dumps({k: event.get(k) for k in ("RequestType", "LogicalResourceId")}))
    props = event["ResourceProperties"]
    host = props["Endpoint"].replace("https://", "")
    region = props["Region"]
    index = props["IndexName"]
    client = _client(host, region)
    body = _index_body(
        props["VectorField"], props["TextField"],
        props["MetadataField"], props["Dimension"])

    try:
        rtype = event["RequestType"]
        if rtype in ("Create", "Update"):
            if not client.indices.exists(index=index):
                client.indices.create(index=index, body=body)
                print(f"created index {index}")
                # AOSS is eventually consistent; give the index time to be
                # queryable before the KB validates it.
                time.sleep(30)
            else:
                print(f"index {index} already exists")
        elif rtype == "Delete":
            if client.indices.exists(index=index):
                client.indices.delete(index=index)
                print(f"deleted index {index}")
        _send(event, context, "SUCCESS")
    except Exception as exc:  # surface the failure to CloudFormation
        print(f"ERROR: {exc}")
        # On Delete, never block teardown on a data-plane hiccup.
        if event["RequestType"] == "Delete":
            _send(event, context, "SUCCESS", f"delete ignored: {exc}")
        else:
            _send(event, context, "FAILED", str(exc))
