"""
Stage 5 — Live shadow-mode: legacy Oracle Forms ORDERS module vs the migrated .NET API.

Proves behavioural equivalence for the migrated ORDERS master-detail form by
running the SAME operations through two INDEPENDENT paths and diffing every
outcome:

  LEGACY oracle : the exact PL/SQL the form's triggers execute — direct SQL
                  inserts (PRE-INSERT sequences, the line-freeze and stock DB
                  triggers fire) and pkg_pricing / pkg_orders calls — executed
                  BY ORACLE ITSELF via sqlplus. Not a re-implementation.
  MODERN system : the live migrated .NET OrdersController, hit over HTTP
                  (POST /commit, GET /price, GET /totals, POST /status, ...).

Scenarios: per-product effective pricing, order economics (volume tiers, GST/
QST, cash rounding), create-with-items, the full Open->Confirmed->Ready->Paid
lifecycle, and all four business-rule guards (ORA-20001..-20004) — the guard
cases must fail on BOTH sides with the SAME error code.

Run on any host with a sqlplus path to the application schema and HTTPS access
to the deployed API:

  ORACLE_CONN='app_data/<pw>@//<db-host>:1521/<service>' \
  SQLPLUS_CMD='sqlplus'                # or: docker exec -i <container> sqlplus
  API_BASE='https://<cloudfront-domain>/api/orders' \
  python3 shadow_orders.py

Output: SHADOW_RESULTS_ORDERS.md + console table. Exit code = number of
mismatches. Creates two throwaway orders (one per path) that end their life
Paid — consistent, package-audited data.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess  # nosec B404 - sqlplus is the sanctioned SQL path for this sample
import sys
import urllib.request
import urllib.error

CONN = os.environ["ORACLE_CONN"]
SQLPLUS = os.environ.get("SQLPLUS_CMD", "sqlplus")
API = os.environ["API_BASE"].rstrip("/")

TOL = 0.005  # money comparisons: values are ROUNDed on both sides

results: list[tuple[str, str, str, bool]] = []  # (case, legacy, modern, match)


def record(case: str, legacy, modern, match: bool) -> None:
    results.append((case, str(legacy), str(modern), match))
    print(f"  {'MATCH ' if match else 'DIFF !'} {case:44s} legacy={legacy}  modern={modern}")


# ---- the two independent paths ----------------------------------------------

def sql(script: str) -> str:
    """Run a sqlplus script against the application schema, return raw output."""
    full = ("SET PAGESIZE 0 FEEDBACK OFF HEADING OFF VERIFY OFF SERVEROUTPUT ON\n"
            "WHENEVER SQLERROR CONTINUE\n" + script + "\nEXIT\n")
    proc = subprocess.run(  # nosec B603 - command from operator env, no shell
        shlex.split(SQLPLUS) + ["-s", CONN],
        input=full, capture_output=True, text=True, timeout=120)
    return proc.stdout


def sql_tags(script: str) -> dict[str, str]:
    """Extract TAG|value lines emitted by the script."""
    out = sql(script)
    tags: dict[str, str] = {}
    for line in out.splitlines():
        if "|" in line:
            k, _, v = line.strip().partition("|")
            tags[k] = v
    return tags


def sql_error_code(script: str) -> int | None:
    """Run a script expected to raise; return the ORA-2000x code."""
    m = re.search(r"ORA-(20\d{3})", sql(script))
    return int(m.group(1)) if m else None


def api(method: str, path: str, body: dict | None = None):
    """(status_code, parsed_json) for a call to the modern API."""
    req = urllib.request.Request(API + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:  # nosec B310 - API_BASE is operator-supplied https
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read() or b"null")
        except ValueError:
            return err.code, None


def money_eq(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= TOL
    except (TypeError, ValueError):
        return False


# ---- scenarios ---------------------------------------------------------------

def s1_pricing() -> None:
    print("\nS1 — effective line pricing (pkg_pricing.line_unit_price), every product")
    tags = sql_tags(
        "SELECT 'P'||product_id||'|'||pkg_pricing.line_unit_price(product_id) "
        "FROM products ORDER BY product_id;")
    for key, legacy_price in sorted(tags.items(), key=lambda kv: int(kv[0][1:])):
        pid = key[1:]
        status, body = api("GET", f"/price/{pid}")
        modern_price = body.get("unitPrice") if status == 200 and body else None
        record(f"price product {pid}", legacy_price, modern_price,
               money_eq(legacy_price, modern_price))


def s2_totals(extra_ids: list[int]) -> None:
    print("\nS2 — order economics (pkg_pricing.order_totals): subtotal/discount/GST/QST/rounded total")
    tags = sql_tags(
        "SELECT 'OID|'||LISTAGG(order_id, ',') WITHIN GROUP (ORDER BY order_id) FROM ("
        "SELECT DISTINCT order_id FROM orders JOIN order_items ON order_id_fk = order_id "
        "ORDER BY order_id FETCH FIRST 8 ROWS ONLY);")
    ids = [int(x) for x in tags.get("OID", "").split(",") if x] + extra_ids
    for oid in ids:
        legacy = sql_tags(
            "VAR s NUMBER\nVAR d NUMBER\nVAR g NUMBER\nVAR q NUMBER\nVAR t NUMBER\n"
            f"BEGIN pkg_pricing.order_totals({oid}, :s, :d, :g, :q, :t); END;\n/\n"
            "SELECT 'T|'||:s||'/'||:d||'/'||:g||'/'||:q||'/'||:t FROM DUAL;")
        status, body = api("GET", f"/{oid}/totals")
        if status != 200 or "T" not in legacy:
            record(f"totals order {oid}", legacy.get("T"), f"http {status}", False)
            continue
        lvals = legacy["T"].split("/")
        mvals = [body.get(k) for k in ("subtotal", "discount", "gst", "qst", "total")]
        ok = all(money_eq(a, b) for a, b in zip(lvals, mvals))
        record(f"totals order {oid}", legacy["T"], "/".join(str(v) for v in mvals), ok)


def s3_create() -> tuple[int, int]:
    print("\nS3 — create order + 6x product 1 (volume tier 1), each side via its native path")
    # LEGACY: exactly what the form's SAVE does (PRE-INSERT sequences, triggers fire)
    legacy = sql_tags(
        "VAR oid NUMBER\n"
        "DECLARE v_p NUMBER; BEGIN\n"
        "  SELECT order_seq.NEXTVAL INTO :oid FROM DUAL;\n"
        "  v_p := pkg_pricing.line_unit_price(1);\n"
        "  INSERT INTO Orders (Order_ID, Order_Data, Customer_ID, Employee_ID, Table_Number, Order_Type, Statues)\n"
        "  VALUES (:oid, SYSDATE, 2, 3, 7, 'Dine-in', 'Open');\n"
        "  INSERT INTO Order_Items (Item_ID, Order_id_fk, Product_id_fk, Quantity, Unit_Price, Total_Price)\n"
        "  VALUES (item_seq.NEXTVAL, :oid, 1, 6, v_p, 6 * v_p);\n"
        "  COMMIT;\nEND;\n/\n"
        "SELECT 'NEW|'||:oid FROM DUAL;")
    legacy_id = int(legacy["NEW"])

    # MODERN: what the Angular client does (price via API, then POST /commit)
    _, price = api("GET", "/price/1")
    unit = price["unitPrice"]
    status, body = api("POST", "/commit", {
        "order": {"orderId": 0, "customerId": 2, "employeeId": 3, "tableNumber": 7,
                  "orderType": "Dine-in", "statues": "Open"},
        "items": [{"itemId": 0, "productIdFk": 1, "quantity": 6,
                   "unitPrice": unit, "totalPrice": 6 * unit}],
    })
    modern_id = int(body["order"]["orderId"]) if status == 200 else -1

    for oid, side in ((legacy_id, "legacy"), (modern_id, "modern")):
        row = sql_tags(
            f"SELECT 'R|'||o.statues||'/'||COUNT(i.item_id)||'/'||SUM(i.total_price) "
            f"FROM orders o JOIN order_items i ON i.order_id_fk = o.order_id "
            f"WHERE o.order_id = {oid} GROUP BY o.statues;")
        record(f"created via {side} path (order {oid})", "Open/1/" + str(6 * float(unit)),
               row.get("R"), row.get("R", "").startswith("Open/1/") and
               money_eq(row.get("R", "0/0/0").split("/")[-1], 6 * float(unit)))
    return legacy_id, modern_id


def s5_guards(legacy_id: int, modern_id: int) -> None:
    print("\nS5 — business-rule guards must fail identically (same ORA code) on both sides")
    # 20002: Paid straight from Open
    lcode = sql_error_code(f"BEGIN pkg_orders.set_status({legacy_id}, 'Paid'); END;\n/")
    mstat, mbody = api("POST", f"/{modern_id}/status", {"status": "Paid"})
    record("guard 20002 pay-while-Open", lcode,
           (mbody or {}).get("code"), lcode == 20002 == (mbody or {}).get("code") and mstat == 409)
    # 20003: cancel without a reason
    lcode = sql_error_code(f"BEGIN pkg_orders.set_status({legacy_id}, 'Cancelled'); END;\n/")
    mstat, mbody = api("POST", f"/{modern_id}/status", {"status": "Cancelled"})
    record("guard 20003 cancel-without-reason", lcode,
           (mbody or {}).get("code"), lcode == 20003 == (mbody or {}).get("code") and mstat == 409)
    # 20001: quantity above stock
    lcode = sql_error_code(
        "INSERT INTO Order_Items (Item_ID, Order_id_fk, Product_id_fk, Quantity, Unit_Price, Total_Price)\n"
        f"VALUES (item_seq.NEXTVAL, {legacy_id}, 1, 99999, 1, 99999);")
    mstat, mbody = api("POST", f"/{modern_id}/items",
                       {"itemId": 0, "productIdFk": 1, "quantity": 99999})
    record("guard 20001 insufficient-stock", lcode,
           (mbody or {}).get("code"), lcode == 20001 == (mbody or {}).get("code") and mstat == 409)


def s4_lifecycle(legacy_id: int, modern_id: int) -> None:
    print("\nS4 — lifecycle Open -> Confirmed -> Ready -> Paid, then the post-confirm freeze guard")
    for step, extra in (("Confirmed", ""), ("Ready", ""), ("Paid", ", NULL, 'Card'")):
        sql(f"BEGIN pkg_orders.set_status({legacy_id}, '{step}'{extra}); COMMIT; END;\n/")
        api("POST", f"/{modern_id}/status",
            {"status": step, "payMethod": "Card" if step == "Paid" else None})
        pair = sql_tags(
            f"SELECT 'L|'||statues||'/'||total_amount||'/'||final_amount FROM orders WHERE order_id = {legacy_id};\n"
            f"SELECT 'M|'||statues||'/'||total_amount||'/'||final_amount FROM orders WHERE order_id = {modern_id};")
        lparts, mparts = pair.get("L", "//").split("/"), pair.get("M", "//").split("/")
        ok = (lparts[0] == mparts[0] == step and
              all(money_eq(a, b) for a, b in zip(lparts[1:], mparts[1:])))
        record(f"lifecycle {step}", pair.get("L"), pair.get("M"), ok)
        if step == "Confirmed":
            # 20004: order lines freeze after Open (DB trigger on both sides)
            lcode = sql_error_code(
                "INSERT INTO Order_Items (Item_ID, Order_id_fk, Product_id_fk, Quantity, Unit_Price, Total_Price)\n"
                f"VALUES (item_seq.NEXTVAL, {legacy_id}, 2, 1, 1, 1);")
            mstat, mbody = api("POST", f"/{modern_id}/items",
                               {"itemId": 0, "productIdFk": 2, "quantity": 1})
            record("guard 20004 line-freeze-after-Open", lcode,
                   (mbody or {}).get("code"),
                   lcode == 20004 == (mbody or {}).get("code") and mstat == 409)
    pay = sql_tags(
        f"SELECT 'PL|'||COUNT(*)||'/'||MAX(amount_payed) FROM payments WHERE order_id_fk = {legacy_id};\n"
        f"SELECT 'PM|'||COUNT(*)||'/'||MAX(amount_payed) FROM payments WHERE order_id_fk = {modern_id};")
    record("payment row written on Paid", pay.get("PL"), pay.get("PM"),
           pay.get("PL", "").startswith("1/") and pay.get("PM", "").startswith("1/") and
           money_eq(pay.get("PL", "0/0").split("/")[1], pay.get("PM", "0/1").split("/")[1]))


# ---- report ------------------------------------------------------------------

def write_report() -> int:
    mismatches = sum(1 for r in results if not r[3])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SHADOW_RESULTS_ORDERS.md")
    with open(out, "w") as fh:
        fh.write("# Live shadow-mode results — ORDERS (Oracle Forms legacy vs migrated .NET)\n\n")
        fh.write("Each operation ran through TWO independent paths against the SAME schema:\n\n")
        fh.write("- **Legacy**: the exact PL/SQL the re-authored form's triggers execute "
                 "(direct DML with the line-freeze/stock DB triggers firing, plus "
                 "`pkg_pricing` / `pkg_orders` calls), executed **by Oracle** via sqlplus.\n")
        fh.write("- **Modern**: the live migrated .NET `OrdersController` over HTTPS "
                 "(CloudFront -> ALB -> ECS Fargate).\n\n")
        fh.write("| Case | Legacy (Oracle) | Modern (.NET) | Verdict |\n|---|---|---|---|\n")
        for case, legacy, modern, match in results:
            fh.write(f"| {case} | {legacy} | {modern} | {'✅ match' if match else '❌ DIFF'} |\n")
        fh.write(f"\n**Agreement: {len(results) - mismatches}/{len(results)}**\n")
    print(f"\nwrote {out} — agreement {len(results) - mismatches}/{len(results)}")
    return mismatches


def main() -> None:
    s1_pricing()
    legacy_id, modern_id = s3_create()
    s2_totals([legacy_id, modern_id])
    s5_guards(legacy_id, modern_id)
    s4_lifecycle(legacy_id, modern_id)
    sys.exit(write_report())


if __name__ == "__main__":
    main()
