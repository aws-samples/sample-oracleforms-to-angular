# Acceptance Criteria — ORDERS Module Behavioural Equivalence

**Objective:** Prove the modernized Angular + .NET ORDERS module reproduces the legacy Oracle Forms (`ORDERS.fmb`) behaviour **exactly** (Phase 1 — REPLICATE). Each recovered PL/SQL business rule is mapped to its modern implementation location and the executable test that proves equivalence against legacy-derived expected values.

## Traceability Matrix

| # | Legacy Rule | Source Trigger (.fmb) | Business Behaviour | Modern Implementation | Proving Test |
|---|-------------|-----------------------|--------------------|-----------------------|--------------|
| R1 | Sequence key assignment | `PRE-INSERT (ORDERS)` — `SELECT order_seq.NEXTVAL INTO :ORDERS.ORDER_ID` | `ORDER_ID` is always allocated from `ORDER_SEQ.NEXTVAL` on insert; any client-supplied `ORDER_ID` is ignored; values are monotonic and gap-tolerant. | `.NET` `OrderService.CreateAsync` (server-side sequence fetch); Angular `OrdersComponent.createRecord()` → `nextOrderId()` | `test_pre_insert_assigns_sequence_nextval`, `test_pre_insert_ignores_client_supplied_id`, `test_sequence_is_monotonic` |
| R2 | Line total computation | `WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY)` — `:TOTAL_PRICE := nvl(:QUANTITY,0) * nvl(:UNIT_PRICE,0)` | `TOTAL_PRICE = NVL(QUANTITY,0) * NVL(UNIT_PRICE,0)`; NULL quantity or unit price is treated as `0`; result is never NULL. | `.NET` `OrderService.CreateAsync` (recomputes line totals); Angular `OrdersComponent.recomputeLineTotal()` | `test_line_total_basic`, `test_line_total_null_quantity`, `test_line_total_null_unit_price`, `test_line_total_both_null` |
| R3 | Master delete referential guard | `ON-CHECK-DELETE-MASTER (ORDERS)` — open `ORDER_ITEMS_cur`; if `%found` raise `Form_Trigger_Failure` | Deleting an ORDERS master is blocked when any matching `ORDER_ITEMS` detail row exists; the exact legacy message is emitted; deletion proceeds only when no details exist. | `.NET` `OrderService` (delete guard + `CannotDeleteMasterMessage`) | `test_delete_blocked_when_details_exist`, `test_delete_allowed_when_no_details`, `test_delete_block_message_matches_legacy` |

## Edge Cases Explicitly Covered

| Edge Case | Rule | Expected Legacy Behaviour |
|-----------|------|---------------------------|
| NULL quantity | R2 | `NVL(NULL,0)=0` → total `0`, not NULL |
| NULL unit price | R2 | `NVL(NULL,0)=0` → total `0`, not NULL |
| Both NULL | R2 | total `0` |
| Client sends explicit `ORDER_ID` | R1 | Ignored; sequence value wins |
| Delete master with 1+ details | R3 | Blocked, `Form_Trigger_Failure` equivalent, exact message |
| Delete master with 0 details | R3 | Allowed |
| Sequence value ordering | R1 | Strictly increasing (`NEXTVAL` semantics) |

## Definition of Done (Shadow-Mode Criteria)

The ORDERS module is accepted as behaviourally equivalent when **all** of the following hold:

1. **100% rule coverage** — every recovered legacy trigger (R1–R3) maps to at least one passing, executable acceptance test.
2. **Exact-match, not approximate** — modern outputs equal legacy-derived expected values byte-for-byte / value-for-value, including the verbatim `ON-CHECK-DELETE-MASTER` message string `"Cannot delete master record when matching detail records exist."`.
3. **Null-semantics parity** — Oracle `NVL(...,0)` behaviour is reproduced; no computed `TOTAL_PRICE` is ever NULL.
4. **Sequence-key parity** — `ORDER_ID` originates solely from the server-side sequence; client-supplied IDs never leak into persisted records; allocated values are monotonically increasing.
5. **Referential-guard parity** — master deletes are blocked iff detail rows exist; the failure path mirrors `Form_Trigger_Failure` (operation aborted, no partial delete).
6. **Green suite** — `pytest` runs with no external services or database and reports **all tests passing**.
7. **Shadow-mode reconciliation** — running the modern path and the legacy path over the same input corpus yields zero diffs across all matrixed scenarios and edge cases above.
8. **Traceability** — this matrix is kept current; adding or changing a rule requires a corresponding test update in the same change set.

**Exit gate:** Sign-off is granted only when Definition-of-Done items 1–8 are simultaneously satisfied and the reconciliation diff report is empty.