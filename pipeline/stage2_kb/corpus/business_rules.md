# Business Rules Recovered from the Legacy Oracle Application

These are the tacit business rules extracted from the legacy Oracle Forms triggers by the AI modernization pipeline. They are the knowledge that must be preserved during migration.

## ORDERS — ON-POPULATE-DETAILS (ORDERS)
**Intent:** Coordinates a master-detail relationship (populates child rows for the current master).
```plsql
Begin ORDER_ITEMS detail program section
IF ( (:ORDERS.ORDER_ID is not null) ) THEN
rel_id := Find_Relation('ORDERS.ORDERS_ORDER_ITEMS');
Query_Master_Details(rel_id, 'ORDER_ITEMS');
END IF;
IF ( :System.cursor_item <> startitm ) THEN
Go_Item(startitm);
Check_Package_Failure;
END IF;
END;
```

## ORDERS — ON-CHECK-DELETE-MASTER (ORDERS)
**Intent:** Enforces a referential/validation rule and blocks the operation on failure.
```plsql
Begin ORDER_ITEMS detail program section
OPEN ORDER_ITEMS_cur;
FETCH ORDER_ITEMS_cur INTO Dummy_Define;
IF ( ORDER_ITEMS_cur%found ) THEN
Message('Cannot delete master record when matching detail records exist.');
CLOSE ORDER_ITEMS_cur;
RAISE Form_Trigger_Failure;
END IF;
CLOSE ORDER_ITEMS_cur;
END;
```

## ORDERS — PRE-INSERT (ORDERS)
**Intent:** Assigns a surrogate primary key from a database sequence before insert.
```plsql
BEGIN
SELECT order_seq.NEXTVAL
INTO   :ORDERS.ORDER_ID
FROM   DUAL;
END;
```

## ORDERS — WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY)
**Intent:** Computes a derived/total field from other item values.
```plsql
BEGIN
:ORDER_ITEMS.TOTAL_PRICE := nvl(:ORDER_ITEMS.QUANTITY, 0) * nvl(:ORDER_ITEMS.UNIT_PRICE, 0);
END;
```
