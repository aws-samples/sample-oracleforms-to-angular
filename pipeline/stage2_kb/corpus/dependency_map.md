# Legacy Application Dependency Map

Cross-artifact dependency graph extracted from the Forms binaries and the Oracle DDL. These edges are the natural migration seams.

## Summary
- Forms: 6
- Tables: 7
- Sequences: 1
- Fk Edges: 6
- Navigation Edges: 8
- Access Edges: 3

## Form navigation (which form opens which)
- MAIN_MENU opens CATEGORIES_FORM
- MAIN_MENU opens CUSTOMERS_FORM
- MAIN_MENU opens EMPLOYEES_FORM
- MAIN_MENU opens ORDERS
- MAIN_MENU opens PRODUCT_FORM
- ORDERS opens CATEGORIES_FORM
- ORDERS opens CUSTOMERS_FORM
- PRODUCT_FORM opens CATEGORIES_FORM

## Form data access (which form reads/writes which table)
- ORDERS accesses ORDER_ITEMS
- ORDERS accesses PRODUCTS
- PRODUCT_FORM accesses CATEGORIES

## Referential integrity (foreign keys)
- PRODUCTS.CATEGORY_ID_FK references CATEGORIES
- ORDERS.CUSTOMER_ID references CUSTOMERS
- ORDERS.EMPLOYEE_ID references EMPLOYEES
- ORDER_ITEMS.ORDER_ID_FK references ORDERS
- ORDER_ITEMS.PRODUCT_ID_FK references PRODUCTS
- PAYMENTS.ORDER_ID_FK references ORDERS

## Sequences used
- ORDERS uses sequence ORDER_SEQ (trigger PRE-FORM)
- ORDERS uses sequence ORDER_SEQ (trigger PRE-INSERT)