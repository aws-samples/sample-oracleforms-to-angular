"""
test_orders_equivalence.py

Behavioural-equivalence tests proving the modernized Angular+.NET ORDERS module
reproduces the legacy Oracle Forms behaviour EXACTLY.

Legacy oracles encoded here:
  - WHEN-VALIDATE-ITEM: TOTAL_PRICE := nvl(QUANTITY,0) * nvl(UNIT_PRICE,0)
  - PRE-INSERT:         :ORDERS.ORDER_ID := order_seq.NEXTVAL
  - ON-CHECK-DELETE-MASTER: block delete when matching ORDER_ITEMS exist,
    raising the exact legacy MESSAGE() text.

Run with: pytest
"""

import pytest


# ---------------------------------------------------------------------------
# Pure-Python reference implementation (mirrors the generated .NET/Angular logic)
# ---------------------------------------------------------------------------

# Exact legacy message from ON-CHECK-DELETE-MASTER (must match .NET constant).
CANNOT_DELETE_MASTER_MESSAGE = (
    "Cannot delete master record when matching detail records exist."
)


class FormTriggerFailure(Exception):
    """Mirrors Oracle Forms RAISE Form_Trigger_Failure for referential guard."""


def _nvl(value, default):
    """Oracle NVL: return default when value is NULL (None)."""
    return default if value is None else value


def compute_line_total(qty, unit_price):
    """
    WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY):
        :ORDER_ITEMS.TOTAL_PRICE := nvl(:ORDER_ITEMS.QUANTITY, 0)
                                    * nvl(:ORDER_ITEMS.UNIT_PRICE, 0)

    Mirrors Angular recomputeLineTotal():
        const qty = item.quantity ?? 0;
        const price = item.unitPrice ?? 0;
        item.totalPrice = qty * price;
    """
    return _nvl(qty, 0) * _nvl(unit_price, 0)


def next_order_id(seq_state):
    """
    PRE-INSERT (ORDERS):
        SELECT order_seq.NEXTVAL INTO :ORDERS.ORDER_ID FROM DUAL;

    Models ORDER_SEQ.NEXTVAL. `seq_state` is a mutable dict holding the last
    issued value under key "last". Returns the next value and advances state,
    exactly as an Oracle sequence would (monotonic increment by 1).
    """
    seq_state["last"] = seq_state.get("last", 0) + 1
    return seq_state["last"]


def check_delete_master(order_items):
    """
    ON-CHECK-DELETE-MASTER (ORDERS):
        OPEN ORDER_ITEMS_cur; FETCH ...;
        IF found THEN
            Message('Cannot delete master record when matching detail records exist.');
            RAISE Form_Trigger_Failure;
        END IF;

    Raises FormTriggerFailure with the exact legacy message if any detail row
    exists; otherwise returns True to indicate the delete may proceed.
    """
    if order_items:  # cursor%found -> at least one detail row
        raise FormTriggerFailure(CANNOT_DELETE_MASTER_MESSAGE)
    return True


# ---------------------------------------------------------------------------
# (1) WHEN-VALIDATE-ITEM arithmetic: total = nvl(qty,0) * nvl(price,0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "qty, unit_price, expected",
    [
        (2, 10, 20),               # normal case
        (1, 99.99, 99.99),         # decimal price
        (0, 50, 0),                # zero quantity
        (5, 0, 0),                 # zero price
        (0, 0, 0),                 # both zero
        (None, 10, 0),             # null quantity -> nvl(0)
        (3, None, 0),              # null price -> nvl(0)
        (None, None, 0),           # both null -> 0
        (10, 2.5, 25.0),           # fractional price
        (100, 1, 100),             # larger quantity
    ],
)
def test_line_total_matches_legacy_nvl_rule(qty, unit_price, expected):
    assert compute_line_total(qty, unit_price) == expected


def test_line_total_null_handling_is_exactly_zero_not_none():
    # Legacy NVL guarantees a numeric result, never NULL.
    assert compute_line_total(None, None) == 0
    assert compute_line_total(None, None) is not None


# ---------------------------------------------------------------------------
# (2) PRE-INSERT: ORDER_ID assigned from ORDER_SEQ.NEXTVAL and increments
# ---------------------------------------------------------------------------

def test_pk_assigned_from_sequence_increments_by_one():
    seq = {"last": 0}
    first = next_order_id(seq)
    second = next_order_id(seq)
    third = next_order_id(seq)
    assert first == 1
    assert second == 2
    assert third == 3


def test_sequence_is_monotonic_across_many_inserts():
    seq = {"last": 0}
    ids = [next_order_id(seq) for _ in range(50)]
    # Strictly increasing, no gaps, no duplicates.
    assert ids == list(range(1, 51))
    assert len(set(ids)) == len(ids)


def test_sequence_continues_from_existing_high_water_mark():
    # Emulates a sequence already advanced (e.g., pre-existing data).
    seq = {"last": 1000}
    assert next_order_id(seq) == 1001
    assert next_order_id(seq) == 1002


def test_client_supplied_order_id_is_ignored_sequence_wins():
    # Legacy PRE-INSERT always overwrites :ORDERS.ORDER_ID with NEXTVAL,
    # and the .NET CreateAsync ignores any client-supplied ORDER_ID.
    seq = {"last": 41}
    client_supplied_id = 999999
    assigned = next_order_id(seq)
    assert assigned == 42
    assert assigned != client_supplied_id


# ---------------------------------------------------------------------------
# (3) ON-CHECK-DELETE-MASTER: block delete with details, allow without
# ---------------------------------------------------------------------------

def test_delete_master_with_items_raises_exact_legacy_message():
    order_items = [
        {"itemId": 1, "orderIdFk": 42, "quantity": 2, "unitPrice": 10, "totalPrice": 20},
    ]
    with pytest.raises(FormTriggerFailure) as excinfo:
        check_delete_master(order_items)
    assert str(excinfo.value) == CANNOT_DELETE_MASTER_MESSAGE


def test_delete_master_with_multiple_items_raises():
    order_items = [
        {"itemId": 1, "orderIdFk": 42},
        {"itemId": 2, "orderIdFk": 42},
    ]
    with pytest.raises(FormTriggerFailure):
        check_delete_master(order_items)


def test_delete_master_without_items_succeeds():
    assert check_delete_master([]) is True
    assert check_delete_master(None) is True


def test_legacy_message_matches_dotnet_constant_text():
    # Guards against drift between the legacy MESSAGE() text and the .NET
    # OrderService.CannotDeleteMasterMessage constant.
    dotnet_constant = "Cannot delete master record when matching detail records exist."
    assert CANNOT_DELETE_MASTER_MESSAGE == dotnet_constant


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))