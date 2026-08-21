-- =============================================================================
-- app_data_packages.sql  (BUG-4 seed artifact)
-- Run as SYSTEM against XEPDB1 by DatabaseStack EC2 UserData. The bootstrap
-- realigns app_data's password to the Secrets Manager value right after this runs.
--
-- Creates the app_data schema that the modern .NET API connects as, and provisions
-- the ORDERS retail schema (master ORDERS / detail ORDER_ITEMS) — the Oracle Forms
-- module being modernized — with a representative seed dataset so the "after" app
-- and the Forms "before" render identical data.
-- =============================================================================
WHENEVER SQLERROR CONTINUE
ALTER SESSION SET CONTAINER = XEPDB1;

DECLARE n NUMBER; BEGIN
  SELECT COUNT(*) INTO n FROM dba_users WHERE username = 'APP_DATA';
  IF n = 0 THEN EXECUTE IMMEDIATE 'CREATE USER app_data IDENTIFIED BY ChangeMe_2026'; END IF;
END;
/
GRANT CONNECT, RESOURCE TO app_data;
ALTER USER app_data QUOTA UNLIMITED ON USERS;

ALTER SESSION SET CURRENT_SCHEMA = app_data;

-- ---- ORDERS retail schema -------------------------------------------------
CREATE TABLE Categories (Category_ID NUMBER PRIMARY KEY, Category_Name VARCHAR2(100) NOT NULL, Descriptions VARCHAR2(255));
CREATE SEQUENCE cat_seq START WITH 1 INCREMENT BY 1;
CREATE TABLE Customers(Customer_ID NUMBER PRIMARY KEY, Name VARCHAR2(100) NOT NULL, Phone VARCHAR2(15), Register_Data DATE DEFAULT SYSDATE);
CREATE SEQUENCE cust_seq START WITH 1 INCREMENT BY 1;
CREATE TABLE Employees (Employee_ID NUMBER PRIMARY KEY, Name VARCHAR2(100) NOT NULL, phone VARCHAR2(15), Role VARCHAR2(60), Salary NUMBER(10,2));
CREATE SEQUENCE emp_seq START WITH 1 INCREMENT BY 1;
CREATE TABLE Products(Product_ID NUMBER PRIMARY KEY, Name VARCHAR2(60) NOT NULL, Price NUMBER(8,2) NOT NULL, Category_ID_fk NUMBER, Cost NUMBER(8,2), Available VARCHAR2(20), CONSTRAINT fk_category FOREIGN KEY (Category_ID_fk) REFERENCES Categories(Category_ID));
CREATE SEQUENCE Prod_seq START WITH 1 INCREMENT BY 1;
CREATE TABLE Orders(Order_ID NUMBER PRIMARY KEY, Order_Data DATE DEFAULT SYSDATE, Customer_ID NUMBER, Employee_ID NUMBER, Total_Amount NUMBER(10,2), Table_Number NUMBER, Order_Type VARCHAR2(50), Discount NUMBER(10,2), Final_Amount Number(10,2), Statues VARCHAR2(50), CONSTRAINT fk_cust FOREIGN KEY (Customer_ID) REFERENCES Customers(Customer_ID), CONSTRAINT fk_emp FOREIGN KEY (Employee_ID) REFERENCES Employees(Employee_ID));
CREATE SEQUENCE Ord_seq START WITH 1 INCREMENT BY 1;
-- BUG-10: the ORDERS form uses ORDER_SEQ (not Ord_seq)
CREATE SEQUENCE ORDER_SEQ START WITH 1 INCREMENT BY 1;
CREATE TABLE Order_Items(Item_ID NUMBER PRIMARY KEY, Order_id_fk NUMBER, Product_id_fk number, Quantity NUMBER NOT NULL, Unit_Price NUMBER(8,2), Total_Price NUMBER(10,2), CONSTRAINT fk_order_link FOREIGN KEY (Order_id_fk) REFERENCES Orders(Order_id), CONSTRAINT fk_prod_link FOREIGN KEY (Product_id_fk) REFERENCES Products(Product_id));
CREATE SEQUENCE item_seq START WITH 1 INCREMENT BY 1;
CREATE TABLE Payments(Payment_ID NUMBER PRIMARY KEY, Order_id_fk NUMBER, Payment_Method VARCHAR2(50), Amount_Payed NUMBER(10,2), Payment_Date DATE DEFAULT SYSDATE, CONSTRAINT fk_payment_order FOREIGN KEY (Order_id_fk) REFERENCES Orders(Order_id));
CREATE SEQUENCE pay_seq START WITH 1 INCREMENT BY 1;

-- ---- representative seed dataset ------------------------------------------
DECLARE
  v_ord NUMBER; v_cust NUMBER; v_emp NUMBER; v_prod NUMBER; v_price NUMBER; v_qty NUMBER; v_tot NUMBER; v_disc NUMBER;
  TYPE tarr IS TABLE OF VARCHAR2(60);
  cust_names tarr := tarr('Sample Customer','Alice Martin','Bob Chen','Carla Diaz','David Okoro','Emma Rossi','Farid Haddad','Grace Kim','Hiro Tanaka','Ivan Petrov','Julia Santos','Kenji Ito','Lucia Ferro','Mateo Cruz','Nina Popov','Otto Braun','Petra Novak','Quinn Ryan','Rosa Vega','Sam Bello','Tara Singh');
  emp_names  tarr := tarr('Sample Employee','Liam Turner','Nadia Aziz','Omar Silva','Priya Nair');
  prod_names tarr := tarr('Latte','Espresso','Cappuccino','Green Tea','Croissant','BLT Sandwich','Caesar Salad','Cheesecake','Brownie','Orange Juice','Club Sandwich');
  otypes tarr := tarr('Dine-in','Takeaway','Delivery');
  ostatus tarr := tarr('Open','Paid','Cancelled');
  pmeth tarr := tarr('Cash','Card','Online');
BEGIN
  INSERT INTO Categories VALUES (cat_seq.NEXTVAL,'Drinks','Hot and Cold');
  INSERT INTO Categories VALUES (cat_seq.NEXTVAL,'Food','Mains and sides');
  INSERT INTO Categories VALUES (cat_seq.NEXTVAL,'Desserts','Sweet treats');
  FOR i IN 1..prod_names.COUNT LOOP
    INSERT INTO Products (Product_ID,Name,Price,Category_ID_fk,Cost,Available)
      VALUES (prod_seq.NEXTVAL, prod_names(i), 20 + MOD(i*7,40), MOD(i,3)+1, 8 + MOD(i,15), 'Yes');
  END LOOP;
  FOR i IN 1..cust_names.COUNT LOOP
    INSERT INTO Customers VALUES (cust_seq.NEXTVAL, cust_names(i), '555-01'||LPAD(i,2,'0'), SYSDATE - i);
  END LOOP;
  FOR i IN 1..emp_names.COUNT LOOP
    INSERT INTO Employees VALUES (emp_seq.NEXTVAL, emp_names(i), '555-02'||LPAD(i,2,'0'),
      CASE MOD(i,3) WHEN 0 THEN 'Server' WHEN 1 THEN 'Cashier' ELSE 'Barista' END, 3000 + i*250);
  END LOOP;
  COMMIT;
  FOR i IN 1..100 LOOP
    SELECT customer_id INTO v_cust FROM (SELECT customer_id FROM Customers ORDER BY DBMS_RANDOM.VALUE) WHERE ROWNUM=1;
    SELECT employee_id INTO v_emp  FROM (SELECT employee_id FROM Employees ORDER BY DBMS_RANDOM.VALUE) WHERE ROWNUM=1;
    v_ord := ORDER_SEQ.NEXTVAL; v_tot := 0;
    INSERT INTO Orders (Order_ID,Order_Data,Customer_ID,Employee_ID,Total_Amount,Table_Number,Order_Type,Discount,Final_Amount,Statues)
      VALUES (v_ord, SYSDATE - MOD(i,14), v_cust, v_emp, 0, MOD(i,12)+1, otypes(MOD(i,3)+1), 0, 0, ostatus(MOD(i,3)+1));
    FOR j IN 1..(MOD(i,3)+1) LOOP
      SELECT product_id, price INTO v_prod, v_price FROM (SELECT product_id, price FROM Products ORDER BY DBMS_RANDOM.VALUE) WHERE ROWNUM=1;
      v_qty := MOD(i+j,4)+1;
      INSERT INTO Order_Items (Item_ID,Order_id_fk,Product_id_fk,Quantity,Unit_Price,Total_Price)
        VALUES (item_seq.NEXTVAL, v_ord, v_prod, v_qty, v_price, v_price*v_qty);
      v_tot := v_tot + v_price*v_qty;
    END LOOP;
    v_disc := ROUND(v_tot * CASE WHEN MOD(i,4)=0 THEN 0.10 ELSE 0 END, 2);
    UPDATE Orders SET Total_Amount=v_tot, Discount=v_disc, Final_Amount=v_tot-v_disc WHERE Order_ID=v_ord;
    INSERT INTO Payments (Payment_ID,Order_id_fk,Payment_Method,Amount_Payed,Payment_Date)
      VALUES (pay_seq.NEXTVAL, v_ord, pmeth(MOD(i,3)+1), v_tot-v_disc, SYSDATE - MOD(i,14));
  END LOOP;
  COMMIT;
END;
/
-- =============================================================================
-- orders_logic.sql — business rules for the ORDERS retail schema (app_data).
--
-- This is the "legacy" PL/SQL layer the migration pipeline must recover and the
-- modern .NET API calls as-is (thin-gateway / replicate phase). All error
-- messages are deliberately HARDCODED IN ENGLISH, as in a real legacy app; the
-- modern frontend localizes them by ORA error code (-20001..-20004).
--
-- Idempotent: safe to run repeatedly (guarded ALTERs, CREATE OR REPLACE).
-- Run as SYSTEM with CURRENT_SCHEMA=app_data, or as app_data.
-- =============================================================================
WHENEVER SQLERROR CONTINUE

-- ---- schema deltas ----------------------------------------------------------
DECLARE
  PROCEDURE add_col(p_sql VARCHAR2) IS
    e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -1430);
  BEGIN EXECUTE IMMEDIATE p_sql; EXCEPTION WHEN e_exists THEN NULL; END;
BEGIN
  add_col('ALTER TABLE Products ADD (Stock_Qty NUMBER DEFAULT 100 NOT NULL)');
  add_col('ALTER TABLE Products ADD (Reorder_Level NUMBER DEFAULT 10)');
  add_col('ALTER TABLE Orders ADD (Cancel_Reason VARCHAR2(200))');
END;
/

DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE Pricing_Config (
     Param_Name  VARCHAR2(40) PRIMARY KEY,
     Param_Value VARCHAR2(40) NOT NULL)';
EXCEPTION WHEN e_exists THEN NULL; END;
/

-- config-driven so the happy hour is demoable at any time of day
MERGE INTO Pricing_Config c USING (
  SELECT 'HAPPY_HOUR_START'    n, '15'      v FROM dual UNION ALL
  SELECT 'HAPPY_HOUR_END'      n, '18'      v FROM dual UNION ALL
  SELECT 'HAPPY_HOUR_DISCOUNT' n, '0.20'    v FROM dual UNION ALL
  SELECT 'HAPPY_HOUR_CATEGORY' n, 'Drinks'  v FROM dual UNION ALL
  SELECT 'VOLUME_TIER1_QTY'    n, '5'       v FROM dual UNION ALL
  SELECT 'VOLUME_TIER1_PCT'    n, '0.05'    v FROM dual UNION ALL
  SELECT 'VOLUME_TIER2_QTY'    n, '10'      v FROM dual UNION ALL
  SELECT 'VOLUME_TIER2_PCT'    n, '0.10'    v FROM dual UNION ALL
  SELECT 'CASH_ROUNDING'       n, '0.05'    v FROM dual UNION ALL
  SELECT 'GST_RATE'            n, '0.05'    v FROM dual UNION ALL
  SELECT 'QST_RATE'            n, '0.09975' v FROM dual
) s ON (c.Param_Name = s.n)
WHEN NOT MATCHED THEN INSERT (Param_Name, Param_Value) VALUES (s.n, s.v);
COMMIT;

-- ---- pkg_pricing ------------------------------------------------------------
CREATE OR REPLACE PACKAGE pkg_pricing AS
  FUNCTION cfg(p_name VARCHAR2) RETURN NUMBER;
  -- TRUE when p_at falls inside the configured happy-hour window
  FUNCTION is_happy_hour(p_at DATE DEFAULT SYSDATE) RETURN BOOLEAN;
  -- effective unit price: base price, minus the happy-hour discount when the
  -- product belongs to the configured category and p_at is in the window
  FUNCTION line_unit_price(p_product_id NUMBER, p_at DATE DEFAULT SYSDATE) RETURN NUMBER;
  -- legacy cash-drawer quirk: totals rounded to the nearest 0.05
  FUNCTION round_cash(p_amount NUMBER) RETURN NUMBER;
  -- full order economics; volume discount by TOTAL item count on the order
  PROCEDURE order_totals(p_order_id  IN  NUMBER,
                         p_subtotal  OUT NUMBER,
                         p_discount  OUT NUMBER,
                         p_gst       OUT NUMBER,
                         p_qst       OUT NUMBER,
                         p_total     OUT NUMBER);
END pkg_pricing;
/
CREATE OR REPLACE PACKAGE BODY pkg_pricing AS

  FUNCTION cfg(p_name VARCHAR2) RETURN NUMBER IS
    v VARCHAR2(40);
  BEGIN
    SELECT Param_Value INTO v FROM Pricing_Config WHERE Param_Name = p_name;
    RETURN TO_NUMBER(v);
  END;

  FUNCTION cfgs(p_name VARCHAR2) RETURN VARCHAR2 IS
    v VARCHAR2(40);
  BEGIN
    SELECT Param_Value INTO v FROM Pricing_Config WHERE Param_Name = p_name;
    RETURN v;
  END;

  FUNCTION is_happy_hour(p_at DATE DEFAULT SYSDATE) RETURN BOOLEAN IS
    h NUMBER := TO_NUMBER(TO_CHAR(p_at, 'HH24'));
  BEGIN
    RETURN h >= cfg('HAPPY_HOUR_START') AND h < cfg('HAPPY_HOUR_END');
  END;

  FUNCTION line_unit_price(p_product_id NUMBER, p_at DATE DEFAULT SYSDATE) RETURN NUMBER IS
    v_price Products.Price%TYPE;
    v_cat   Categories.Category_Name%TYPE;
  BEGIN
    SELECT p.Price, c.Category_Name INTO v_price, v_cat
      FROM Products p LEFT JOIN Categories c ON c.Category_ID = p.Category_ID_fk
     WHERE p.Product_ID = p_product_id;
    IF is_happy_hour(p_at) AND v_cat = cfgs('HAPPY_HOUR_CATEGORY') THEN
      v_price := ROUND(v_price * (1 - cfg('HAPPY_HOUR_DISCOUNT')), 2);
    END IF;
    RETURN v_price;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    RAISE_APPLICATION_ERROR(-20005, 'Unknown product id ' || p_product_id);
  END;

  FUNCTION round_cash(p_amount NUMBER) RETURN NUMBER IS
    r NUMBER := cfg('CASH_ROUNDING');
  BEGIN
    RETURN ROUND(p_amount / r) * r;
  END;

  PROCEDURE order_totals(p_order_id  IN  NUMBER,
                         p_subtotal  OUT NUMBER,
                         p_discount  OUT NUMBER,
                         p_gst       OUT NUMBER,
                         p_qst       OUT NUMBER,
                         p_total     OUT NUMBER) IS
    v_qty NUMBER;
    v_net NUMBER;
  BEGIN
    SELECT NVL(SUM(Total_Price), 0), NVL(SUM(Quantity), 0)
      INTO p_subtotal, v_qty
      FROM Order_Items WHERE Order_id_fk = p_order_id;

    IF    v_qty >= cfg('VOLUME_TIER2_QTY') THEN p_discount := ROUND(p_subtotal * cfg('VOLUME_TIER2_PCT'), 2);
    ELSIF v_qty >= cfg('VOLUME_TIER1_QTY') THEN p_discount := ROUND(p_subtotal * cfg('VOLUME_TIER1_PCT'), 2);
    ELSE  p_discount := 0;
    END IF;

    v_net   := p_subtotal - p_discount;
    p_gst   := ROUND(v_net * cfg('GST_RATE'), 2);
    p_qst   := ROUND(v_net * cfg('QST_RATE'), 2);
    p_total := round_cash(v_net + p_gst + p_qst);
  END;

END pkg_pricing;
/

-- ---- pkg_orders (status state machine) ---------------------------------------
CREATE OR REPLACE PACKAGE pkg_orders AS
  FUNCTION can_transition(p_from VARCHAR2, p_to VARCHAR2) RETURN BOOLEAN;
  -- validates the transition, applies side effects:
  --   Confirmed -> recomputes and stores the order totals (pkg_pricing)
  --   Cancelled -> requires p_reason, restocks every line
  --   Paid      -> records a Payment row for the final amount
  PROCEDURE set_status(p_order_id NUMBER, p_new_status VARCHAR2,
                       p_reason VARCHAR2 DEFAULT NULL,
                       p_pay_method VARCHAR2 DEFAULT 'Cash');
END pkg_orders;
/
CREATE OR REPLACE PACKAGE BODY pkg_orders AS

  FUNCTION can_transition(p_from VARCHAR2, p_to VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN (p_from = 'Open'      AND p_to IN ('Confirmed', 'Cancelled'))
        OR (p_from = 'Confirmed' AND p_to IN ('Ready', 'Cancelled'))
        OR (p_from = 'Ready'     AND p_to IN ('Paid', 'Cancelled'));
  END;

  PROCEDURE set_status(p_order_id NUMBER, p_new_status VARCHAR2,
                       p_reason VARCHAR2 DEFAULT NULL,
                       p_pay_method VARCHAR2 DEFAULT 'Cash') IS
    v_cur   Orders.Statues%TYPE;
    v_sub   NUMBER; v_disc NUMBER; v_gst NUMBER; v_qst NUMBER; v_tot NUMBER;
  BEGIN
    SELECT Statues INTO v_cur FROM Orders WHERE Order_ID = p_order_id FOR UPDATE;

    IF NOT can_transition(v_cur, p_new_status) THEN
      RAISE_APPLICATION_ERROR(-20002,
        'Invalid status transition: "' || v_cur || '" -> "' || p_new_status || '"');
    END IF;

    IF p_new_status = 'Cancelled' AND (p_reason IS NULL OR TRIM(p_reason) IS NULL) THEN
      RAISE_APPLICATION_ERROR(-20003, 'A cancellation reason is required');
    END IF;

    IF p_new_status = 'Confirmed' THEN
      pkg_pricing.order_totals(p_order_id, v_sub, v_disc, v_gst, v_qst, v_tot);
      UPDATE Orders
         SET Total_Amount = v_sub, Discount = v_disc, Final_Amount = v_tot
       WHERE Order_ID = p_order_id;
    ELSIF p_new_status = 'Cancelled' THEN
      -- put every line back into stock; lines are frozen after Open, so this
      -- is the single restock point (see trg_items_status_guard)
      FOR l IN (SELECT Product_id_fk, Quantity FROM Order_Items
                 WHERE Order_id_fk = p_order_id) LOOP
        UPDATE Products SET Stock_Qty = Stock_Qty + l.Quantity
         WHERE Product_ID = l.Product_id_fk;
      END LOOP;
      UPDATE Orders SET Cancel_Reason = p_reason WHERE Order_ID = p_order_id;
    ELSIF p_new_status = 'Paid' THEN
      SELECT NVL(Final_Amount, 0) INTO v_tot FROM Orders WHERE Order_ID = p_order_id;
      INSERT INTO Payments (Payment_ID, Order_id_fk, Payment_Method, Amount_Payed, Payment_Date)
      VALUES (pay_seq.NEXTVAL, p_order_id, p_pay_method, v_tot, SYSDATE);
    END IF;

    UPDATE Orders SET Statues = p_new_status WHERE Order_ID = p_order_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    RAISE_APPLICATION_ERROR(-20006, 'Unknown order id ' || p_order_id);
  END;

END pkg_orders;
/

-- ---- stock + line-freeze triggers on ORDER_ITEMS ------------------------------
-- Lines may only change while the order is Open (guard), and stock moves with
-- every line change. Messages are in a strict, parseable English format.
CREATE OR REPLACE TRIGGER trg_items_status_guard
BEFORE INSERT OR UPDATE OR DELETE ON Order_Items
FOR EACH ROW
DECLARE
  v_status Orders.Statues%TYPE;
  v_order  NUMBER := COALESCE(:new.Order_id_fk, :old.Order_id_fk);
BEGIN
  SELECT Statues INTO v_status FROM Orders WHERE Order_ID = v_order;
  IF v_status <> 'Open' THEN
    RAISE_APPLICATION_ERROR(-20004,
      'Order lines can only be modified while the order is Open (current status: "'
      || v_status || '")');
  END IF;
EXCEPTION WHEN NO_DATA_FOUND THEN NULL; -- master inserted in same tx
END;
/

CREATE OR REPLACE TRIGGER trg_items_stock
BEFORE INSERT OR UPDATE OF Quantity OR DELETE ON Order_Items
FOR EACH ROW
DECLARE
  v_name  Products.Name%TYPE;
  v_stock Products.Stock_Qty%TYPE;
  v_delta NUMBER := NVL(:new.Quantity, 0) - NVL(:old.Quantity, 0); -- net stock take
BEGIN
  IF DELETING THEN
    UPDATE Products SET Stock_Qty = Stock_Qty + :old.Quantity
     WHERE Product_ID = :old.Product_id_fk;
    RETURN;
  END IF;
  SELECT Name, Stock_Qty INTO v_name, v_stock
    FROM Products WHERE Product_ID = :new.Product_id_fk FOR UPDATE;
  IF v_delta > v_stock THEN
    RAISE_APPLICATION_ERROR(-20001,
      'Insufficient stock for product "' || v_name || '" (available: ' || v_stock
      || ', requested: ' || v_delta || ')');
  END IF;
  UPDATE Products SET Stock_Qty = Stock_Qty - v_delta
   WHERE Product_ID = :new.Product_id_fk;
END;
/

-- verification block
SET SERVEROUTPUT ON
DECLARE
  s NUMBER; d NUMBER; g NUMBER; q NUMBER; t NUMBER;
BEGIN
  pkg_pricing.order_totals(1, s, d, g, q, t);
  DBMS_OUTPUT.PUT_LINE('LOGIC_OK subtotal=' || s || ' discount=' || d ||
                       ' gst=' || g || ' qst=' || q || ' total=' || t);
END;
/
SELECT object_name, object_type, status FROM all_objects
 WHERE owner = 'APP_DATA'
   AND object_name IN ('PKG_PRICING','PKG_ORDERS','TRG_ITEMS_STOCK','TRG_ITEMS_STATUS_GUARD')
 ORDER BY object_name, object_type;
