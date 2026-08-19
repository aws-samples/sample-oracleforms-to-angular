# Form: ORDERS

Source: `ORDERS.fmb` (Oracle Forms, object store `ROS.60050`). This form bundles UI, business logic (triggers), and data access.

- Blocks: BLOCK7, INTRNL, ORDERS, ORDER_ITEMS
- Tables accessed: ORDER_ITEMS, PRODUCTS
- Navigates to: CATEGORIES_FORM, CUSTOMERS_FORM
- Triggers with logic: 17

## Triggers and PL/SQL logic

### ON-POPULATE-DETAILS on ORDERS
_items=['ORDERS.ORDER_ID']; builtins=['CHECK_PACKAGE_FAILURE', 'GO_ITEM']_
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

### ON-CHECK-DELETE-MASTER on ORDERS
_builtins=['FORM_TRIGGER_FAILURE', 'MESSAGE', 'RAISE']_
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

### PRE-FORM on Form
_tables=['DUAL']; sequences=['ORDER_SEQ']; items=['ORDERS.ORDER_ID']_
```plsql
BEGIN
SELECT order_seq.NEXTVAL INTO :ORDERS.ORDER_ID FROM DUAL;
END;
```

### ON-CLEAR-DETAILS on Form
```plsql
BEGIN
Clear_All_Master_Details;
END;
```

### PRE-INSERT on ORDERS
_tables=['DUAL']; sequences=['ORDER_SEQ']; items=['ORDERS.ORDER_ID']_
```plsql
BEGIN
SELECT order_seq.NEXTVAL
INTO   :ORDERS.ORDER_ID
FROM   DUAL;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
_builtins=['NEXT_RECORD']_
```plsql
BEGIN
NEXT_RECORD;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
_builtins=['PREVIOUS_RECORD']_
```plsql
BEGIN
PREVIOUS_RECORD;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
```plsql
BEGIN
CREATE_RECORD;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
_builtins=['PREVIOUS_RECORD']_
```plsql
BEGIN
PREVIOUS_RECORD;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
_builtins=['COMMIT_FORM']_
```plsql
BEGIN
DELETE_RECORD;
COMMIT_FORM;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
_builtins=['PREVIOUS_RECORD']_
```plsql
BEGIN
PREVIOUS_RECORD;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
_builtins=['COMMIT_FORM', 'FORM_SUCCESS', 'MESSAGE']_
```plsql
BEGIN
COMMIT_FORM;
IF FORM_SUCCESS THEN
MESSAGE('
!');
MESSAGE(' '); --
ELSE
MESSAGE('
');
END IF;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
```plsql
BEGIN
EXIT_FORM(NO_VALIDATE);
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
```plsql
BEGIN
FIRST_RECORD;
END;
```

### WHEN-BUTTON-PRESSED on INTRNL.INTRNL
```plsql
BEGIN
LAST_RECORD;
END;
```

### WHEN-VALIDATE-ITEM on ORDER_ITEMS.QUANTITY
_items=['ORDER_ITEMS.QUANTITY', 'ORDER_ITEMS.TOTAL_PRICE', 'ORDER_ITEMS.UNIT_PRICE']_
```plsql
BEGIN
:ORDER_ITEMS.TOTAL_PRICE := nvl(:ORDER_ITEMS.QUANTITY, 0) * nvl(:ORDER_ITEMS.UNIT_PRICE, 0);
END;
```

### WHEN-BUTTON-PRESSED on BLOCK7.ITEM12
_builtins=['CALL_FORM']_
```plsql
BEGIN
/CALL_FORM('D:\dp_project\categories_form.fmx');
END;
```
