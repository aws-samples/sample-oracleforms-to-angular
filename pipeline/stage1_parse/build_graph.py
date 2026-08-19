"""
Stage 1 (part 2) — Dependency graph builder  |  Oracle AI Modernization POC

Consumes the parsed-form JSON from fmb_parser.py plus the DDL schema, and emits
the cross-artifact dependency graph the modernization pipeline needs:

    Form  --NAVIGATES-->  Form           (CALL_FORM / OPEN_FORM edges)
    Form  --READS/WRITES-->  Table        (base-table + SQL references)
    Table --FK-->  Table                  (parsed from CREATE TABLE constraints)
    Trigger --USES_SEQUENCE-->  Sequence

Outputs:
    graph.json          nodes + edges (machine-readable, feeds Stage 2 KB)
    graph.md            human-readable dependency report
    graph.dot           Graphviz (render with: dot -Tpng graph.dot -o graph.png)

This is the "AI builds the dependency map first" deliverable from the deck —
the natural migration seams emerge from these edges.
"""

from __future__ import annotations

import glob
import json
import os
import re
import argparse


def parse_schema(sql_path: str) -> tuple[dict, list]:
    """Return ({table: [cols]}, [(child, parent, via) FK edges]) from DDL."""
    sql = open(sql_path, encoding="utf-8", errors="replace").read()
    tables: dict[str, list[str]] = {}
    fks: list[tuple[str, str, str]] = []

    for m in re.finditer(r"CREATE\s+TABLE\s+(\w+)\s*\((.*?)\)\s*;", sql,
                         re.IGNORECASE | re.DOTALL):
        tname = m.group(1).upper()
        body = m.group(2)
        cols = []
        for line in body.split(","):
            line = line.strip()
            cm = re.match(r"(\w+)\s+(NUMBER|VARCHAR2|DATE|CHAR|CLOB|BLOB|FLOAT|INT)",
                          line, re.IGNORECASE)
            if cm and not line.upper().startswith("CONSTRAINT"):
                cols.append(cm.group(1).upper())
        tables[tname] = cols
        # FK constraints
        for fk in re.finditer(
            r"FOREIGN\s+KEY\s*\(\s*(\w+)\s*\)\s*REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)",
            body, re.IGNORECASE,
        ):
            fks.append((tname, fk.group(2).upper(), fk.group(1).upper()))
    return tables, fks


def build(parsed_dir: str, schema_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    forms = []
    for p in sorted(glob.glob(os.path.join(parsed_dir, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        forms.append(json.load(open(p)))

    tables, fks = parse_schema(schema_path)

    nodes = {}
    edges = []

    def add_node(nid, ntype, **attrs):
        nodes[nid] = {"id": nid, "type": ntype, **attrs}

    # Table + sequence + form nodes
    for t, cols in tables.items():
        add_node(f"table:{t}", "table", columns=cols)
    for child, parent, via in fks:
        edges.append({"from": f"table:{child}", "to": f"table:{parent}",
                      "type": "FK", "via": via})

    for f in forms:
        fid = f"form:{f['module'].upper()}"
        add_node(fid, "form",
                 triggers=f["stats"]["triggers_with_logic"],
                 blocks=f["blocks"])
        # navigation edges
        for target in f["navigation"]:
            tgt = target.upper()
            edges.append({"from": fid, "to": f"form:{tgt}", "type": "NAVIGATES"})
        # table access edges (form-level)
        for t in f["tables"]:
            if t in tables:
                edges.append({"from": fid, "to": f"table:{t}", "type": "ACCESSES"})
        # trigger-level: sequences + fine-grained table refs + business rules
        for trig in f["triggers"]:
            for seq in trig["sequences"]:
                sid = f"sequence:{seq}"
                add_node(sid, "sequence")
                edges.append({"from": fid, "to": sid, "type": "USES_SEQUENCE",
                              "trigger": trig["name"]})
            for t in trig["tables"]:
                if t in tables:
                    edges.append({"from": fid, "to": f"table:{t}",
                                  "type": "ACCESSES", "trigger": trig["name"]})

    # de-dup edges
    seen = set(); uniq = []
    for e in edges:
        k = (e["from"], e["to"], e["type"], e.get("via"), e.get("trigger"))
        if k not in seen:
            seen.add(k); uniq.append(e)
    edges = uniq

    graph = {"nodes": list(nodes.values()), "edges": edges,
             "summary": {
                 "forms": sum(1 for n in nodes.values() if n["type"] == "form"),
                 "tables": len(tables),
                 "sequences": sum(1 for n in nodes.values() if n["type"] == "sequence"),
                 "fk_edges": len(fks),
                 "navigation_edges": sum(1 for e in edges if e["type"] == "NAVIGATES"),
                 "access_edges": sum(1 for e in edges if e["type"] == "ACCESSES"),
             }}
    json.dump(graph, open(os.path.join(out_dir, "graph.json"), "w"), indent=2)

    # ---- Graphviz ----
    dot = ["digraph RIMS_GPC {", '  rankdir=LR;', '  node [style=filled,fontname="Helvetica"];']
    for n in nodes.values():
        if n["type"] == "form":
            dot.append(f'  "{n["id"]}" [shape=component,fillcolor="#E8A87C",label="{n["id"].split(":")[1]}"];')
        elif n["type"] == "table":
            dot.append(f'  "{n["id"]}" [shape=cylinder,fillcolor="#85CDCA",label="{n["id"].split(":")[1]}"];')
        else:
            dot.append(f'  "{n["id"]}" [shape=oval,fillcolor="#C38D9E",label="{n["id"].split(":")[1]}"];')
    style = {"FK": 'color="#41436A",style=bold', "NAVIGATES": 'color="#E27D60"',
             "ACCESSES": 'color="#666"', "USES_SEQUENCE": 'color="#999",style=dashed'}
    for e in edges:
        lbl = e["type"] + (f'\\n{e["via"]}' if e.get("via") else "")
        dot.append(f'  "{e["from"]}" -> "{e["to"]}" [{style.get(e["type"],"")},label="{lbl}"];')
    dot.append("}")
    open(os.path.join(out_dir, "graph.dot"), "w").write("\n".join(dot))

    # ---- Markdown report ----
    md = ["# Legacy Application Dependency Map (AI-extracted)\n",
          "_Generated by Stage 1 of the AI modernization pipeline from the "
          "Oracle Forms binaries + DDL. These edges are the natural migration seams._\n",
          "## Summary\n"]
    for k, v in graph["summary"].items():
        md.append(f"- **{k.replace('_',' ').title()}:** {v}")
    md.append("\n## Navigation (Form → Form)\n")
    for e in edges:
        if e["type"] == "NAVIGATES":
            md.append(f"- `{e['from'].split(':')[1]}` → `{e['to'].split(':')[1]}`")
    md.append("\n## Data Access (Form → Table)\n")
    for e in edges:
        if e["type"] == "ACCESSES":
            via = f" _(via {e['trigger']})_" if e.get("trigger") else ""
            md.append(f"- `{e['from'].split(':')[1]}` → `{e['to'].split(':')[1]}`{via}")
    md.append("\n## Referential Integrity (Table → Table)\n")
    for e in edges:
        if e["type"] == "FK":
            md.append(f"- `{e['from'].split(':')[1]}` →(FK `{e['via']}`)→ `{e['to'].split(':')[1]}`")
    md.append("\n## Business Rules Recovered\n")
    for f in forms:
        rules = [t for t in f["triggers"]
                 if t["name"] in ("WHEN-VALIDATE-ITEM", "ON-CHECK-DELETE-MASTER",
                                  "PRE-INSERT", "ON-POPULATE-DETAILS")]
        for t in rules:
            first = next((l for l in t["plsql"].splitlines()
                          if ":=" in l or "Message" in l or "NEXTVAL" in l.upper()
                          or "Query_Master" in l), t["plsql"].splitlines()[0] if t["plsql"] else "")
            md.append(f"- **{f['module']} / {t['name']}**: `{first.strip()[:90]}`")
    open(os.path.join(out_dir, "graph.md"), "w").write("\n".join(md))

    print(json.dumps(graph["summary"], indent=2))
    print(f"\nWrote graph.json, graph.dot, graph.md -> {out_dir}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", default="stage1_parse/parsed")
    ap.add_argument("--schema", default="forms/tables.SQL")
    ap.add_argument("--out", default="stage1_parse/graph")
    a = ap.parse_args()
    build(a.parsed, a.schema, a.out)
