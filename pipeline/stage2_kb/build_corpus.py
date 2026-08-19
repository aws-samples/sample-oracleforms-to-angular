"""
Stage 2 (part 1) — Build the RAG corpus  |  Oracle AI Modernization POC

Turns the Stage 1 structured output into clean, self-contained Markdown documents
optimised for retrieval. Each document is a coherent chunk of knowledge a
developer would ask about, so Bedrock KB retrieval returns tight, citable context:

  - one doc per Form  (its triggers + reconstructed PL/SQL + what it touches)
  - one doc for the dependency graph (navigation, data access, FK)
  - one doc for the recovered business rules (the tacit-knowledge capture)
  - one doc for the data schema (tables, columns, keys)

Output: stage2_kb/corpus/*.md  (uploaded to S3 as the KB data source)
"""

from __future__ import annotations
import glob, json, os

HERE = os.path.dirname(__file__)
PARSED = os.path.join(HERE, "..", "stage1_parse", "parsed")
GRAPH = os.path.join(HERE, "..", "stage1_parse", "graph", "graph.json")
SCHEMA = os.path.join(HERE, "..", "forms", "tables.SQL")
OUT = os.path.join(HERE, "corpus")

KEY_RULES = {"WHEN-VALIDATE-ITEM", "ON-CHECK-DELETE-MASTER", "PRE-INSERT",
             "ON-POPULATE-DETAILS", "POST-INSERT", "WHEN-VALIDATE-RECORD"}


def form_doc(f: dict) -> str:
    m = f["module"]
    lines = [f"# Form: {m}",
             "",
             f"Source: `{m}.fmb` (Oracle Forms, object store `{f['magic']}`). "
             f"This form bundles UI, business logic (triggers), and data access.",
             "",
             f"- Blocks: {', '.join(f['blocks']) or 'n/a'}",
             f"- Tables accessed: {', '.join(f['tables']) or 'n/a'}",
             f"- Navigates to: {', '.join(f['navigation']) or 'n/a'}",
             f"- Triggers with logic: {f['stats']['triggers_with_logic']}",
             "",
             "## Triggers and PL/SQL logic", ""]
    for t in f["triggers"]:
        body = t["plsql"].strip()
        if not body:
            continue
        meta = []
        if t["tables"]: meta.append(f"tables={t['tables']}")
        if t["sequences"]: meta.append(f"sequences={t['sequences']}")
        if t["items"]: meta.append(f"items={t['items']}")
        if t["builtins"]: meta.append(f"builtins={t['builtins']}")
        lines.append(f"### {t['name']} on {t['scope']}")
        if meta:
            lines.append(f"_{'; '.join(meta)}_")
        lines.append("```plsql")
        lines.append(body)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def rules_doc(forms: list[dict]) -> str:
    lines = ["# Business Rules Recovered from the Legacy Oracle Application",
             "",
             "These are the tacit business rules extracted from the legacy Oracle "
             "Forms triggers by the AI modernization pipeline. They are the "
             "knowledge that must be preserved during migration.", ""]
    for f in forms:
        for t in f["triggers"]:
            if t["name"] not in KEY_RULES:
                continue
            body = t["plsql"].strip()
            if not body:
                continue
            # human summary of the intent
            intent = ""
            b = body.upper()
            if "NEXTVAL" in b:
                intent = "Assigns a surrogate primary key from a database sequence before insert."
            elif ":=" in body and "*" in body:
                intent = "Computes a derived/total field from other item values."
            elif "MESSAGE(" in b and "RAISE" in b:
                intent = "Enforces a referential/validation rule and blocks the operation on failure."
            elif "QUERY_MASTER_DETAILS" in b or "FIND_RELATION" in b:
                intent = "Coordinates a master-detail relationship (populates child rows for the current master)."
            lines.append(f"## {f['module']} — {t['name']} ({t['scope']})")
            if intent:
                lines.append(f"**Intent:** {intent}")
            lines.append("```plsql")
            lines.append(body)
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def graph_doc(g: dict) -> str:
    lines = ["# Legacy Application Dependency Map",
             "",
             "Cross-artifact dependency graph extracted from the Forms binaries and "
             "the Oracle DDL. These edges are the natural migration seams.", "",
             "## Summary"]
    for k, v in g["summary"].items():
        lines.append(f"- {k.replace('_',' ').title()}: {v}")
    lines += ["", "## Form navigation (which form opens which)"]
    for e in g["edges"]:
        if e["type"] == "NAVIGATES":
            lines.append(f"- {e['from'].split(':')[1]} opens {e['to'].split(':')[1]}")
    lines += ["", "## Form data access (which form reads/writes which table)"]
    for e in g["edges"]:
        if e["type"] == "ACCESSES":
            via = f" (via trigger {e['trigger']})" if e.get("trigger") else ""
            lines.append(f"- {e['from'].split(':')[1]} accesses {e['to'].split(':')[1]}{via}")
    lines += ["", "## Referential integrity (foreign keys)"]
    for e in g["edges"]:
        if e["type"] == "FK":
            lines.append(f"- {e['from'].split(':')[1]}.{e['via']} references {e['to'].split(':')[1]}")
    lines += ["", "## Sequences used"]
    for e in g["edges"]:
        if e["type"] == "USES_SEQUENCE":
            lines.append(f"- {e['from'].split(':')[1]} uses sequence {e['to'].split(':')[1]} (trigger {e.get('trigger')})")
    return "\n".join(lines)


def schema_doc() -> str:
    sql = open(SCHEMA, encoding="utf-8", errors="replace").read()
    return ("# Data Schema (Oracle DDL)\n\n"
            "The database schema underlying the Forms application. No production "
            "row data — schema/metadata only.\n\n```sql\n" + sql.strip() + "\n```\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    forms = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(PARSED, "*.json")))
             if not os.path.basename(p).startswith("_")]
    g = json.load(open(GRAPH))

    written = []
    for f in forms:
        p = os.path.join(OUT, f"form_{f['module']}.md")
        open(p, "w").write(form_doc(f)); written.append(p)
    for name, content in [("business_rules.md", rules_doc(forms)),
                          ("dependency_map.md", graph_doc(g)),
                          ("data_schema.md", schema_doc())]:
        p = os.path.join(OUT, name)
        open(p, "w").write(content); written.append(p)

    print(f"Wrote {len(written)} corpus documents -> {OUT}/")
    for p in written:
        print(f"  {os.path.basename(p):28s} {os.path.getsize(p):>6d} bytes")


if __name__ == "__main__":
    main()
