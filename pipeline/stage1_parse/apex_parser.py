"""
Stage 1 (APEX variant) — Oracle APEX export parser  |  Oracle AI Modernization POC

Parses an Oracle APEX application export (.sql) — the APEX analog of an Oracle
Forms .fmb: one monolithic artifact bundling UI (pages/regions/items), business
logic (processes/validations/computations), and data access (SQL) together.

This proves the pipeline scales to REAL complexity: the Opportunities CRM export
is ~100k lines with 157 pages, 237 processes, 57 validations, 10 PL/SQL packages.

The APEX export DSL is a sequence of `wwv_flow_imp*.create_X( p_arg=>value, ... )`
calls. We parse each call into (type, {args}), reconstruct wwv_flow_string.join()
multi-line PL/SQL/SQL blocks, and emit the same structured JSON shape as the
Forms parser so Stages 2-4 (KB / generate / validate) consume it unchanged.

Usage:
    python apex_parser.py <app_export.sql> --out <dir>
"""

from __future__ import annotations
import argparse, json, os, re
from dataclasses import dataclass, field, asdict


# ---- tokenizer for create_X(...) calls --------------------------------------

CALL_RE = re.compile(r"(wwv_flow_imp(?:_page|_shared)?)\.(create_[a-z_]+)\s*\(",
                     re.IGNORECASE)


def _split_args(body: str) -> dict:
    """Split a create_X(...) arg body into {p_name: value}, respecting nested
    parens/quotes (so wwv_flow_string.join(...) and quoted commas don't break)."""
    args = {}
    i, n = 0, len(body)
    depth = 0
    in_str = False
    cur = []
    parts = []
    while i < n:
        c = body[i]
        if in_str:
            cur.append(c)
            if c == "'":
                # doubled '' inside string
                if i + 1 < n and body[i + 1] == "'":
                    cur.append("'"); i += 2; continue
                in_str = False
        else:
            if c == "'":
                in_str = True; cur.append(c)
            elif c == "(":
                depth += 1; cur.append(c)
            elif c == ")":
                depth -= 1; cur.append(c)
            elif c == "," and depth == 0:
                parts.append("".join(cur)); cur = []
            else:
                cur.append(c)
        i += 1
    if cur:
        parts.append("".join(cur))

    for p in parts:
        m = re.match(r"\s*(p_[a-z0-9_]+)\s*=>\s*(.*)", p, re.IGNORECASE | re.DOTALL)
        if m:
            args[m.group(1).lower()] = _clean_value(m.group(2).strip())
    return args


def _clean_value(v: str) -> str:
    """Normalize an APEX arg value: unwrap wwv_flow_string.join(...) multi-line
    blocks, strip wwv_flow_imp.id(...), unquote simple strings."""
    v = v.strip()
    # wwv_flow_string.join(wwv_flow_t_varchar2( 'a','b',... ))
    jm = re.search(r"wwv_flow_string\.join\(\s*wwv_flow_t_varchar2\((.*)\)\s*\)",
                   v, re.DOTALL | re.IGNORECASE)
    if jm:
        lines = re.findall(r"'((?:[^']|'')*)'", jm.group(1))
        return "\n".join(s.replace("''", "'") for s in lines)
    # wwv_flow_imp.id(12345)  -> the numeric id
    im = re.match(r"wwv_flow_imp\.id\((\d+)\)", v, re.IGNORECASE)
    if im:
        return im.group(1)
    # simple quoted string
    sm = re.match(r"^'((?:[^']|'')*)'$", v, re.DOTALL)
    if sm:
        return sm.group(1).replace("''", "'")
    return v


def parse_calls(sql: str):
    """Yield (owner, call_type, args_dict) for every create_X(...) call."""
    for m in CALL_RE.finditer(sql):
        owner, ctype = m.group(1), m.group(2).lower()
        # find matching close paren from m.end()-1
        i = m.end() - 1
        depth = 0
        in_str = False
        n = len(sql)
        start = i + 1
        while i < n:
            c = sql[i]
            if in_str:
                if c == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2; continue
                    in_str = False
            else:
                if c == "'":
                    in_str = True
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        body = sql[start:i]
        yield owner, ctype, _split_args(body)


# ---- build the structured model ---------------------------------------------

@dataclass
class ApexApp:
    module: str
    kind: str = "apex"
    pages: list = field(default_factory=list)
    processes: list = field(default_factory=list)   # PL/SQL logic
    validations: list = field(default_factory=list)  # business rules
    computations: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    packages: list = field(default_factory=list)
    lovs: int = 0
    stats: dict = field(default_factory=dict)


TABLE_REF_RE = re.compile(r"\b(?:from|join|into|update)\s+([a-z_][a-z0-9_]{2,})",
                          re.IGNORECASE)


def build(sql: str, module: str) -> ApexApp:
    app = ApexApp(module=module)
    pages_by_id = {}
    cur_page = None

    for owner, ctype, a in parse_calls(sql):
        if ctype == "create_page":
            cur_page = {"id": a.get("p_id"), "name": a.get("p_name") or a.get("p_step_title"),
                        "alias": a.get("p_alias")}
            if cur_page["name"] and cur_page["name"] not in ("0",):
                app.pages.append(cur_page)
                pages_by_id[cur_page["id"]] = cur_page

        elif ctype == "create_page_process":
            body = a.get("p_process_sql_clob", "")
            proc = {"name": a.get("p_process_name"),
                    "type": a.get("p_process_type"),
                    "point": a.get("p_process_point"),
                    "page": cur_page["name"] if cur_page else None,
                    "plsql": body,
                    "tables": sorted(set(t.upper() for t in TABLE_REF_RE.findall(body)))}
            # keep the ones with real logic OR native form fetch/process (data access)
            if body.strip() or (proc["type"] or "").startswith("NATIVE_FORM"):
                if not body.strip():
                    # declarative form process — record the target table
                    tgt = a.get("p_attribute_02")
                    if tgt:
                        proc["tables"] = [tgt.upper()]
                        proc["plsql"] = f"-- declarative {proc['type']} on {tgt}"
                app.processes.append(proc)

        elif ctype == "create_page_validation":
            v = a.get("p_validation", "")
            app.validations.append({
                "name": a.get("p_validation_name"),
                "type": a.get("p_validation_type"),
                "page": cur_page["name"] if cur_page else None,
                "condition": v,
                "error_message": a.get("p_error_message"),
                "tables": sorted(set(t.upper() for t in TABLE_REF_RE.findall(v)))})

        elif ctype == "create_page_computation":
            app.computations.append({
                "item": a.get("p_computation_item"),
                "type": a.get("p_computation_type"),
                "page": cur_page["name"] if cur_page else None,
                "expr": a.get("p_computation_processing") or a.get("p_compute_when")})

        elif ctype == "create_install_object":
            ot = (a.get("p_object_type") or "").upper()
            on = a.get("p_object_name")
            if on:
                if ot == "TABLE":
                    app.tables.append(on.upper())
                elif "PACKAGE" in ot:
                    app.packages.append(f"{on} ({ot})")

        elif ctype == "create_list_of_values":
            app.lovs += 1

    app.tables = sorted(set(app.tables))
    app.packages = sorted(set(app.packages))
    plsql_procs = [p for p in app.processes if p["plsql"] and not p["plsql"].startswith("-- declarative")]
    app.stats = {
        "pages": len(app.pages),
        "processes_total": len(app.processes),
        "processes_with_plsql": len(plsql_procs),
        "validations": len(app.validations),
        "computations": len(app.computations),
        "tables": len(app.tables),
        "packages": len(app.packages),
        "lovs": app.lovs,
        "source_lines": sql.count("\n") + 1,
    }
    return app


def main():
    ap = argparse.ArgumentParser(description="Parse Oracle APEX export .sql -> structured JSON")
    ap.add_argument("sqlfile")
    ap.add_argument("--out", default="apex_parsed")
    ap.add_argument("--module", default=None)
    args = ap.parse_args()

    sql = open(args.sqlfile, encoding="utf-8", errors="replace").read()
    module = args.module or os.path.splitext(os.path.basename(args.sqlfile))[0]
    app = build(sql, module)

    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, f"{module}.json")
    json.dump(asdict(app), open(out, "w"), indent=2)

    print(f"Parsed APEX app '{module}':")
    for k, v in app.stats.items():
        print(f"  {k:22s} {v}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
