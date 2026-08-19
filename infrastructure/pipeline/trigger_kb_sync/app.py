"""TriggerKBSync — kick off a Bedrock Knowledge Base ingestion job so all the
pipeline artifacts (Forms XML, PL/SQL source, analysis, generated code) become
searchable for the developer Q&A demo.

Input : environment KB_ID + KB_DATA_SOURCE_ID (set by PipelineStack).
Output: { "kb_ingestion_job_id": "..." }

Fire-and-return: ingestion is asynchronous (5-10 min); we do not block on it.
"""
import os

from common.aws_helpers import start_kb_ingestion

KB_ID = os.environ["KB_ID"]
KB_DATA_SOURCE_ID = os.environ["KB_DATA_SOURCE_ID"]


def handler(event, _context):
    job_id = start_kb_ingestion(KB_ID, KB_DATA_SOURCE_ID)
    return {"kb_ingestion_job_id": job_id, "knowledge_base_id": KB_ID}
