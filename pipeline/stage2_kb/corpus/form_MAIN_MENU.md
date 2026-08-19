# Form: MAIN_MENU

Source: `MAIN_MENU.fmb` (Oracle Forms, object store `ROS.60050`). This form bundles UI, business logic (triggers), and data access.

- Blocks: BLOCK7
- Tables accessed: n/a
- Navigates to: CATEGORIES_FORM, CUSTOMERS_FORM, EMPLOYEES_FORM, ORDERS, PRODUCT_FORM
- Triggers with logic: 6

## Triggers and PL/SQL logic

### WHEN-BUTTON-PRESSED on BLOCK7.ITEM16
```plsql
BEGIN
EXIT_FORM(ASK_COMMIT);
END;
```

### WHEN-NEW-FORM-INSTANCE on Form
_builtins=['EXECUTE_QUERY']_
```plsql
BEGIN
EXECUTE_QUERY;
END;
```

### WHEN-BUTTON-PRESSED on BLOCK7.ITEM12
_builtins=['CALL_FORM']_
```plsql
BEGIN
/CALL_FORM('D:\dp_project\categories_form.fmx');
END;
```

### WHEN-BUTTON-PRESSED on BLOCK7.ITEM13
_builtins=['CALL_FORM']_
```plsql
BEGIN
.CALL_FORM('D:\dp_project\employees_form.fmx');
END;
```

### WHEN-BUTTON-PRESSED on BLOCK7.ITEM14
_builtins=['CALL_FORM']_
```plsql
BEGIN
,CALL_FORM('D:\dp_project\product_form.fmx');
END;
```

### WHEN-BUTTON-PRESSED on BLOCK7.ITEM16
```plsql
BEGIN
EXIT_FORM(ASK_COMMIT);
END;
```
