"""Shared helpers for the pipeline Lambdas: S3 I/O, Secrets, Bedrock Converse.

Design rules enforced here:
  * Lambdas exchange S3 KEYS via the state machine, never file bodies.
  * Bedrock uses the Converse API. Extended thinking sets thinking.budget_tokens
    and OMITS temperature/top_p/top_k (Bedrock rejects them with thinking on).
  * Errors surface loudly (no silent except/pass).
"""
import io
import json
import os
import zipfile

import boto3
from botocore.config import Config

_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Adaptive retries absorb Bedrock throttling without hand-rolled backoff.
_BOTO_CFG = Config(retries={"max_attempts": 6, "mode": "adaptive"})

# Bedrock generation of large outputs (multi-thousand-token OpenAPI specs and
# code) routinely runs well past botocore's default 60s socket read_timeout,
# which surfaces as ReadTimeoutError and burns the whole Lambda budget on
# retries. Give the Bedrock client a read_timeout that fits a long generation
# but stays under the 15-min Lambda timeout, and cap its own retries at 2 so a
# genuine hang fails fast rather than silently looping.
_BEDROCK_CFG = Config(
    region_name=_REGION,
    retries={"max_attempts": 2, "mode": "adaptive"},
    read_timeout=600,
    connect_timeout=10,
)

_s3 = boto3.client("s3", config=_BOTO_CFG)
_secrets = boto3.client("secretsmanager", region_name=_REGION, config=_BOTO_CFG)
_bedrock = boto3.client("bedrock-runtime", config=_BEDROCK_CFG)
_bedrock_agent = boto3.client("bedrock-agent", region_name=_REGION, config=_BOTO_CFG)

ARTIFACTS_BUCKET = os.environ["ARTIFACTS_BUCKET"]
CLAUDE_MODEL_ID = os.environ.get(
    "CLAUDE_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
CLAUDE_LARGE_MODEL_ID = os.environ.get(
    "CLAUDE_LARGE_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")


# --------------------------------------------------------------------------- #
# S3
# --------------------------------------------------------------------------- #
def s3_get_text(key: str) -> str:
    obj = _s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=key)
    return obj["Body"].read().decode("utf-8")


def s3_get_json(key: str) -> dict:
    return json.loads(s3_get_text(key))


def s3_put_text(key: str, text: str, content_type: str = "text/plain") -> str:
    _s3.put_object(Bucket=ARTIFACTS_BUCKET, Key=key,
                   Body=text.encode("utf-8"), ContentType=content_type)
    return key


def s3_put_json(key: str, obj) -> str:
    return s3_put_text(key, json.dumps(obj, indent=2, default=str),
                       content_type="application/json")


def s3_put_zip(key: str, files: dict) -> str:
    """Zip a {relative_path: text} map and upload it. Returns the key."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buf.seek(0)
    _s3.put_object(Bucket=ARTIFACTS_BUCKET, Key=key, Body=buf.getvalue(),
                   ContentType="application/zip")
    return key


# --------------------------------------------------------------------------- #
# Secrets
# --------------------------------------------------------------------------- #
def get_secret_json(secret_arn: str) -> dict:
    resp = _secrets.get_secret_value(SecretId=secret_arn)
    return json.loads(resp["SecretString"])


# --------------------------------------------------------------------------- #
# Bedrock Converse
# --------------------------------------------------------------------------- #
def converse(
    system_prompt: str,
    user_text: str,
    *,
    model_id: str = None,
    max_tokens: int = 8192,
    thinking_budget: int = 0,
    temperature: float = None,
):
    """Call the Bedrock Converse API and return the assistant text.

    If thinking_budget > 0, extended thinking is enabled and temperature/top_p/
    top_k are OMITTED (Bedrock rejects them when thinking is on). Otherwise a
    temperature may be supplied for deterministic-ish generation.
    """
    model = model_id or CLAUDE_MODEL_ID
    inference_config = {"maxTokens": max_tokens}
    additional_fields = {}

    if thinking_budget and thinking_budget >= 1024:
        additional_fields["thinking"] = {
            "type": "enabled", "budget_tokens": thinking_budget}
        # IMPORTANT: do not set temperature/top_p/top_k with thinking enabled.
    elif temperature is not None:
        inference_config["temperature"] = temperature

    kwargs = dict(
        modelId=model,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig=inference_config,
    )
    if additional_fields:
        kwargs["additionalModelRequestFields"] = additional_fields

    resp = _bedrock.converse(**kwargs)
    # Fail loud on truncation: stopReason == "max_tokens" means the model ran
    # into the output cap and the text is incomplete. Returning it silently lets
    # a truncated JSON body reach json.loads() and surface as a misleading
    # "Unterminated string" far from the real cause. Surface it here instead.
    stop_reason = resp.get("stopReason")
    if stop_reason == "max_tokens":
        raise RuntimeError(
            f"Bedrock response truncated at maxTokens={max_tokens} "
            f"(stopReason=max_tokens). Raise max_tokens for this step.")
    parts = resp["output"]["message"]["content"]
    # Skip reasoningContent blocks; concatenate text blocks.
    return "".join(p["text"] for p in parts if "text" in p)


def converse_json(system_prompt: str, user_text: str, **kwargs) -> dict:
    """Converse and parse the reply as JSON, tolerating ```json fences."""
    raw = converse(system_prompt, user_text, **kwargs)
    return _extract_json(raw)


def _extract_json(raw: str):
    text = raw.strip()
    if text.startswith("```"):
        # strip ```json ... ``` or ``` ... ```
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: grab the outermost JSON object/array.
        start = min((i for i in (text.find("{"), text.find("[")) if i != -1),
                    default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        raise


# --------------------------------------------------------------------------- #
# Multi-file generation (delimiter format, NOT JSON)
# --------------------------------------------------------------------------- #
# The Bedrock model can reliably emit STRICT JSON for small/medium replies, but
# a map of {path: full_source_file} forces it to JSON-escape every newline,
# quote and backslash across thousands of lines of code. Past ~40 KB it makes an
# escaping slip and the whole reply fails to parse (JSONDecodeError, mid-string).
# Raising max_tokens does not help: the failure is escaping fragility, not
# truncation. A line-delimited format sidesteps escaping entirely — file bodies
# are copied verbatim between markers, so there is nothing to escape.
_FILE_BEGIN = "===FILE==="   # followed by the relative path on the same line
_FILE_END = "===ENDFILE==="

FILES_PROTOCOL = (
    "Output EVERY file using this EXACT plain-text format and NOTHING else "
    "(no markdown, no JSON, no commentary):\n"
    f"{_FILE_BEGIN} <relative/path>\n"
    "<the complete, verbatim file contents>\n"
    f"{_FILE_END}\n"
    "Repeat the block for each file. Do not escape or modify file contents in "
    "any way — emit them exactly as they should be written to disk."
)


def converse_files(system_prompt: str, user_text: str, **kwargs) -> dict:
    """Converse for a multi-file code generation and return {path: contents}.

    Uses the delimiter protocol (see FILES_PROTOCOL) instead of JSON so large
    source files need no escaping. Raises if no files are parsed, rather than
    silently returning an empty map (no quiet failure).
    """
    raw = converse(system_prompt, user_text, **kwargs)
    files = _parse_files(raw)
    if not files:
        raise RuntimeError(
            "Model returned no parseable files (expected "
            f"'{_FILE_BEGIN} <path>' blocks).")
    return files


def _parse_files(raw: str) -> dict:
    files = {}
    path = None
    body_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith(_FILE_BEGIN):
            path = stripped[len(_FILE_BEGIN):].strip()
            body_lines = []
        elif stripped == _FILE_END:
            if path:
                files[path] = "\n".join(body_lines)
            path = None
            body_lines = []
        elif path is not None:
            body_lines.append(line)
    return files


def start_kb_ingestion(kb_id: str, data_source_id: str) -> str:
    resp = _bedrock_agent.start_ingestion_job(
        knowledgeBaseId=kb_id, dataSourceId=data_source_id)
    return resp["ingestionJob"]["ingestionJobId"]
