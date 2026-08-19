"""
Stage 1 — Oracle Forms (.fmb) parser  |  Oracle AI Modernization Pipeline POC

Pure-Python parser: reads an Oracle Forms .fmb binary directly and extracts the
structured artifacts an AI modernization pipeline needs — triggers and their
PL/SQL bodies, blocks, items, LOVs, master-detail relations, and outbound
CALL_FORM navigation. No Oracle runtime, no JDAPI, no X11 — runs anywhere
(laptop, Lambda, CodeBuild), which matches the target AWS-native architecture.

Design note (grounded in real inspection of the sample .fmb files):
  The .fmb object store interleaves printable "runs" with binary control bytes.
  A trigger's PL/SQL body (BEGIN ... END;) appears in the stream immediately
  FOLLOWED by its trigger-name marker, e.g.  PRE-INSERT (ORDERS).
  We reconstruct runs with their byte offsets, then associate each trigger-name
  marker with the nearest preceding BEGIN..END; block. This is robust across all
  six sample forms (Forms 10g/12c object store, magic "ROS.<version>").

Usage:
    python fmb_parser.py <form.fmb> [<form2.fmb> ...] --out <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field, asdict


# ---- printable-run extraction ------------------------------------------------

def extract_runs(data: bytes, min_len: int = 3) -> list[tuple[int, str]]:
    """Return (offset, text) for every printable run in the binary."""
    runs: list[tuple[int, str]] = []
    cur = bytearray()
    start = 0
    for i, b in enumerate(data):
        if b in (9, 10, 13) or 32 <= b <= 126:
            if not cur:
                start = i
            cur.append(b)
        else:
            if len(cur) >= min_len:
                runs.append((start, cur.decode("latin1")))
            cur = bytearray()
    if len(cur) >= min_len:
        runs.append((start, cur.decode("latin1")))
    return runs


# ---- structural markers ------------------------------------------------------

TRIGGER_RE = re.compile(
    # tolerate a stray object-store byte glued to the front (e.g. ")WHEN-...")
    r"^[)#\s]?((?:PRE|POST|WHEN|ON|KEY)-[A-Z-]+)\s*\(([^)]+)\)\s*$"
)
# base-table / column references and navigation
CALL_FORM_RE = re.compile(r"CALL_FORM\('([^']+)'\)", re.IGNORECASE)
OPEN_FORM_RE = re.compile(r"(?:OPEN_FORM|NEW_FORM)\('([^']+)'\)", re.IGNORECASE)
TABLE_REF_RE = re.compile(r"\bFROM\s+([A-Z_][A-Z0-9_]{2,})", re.IGNORECASE)
INTO_REF_RE = re.compile(r"\bINTO\s+(:[A-Z_][A-Z0-9_.]*)", re.IGNORECASE)
ITEM_REF_RE = re.compile(r":([A-Z_][A-Z0-9_]*)\.([A-Z_][A-Z0-9_]*)")
SEQ_RE = re.compile(r"([A-Z_][A-Z0-9_]*)\.NEXTVAL", re.IGNORECASE)


@dataclass
class Trigger:
    name: str            # e.g. PRE-INSERT
    scope: str           # e.g. ORDERS  /  Form  /  BLOCK7.ITEM12
    plsql: str           # reconstructed body
    tables: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    sequences: list[str] = field(default_factory=list)
    calls_form: list[str] = field(default_factory=list)
    builtins: list[str] = field(default_factory=list)


@dataclass
class ParsedForm:
    module: str
    magic: str
    triggers: list[dict] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    lovs: int = 0
    relations: int = 0
    navigation: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


FORMS_BUILTINS = [
    "COMMIT_FORM", "GO_ITEM", "GO_BLOCK", "EXECUTE_QUERY", "CLEAR_FORM",
    "MESSAGE", "RAISE", "CALL_FORM", "OPEN_FORM", "NEW_FORM", "SET_ITEM_PROPERTY",
    "SHOW_LOV", "NEXT_RECORD", "PREVIOUS_RECORD", "CLEAR_BLOCK", "POST",
    "FORM_SUCCESS", "FORM_TRIGGER_FAILURE", "CHECK_PACKAGE_FAILURE",
]


def _clean_plsql(text: str) -> str:
    """Trim the object-store noise around a reconstructed BEGIN..END; block."""
    # Drop a leading stray marker char sometimes glued to BEGIN (e.g. "VBEGIN", "9SELECT")
    text = re.sub(r"^[^A-Za-z-]*(?=BEGIN|DECLARE|SELECT|IF)", "", text.strip())
    # Collapse trailing object-store token lists like  "FORM_SUCCESS"NOT"...
    return text.strip()


# A line is object-store noise (string table / property blob) rather than PL/SQL
# when it is a run of quoted identifiers or contains no PL/SQL grammar.
NOISE_RE = re.compile(r'^[\s"]*([A-Z0-9_$<>]+"?)(\s*"?[A-Z0-9_$<>./]+"?){2,}\s*$')
CODE_HINT_RE = re.compile(
    r"\b(BEGIN|DECLARE|END|END;|IF|THEN|ELSE|ELSIF|LOOP|SELECT|INSERT|UPDATE|"
    r"DELETE|COMMIT|RAISE|MESSAGE|COMMIT_FORM|GO_ITEM|GO_BLOCK|NEXT_RECORD|"
    r"PREVIOUS_RECORD|CREATE_RECORD|EXECUTE_QUERY|CLEAR_FORM|CALL_FORM|:)",
    re.IGNORECASE,
)


def _reconstruct_body(window_runs: list[str]) -> str:
    """Given the printable runs in the byte-window that precedes a trigger-name
    marker, reconstruct the trigger's PL/SQL body (the LAST BEGIN/DECLARE..END;
    in the window), discarding object-store string-table noise."""
    text = "\n".join(r.rstrip() for r in window_runs)
    # find the last BEGIN or DECLARE that opens the trigger body
    starts = [m.start() for m in re.finditer(r"\b(DECLARE|BEGIN)\b", text, re.I)]
    if not starts:
        return ""
    start = starts[-1]
    # Walk tokens from the body start, tracking block depth so we close on the
    # matching END; rather than a trailing duplicate the object store appends.
    seg = text[start:]
    depth = 0
    end_pos = None
    for m in re.finditer(r"\b(BEGIN|DECLARE|IF|LOOP|CASE|END\s*;?)\b", seg, re.I):
        tok = m.group(1).upper().replace(" ", "")
        if tok in ("BEGIN", "IF", "LOOP", "CASE"):
            depth += 1
        elif tok.startswith("END"):
            depth -= 1
            if depth <= 0:
                end_pos = m.end()
                break
    body = seg[:end_pos] if end_pos else seg
    # scrub trailing/inline object-store noise lines
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        if NOISE_RE.match(s) and not CODE_HINT_RE.search(s):
            continue
        # strip a trailing string-table blob glued to a code line: ... END; "TOK"TOK"
        s = re.sub(r'\s+"[A-Z0-9_$<>][A-Z0-9_$<>".\s]*$', "", s)
        # strip a stray leading control char glued to a keyword (jBEGIN, 9SELECT, VBEGIN)
        s = re.sub(r"^[^A-Za-z(:-]*([a-z])?(?=BEGIN|DECLARE|SELECT|IF|END|:)", "", s)
        # drop pure Forms-generated comment separators
        if s in ("--",) or re.fullmatch(r"--\s*(Begin|End).*", s, re.I):
            continue
        lines.append(s)
    cleaned = "\n".join(lines).strip()
    # collapse an object-store duplicate opener (BEGIN\nBEGIN -> BEGIN)
    cleaned = re.sub(r"^(BEGIN|DECLARE)\s*\n(?=BEGIN\b)", "", cleaned, flags=re.I)
    # ensure the body terminates with a single END;
    cleaned = re.sub(r"\bEND\s*;?\s*$", "END;", cleaned, flags=re.I)
    return cleaned


def parse_fmb(path: str) -> ParsedForm:
    data = open(path, "rb").read()
    magic = data[:16].decode("latin1", errors="replace").split("\x00")[0]
    runs = extract_runs(data)

    module = os.path.splitext(os.path.basename(path))[0]
    pf = ParsedForm(module=module, magic=magic)

    # Collect trigger-name markers with offsets (in stream order)
    markers: list[tuple[int, str, str]] = []
    for off, s in runs:
        m = TRIGGER_RE.match(s.strip())
        if m:
            markers.append((off, m.group(1), m.group(2)))

    # For each marker, the body is the runs in the window from the previous
    # marker up to this marker (body precedes its name in the object store).
    prev_off = 0
    for idx, (off, name, scope) in enumerate(markers):
        window = [s for o, s in runs if prev_off <= o < off]
        prev_off = off
        body = _reconstruct_body(window)

        norm = re.sub(r"\s+", " ", body).upper().strip()
        if not body or norm in ("BEGIN END;", "END;", "BEGIN"):
            continue  # empty internal placeholder trigger — skip

        trig = Trigger(name=name, scope=scope, plsql=body)
        trig.tables = sorted(set(t.upper() for t in TABLE_REF_RE.findall(body)))
        trig.items = sorted(set(f"{a}.{b}".upper() for a, b in ITEM_REF_RE.findall(body)))
        trig.sequences = sorted(set(s.upper() for s in SEQ_RE.findall(body)))
        trig.calls_form = [re.split(r"[\\/]", c)[-1].upper()
                           for c in CALL_FORM_RE.findall(body)]
        trig.builtins = sorted({b for b in FORMS_BUILTINS if re.search(rf"\b{b}\b", body, re.I)})
        pf.triggers.append(asdict(trig))

    # Blocks referenced
    pf.blocks = sorted({sc.split(".")[0].upper() for _, _, sc in markers
                        if sc.upper() not in ("FORM", "INTRNL")})
    # Navigation (form-wide, from raw runs so we catch it even outside triggers)
    nav = set()
    for _, s in runs:
        for c in CALL_FORM_RE.findall(s) + OPEN_FORM_RE.findall(s):
            base = re.split(r"[\\/]", c)[-1]  # handle Windows backslash paths
            nav.add(base.upper().replace(".FMX", "").replace(".FMB", ""))
    pf.navigation = sorted(nav)
    # Tables (form-wide)
    pf.tables = sorted({t.upper() for _, s in runs for t in TABLE_REF_RE.findall(s)
                        if t.upper() not in ("DUAL",)})
    # Counts from raw string scan (structural fidelity)
    raw = "\n".join(s for _, s in runs)
    pf.lovs = len(re.findall(r"\bLOV\b", raw))
    pf.relations = raw.upper().count("RELATION")
    pf.stats = {
        "triggers_with_logic": len(pf.triggers),
        "trigger_markers_total": len(markers),
        "blocks": len(pf.blocks),
        "tables_referenced": len(pf.tables),
        "navigation_edges": len(pf.navigation),
        "lov_markers": pf.lovs,
        "file_bytes": len(data),
    }
    return pf


def main():
    ap = argparse.ArgumentParser(description="Parse Oracle Forms .fmb → structured JSON")
    ap.add_argument("forms", nargs="+", help=".fmb files")
    ap.add_argument("--out", default="parsed", help="output directory")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    summary = []
    for p in args.forms:
        pf = parse_fmb(p)
        out = os.path.join(args.out, f"{pf.module}.json")
        with open(out, "w") as f:
            json.dump(asdict(pf), f, indent=2)
        print(f"  {pf.module:20s} magic={pf.magic:12s} "
              f"triggers={pf.stats['triggers_with_logic']:2d}  "
              f"blocks={pf.stats['blocks']:2d}  "
              f"tables={pf.stats['tables_referenced']:2d}  "
              f"nav={pf.stats['navigation_edges']:2d}  -> {out}")
        summary.append(asdict(pf))

    with open(os.path.join(args.out, "_all_forms.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nParsed {len(summary)} forms -> {args.out}/")


if __name__ == "__main__":
    main()
