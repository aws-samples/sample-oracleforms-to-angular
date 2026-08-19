"""IngestPLSQL — extract PL/SQL source, dependency graph and argument metadata.

Connects to Oracle XE 21c (thin-mode `oracledb`, no Instant Client) and pulls
from the data-dictionary views ONLY — schema/metadata, never production rows:
  * ALL_SOURCE       -> full PL/SQL text per object
  * ALL_DEPENDENCIES -> dependency edges (the call/reference graph)
  * ALL_ARGUMENTS    -> procedure/function signatures

Input : { "run_id": "...", "schemas": ["APP_DATA","HR"] (optional) }
Output: { "plsql_corpus_key", "dependency_graph_key", "args_metadata_key",
          "object_count", "edge_count" }
"""
import os

import time

import oracledb

from common.aws_helpers import get_secret_json, s3_put_json

ORACLE_SECRET_ARN = os.environ["ORACLE_SECRET_ARN"]
DEFAULT_SCHEMAS = ["APP_DATA", "HR"]

# A VPC Lambda's ENI is still being wired up during a cold start, so the first
# outbound socket connect can transiently fail with OSError [Errno 16] EBUSY
# (surfaced by oracledb as DPY-6005). The network path itself is fine, so a
# short bounded retry with backoff clears it without masking a real outage.
_CONNECT_ATTEMPTS = 5
_CONNECT_BACKOFF_S = 3


def _connect():
    s = get_secret_json(ORACLE_SECRET_ARN)
    dsn = oracledb.makedsn(s["host"], int(s.get("port", 1521)),
                           service_name=s.get("service", "XEPDB1"))
    last_err = None
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            # Connect as the admin/app user; must have read on the ALL_* views.
            return oracledb.connect(
                user=s["username"], password=s["password"], dsn=dsn)
        except (oracledb.OperationalError, OSError) as err:
            last_err = err
            if attempt == _CONNECT_ATTEMPTS:
                break
            print(f"oracle connect attempt {attempt} failed "
                  f"({err}); retrying in {_CONNECT_BACKOFF_S}s")
            time.sleep(_CONNECT_BACKOFF_S)
    raise last_err


def _in_list(schemas):
    # Build a bind-safe IN (...) clause.
    binds = {f"s{i}": s for i, s in enumerate(schemas)}
    placeholders = ", ".join(f":{k}" for k in binds)
    return placeholders, binds


def handler(event, _context):
    run_id = event["run_id"]
    schemas = event.get("schemas", DEFAULT_SCHEMAS)
    placeholders, binds = _in_list(schemas)

    conn = _connect()
    try:
        cur = conn.cursor()

        # --- ALL_SOURCE: reconstruct each object's source, ordered by line ---
        cur.execute(
            "SELECT owner, name, type, line, text FROM all_source "  # nosec B608 - parameterized: {placeholders} is a bind-variable list (:0,:1,...); schema values pass via `binds`, never string-interpolated
            f"WHERE owner IN ({placeholders}) "
            "ORDER BY owner, name, type, line", binds)
        corpus = {}
        for owner, name, otype, _line, text in cur:
            key = f"{owner}.{name}:{otype}"
            corpus.setdefault(key, {"owner": owner, "name": name,
                                    "type": otype, "source": ""})
            corpus[key]["source"] += text
        corpus_list = list(corpus.values())

        # --- ALL_DEPENDENCIES: the reference/call graph -------------------
        cur.execute(
            "SELECT owner, name, type, referenced_owner, referenced_name, "  # nosec B608 - parameterized: {placeholders} is a bind-variable list; schema values pass via `binds`, never string-interpolated
            "referenced_type, dependency_type FROM all_dependencies "
            f"WHERE owner IN ({placeholders})", binds)
        edges = [
            {"owner": o, "name": n, "type": t,
             "ref_owner": ro, "ref_name": rn, "ref_type": rt,
             "dependency_type": dt}
            for (o, n, t, ro, rn, rt, dt) in cur
        ]

        # --- ALL_ARGUMENTS: procedure/function signatures ----------------
        cur.execute(
            "SELECT owner, package_name, object_name, argument_name, "  # nosec B608 - parameterized: {placeholders} is a bind-variable list; schema values pass via `binds`, never string-interpolated
            "position, data_type, in_out, defaulted FROM all_arguments "
            f"WHERE owner IN ({placeholders}) "
            "ORDER BY owner, package_name, object_name, position", binds)
        args = [
            {"owner": o, "package": pkg, "object": obj, "arg": arg,
             "position": pos, "data_type": dt, "in_out": io, "defaulted": defd}
            for (o, pkg, obj, arg, pos, dt, io, defd) in cur
        ]
    finally:
        conn.close()

    corpus_key = s3_put_json(f"pipeline/{run_id}/plsql_corpus.json", corpus_list)
    graph_key = s3_put_json(f"pipeline/{run_id}/dependency_graph.json", edges)
    args_key = s3_put_json(f"pipeline/{run_id}/args_metadata.json", args)

    return {
        "plsql_corpus_key": corpus_key,
        "dependency_graph_key": graph_key,
        "args_metadata_key": args_key,
        "object_count": len(corpus_list),
        "edge_count": len(edges),
        "schemas": schemas,
    }
