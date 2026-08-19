"""
Stage 1+2 (APEX) — dependency graph + RAG corpus for the parsed APEX app.

Consumes stage1_parse/apex_parsed/<app>.json and emits:
  - apex_graph/graph.{json,dot,md}   : Page->Table, Page->Package, Table refs
  - apex_corpus/*.md                 : retrieval-optimized docs for the KB

Mirrors build_graph.py + build_corpus.py but for the APEX structure.
"""
from __future__ import annotations
import argparse, json, os, re


def build_graph(app: dict, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    nodes, edges = {}, []

    def node(nid, ntype, **kw): nodes[nid] = {"id": nid, "type": ntype, **kw}

    for t in app["tables"]:
        node(f"table:{t}", "table")
    for p in app["packages"]:
        node(f"package:{p}", "package")
    for pg in app["pages"]:
        node(f"page:{pg['name']}", "page")

    # page -> table (via processes & validations)
    def add_access(page, tables, kind):
        for t in tables:
            if f"table:{t}" in nodes and page:
                edges.append({"from": f"page:{page}", "to": f"table:{t}",
                              "type": "ACCESSES", "via": kind})

    for pr in app["processes"]:
        add_access(pr.get("page"), pr.get("tables", []), pr.get("name", "process"))
        # package calls inside plsql
        for pkg in app["packages"]:
            pname = pkg.split(" ")[0]
            if pr.get("plsql") and re.search(rf"\b{re.escape(pname)}\b", pr["plsql"], re.I):
                if pr.get("page"):
                    edges.append({"from": f"page:{pr['page']}", "to": f"package:{pkg}",
                                  "type": "CALLS", "via": pr.get("name")})
    for v in app["validations"]:
        add_access(v.get("page"), v.get("tables", []), v.get("name", "validation"))

    # de-dup
    seen, uniq = set(), []
    for e in edges:
        k = (e["from"], e["to"], e["type"])
        if k not in seen:
            seen.add(k); uniq.append(e)
    edges = uniq

    summary = {"pages": sum(1 for n in nodes.values() if n["type"] == "page"),
               "tables": len(app["tables"]), "packages": len(app["packages"]),
               "access_edges": sum(1 for e in edges if e["type"] == "ACCESSES"),
               "call_edges": sum(1 for e in edges if e["type"] == "CALLS")}
    json.dump({"nodes": list(nodes.values()), "edges": edges, "summary": summary},
              open(os.path.join(out_dir, "graph.json"), "w"), indent=2)

    md = ["# APEX Opportunities CRM — Dependency Map (AI-extracted)\n",
          "Cross-artifact dependency graph from the APEX export. These edges are "
          "the migration seams.\n", "## Summary"]
    for k, v in summary.items():
        md.append(f"- {k.replace('_',' ').title()}: {v}")
    md.append("\n## Pages that call PL/SQL packages")
    for e in edges:
        if e["type"] == "CALLS":
            md.append(f"- `{e['from'].split(':')[1]}` calls `{e['to'].split(':')[1]}` (via {e.get('via')})")
    open(os.path.join(out_dir, "graph.md"), "w").write("\n".join(md))
    print(json.dumps(summary, indent=2))
    return summary


def build_corpus(app: dict, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    written = []

    # overview doc
    ov = [f"# APEX Application: {app['module']}", "",
          "A real Oracle APEX application export (sales-opportunity CRM). Like an "
          "Oracle Forms .fmb, it bundles UI (pages), business logic (processes, "
          "validations, computations), and data access (SQL) in one artifact.", "",
          "## Scale"]
    for k, v in app["stats"].items():
        ov.append(f"- {k.replace('_',' ').title()}: {v}")
    ov.append("\n## Tables\n" + ", ".join(app["tables"]))
    ov.append("\n## PL/SQL Packages\n" + "\n".join(f"- {p}" for p in app["packages"]))
    _w(out_dir, "apex_overview.md", "\n".join(ov), written)

    # business rules (validations) doc
    br = ["# Business Rules — Validations (APEX Opportunities CRM)", "",
          "Validation rules recovered from the APEX export. Each is a rule the "
          "modern system must preserve.", ""]
    for v in app["validations"]:
        br.append(f"## {v['name']}  ({v['type']}) — page: {v['page']}")
        if v.get("error_message"):
            br.append(f"**Error message:** {v['error_message']}")
        if v.get("condition"):
            br.append("```sql\n" + v["condition"].strip() + "\n```")
        br.append("")
    _w(out_dir, "apex_business_rules.md", "\n".join(br), written)

    # PL/SQL processes doc
    pr = ["# PL/SQL Processes (APEX Opportunities CRM)", "",
          "Server-side PL/SQL logic recovered from the APEX processes.", ""]
    for p in app["processes"]:
        if p["plsql"] and not p["plsql"].startswith("-- declarative"):
            pr.append(f"## {p['name']}  [{p['type']} @ {p['point']}] — page: {p['page']}")
            if p["tables"]:
                pr.append(f"_tables: {p['tables']}_")
            pr.append("```plsql\n" + p["plsql"].strip() + "\n```")
            pr.append("")
    _w(out_dir, "apex_processes.md", "\n".join(pr), written)

    # pages + data access
    pg = ["# Pages and Data Access (APEX Opportunities CRM)", ""]
    for page in app["pages"]:
        pg.append(f"- Page: {page['name']}" + (f" (alias {page['alias']})" if page.get("alias") else ""))
    _w(out_dir, "apex_pages.md", "\n".join(pg), written)

    print(f"corpus: {len(written)} docs -> {out_dir}/")
    return written


def _w(d, name, content, acc):
    p = os.path.join(d, name)
    open(p, "w").write(content)
    acc.append(p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", default="stage1_parse/apex_parsed/opportunities_crm.json")
    ap.add_argument("--graph_out", default="stage1_parse/apex_graph")
    ap.add_argument("--corpus_out", default="stage2_kb/apex_corpus")
    a = ap.parse_args()
    app = json.load(open(a.parsed))
    build_graph(app, a.graph_out)
    build_corpus(app, a.corpus_out)
