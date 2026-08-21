ALTER SESSION SET CURRENT_SCHEMA = app_data;
SET SERVEROUTPUT ON SIZE UNLIMITED
SET FEEDBACK OFF
DECLARE
  s NUMBER; d NUMBER; g NUMBER; q NUMBER; t NUMBER;
  v_open  NUMBER; v_paid NUMBER; v_item NUMBER;
  v_drink NUMBER; v_base NUMBER; v_hh NUMBER;
  PROCEDURE expect_err(p_label VARCHAR2, p_stmt VARCHAR2, p_code NUMBER) IS
  BEGIN
    EXECUTE IMMEDIATE p_stmt;
    DBMS_OUTPUT.PUT_LINE(p_label || ': FAIL (no error raised)');
    ROLLBACK;
  EXCEPTION WHEN OTHERS THEN
    IF SQLCODE = p_code THEN
      DBMS_OUTPUT.PUT_LINE(p_label || ': OK  [' || SQLERRM || ']');
    ELSE
      DBMS_OUTPUT.PUT_LINE(p_label || ': FAIL (got ' || SQLCODE || ': ' || SQLERRM || ')');
    END IF;
    ROLLBACK;
  END;
BEGIN
  -- pick sample orders
  SELECT MIN(Order_ID) INTO v_open FROM Orders WHERE Statues = 'Open';
  SELECT MIN(Order_ID) INTO v_paid FROM Orders WHERE Statues = 'Paid';
  SELECT MIN(Item_ID)  INTO v_item FROM Order_Items WHERE Order_id_fk = v_paid;

  -- 1) totals engine
  pkg_pricing.order_totals(v_open, s, d, g, q, t);
  DBMS_OUTPUT.PUT_LINE('T1 totals(order ' || v_open || '): subtotal=' || s ||
    ' volDisc=' || d || ' gst=' || g || ' qst=' || q || ' TOTAL=' || t ||
    '  (cash-rounded: ' || CASE WHEN MOD(ROUND(t*100), 5) = 0 THEN 'OK' ELSE 'FAIL' END || ')');

  -- 2) stock rejection (ORA-20001)
  expect_err('T2 stock reject',
    'INSERT INTO Order_Items (Item_ID, Order_id_fk, Product_id_fk, Quantity, Unit_Price, Total_Price) ' ||
    'VALUES (item_seq.NEXTVAL, ' || v_open || ', (SELECT MIN(Product_ID) FROM Products), 99999, 10, 999990)',
    -20001);

  -- 3) line-freeze guard on a non-Open order (ORA-20004)
  expect_err('T3 line freeze',
    'UPDATE Order_Items SET Quantity = Quantity + 1 WHERE Item_ID = ' || v_item,
    -20004);

  -- 4) illegal status transition (ORA-20002)
  expect_err('T4 bad transition',
    'BEGIN pkg_orders.set_status(' || v_paid || ', ''Confirmed''); END;',
    -20002);

  -- 5) cancellation requires a reason (ORA-20003)
  expect_err('T5 cancel needs reason',
    'BEGIN pkg_orders.set_status(' || v_open || ', ''Cancelled''); END;',
    -20003);

  -- 6) happy hour: force window open, compare a Drinks price, restore
  SELECT Product_ID, Price INTO v_drink, v_base
    FROM (SELECT p.Product_ID, p.Price
            FROM Products p JOIN Categories c ON c.Category_ID = p.Category_ID_fk
           WHERE c.Category_Name = 'Drinks' ORDER BY p.Product_ID)
   WHERE ROWNUM = 1;
  UPDATE Pricing_Config SET Param_Value = '0'  WHERE Param_Name = 'HAPPY_HOUR_START';
  UPDATE Pricing_Config SET Param_Value = '24' WHERE Param_Name = 'HAPPY_HOUR_END';
  v_hh := pkg_pricing.line_unit_price(v_drink);
  DBMS_OUTPUT.PUT_LINE('T6 happy hour: base=' || v_base || ' hhPrice=' || v_hh ||
    '  (' || CASE WHEN v_hh = ROUND(v_base * 0.8, 2) THEN 'OK -20%' ELSE 'FAIL' END || ')');
  UPDATE Pricing_Config SET Param_Value = '15' WHERE Param_Name = 'HAPPY_HOUR_START';
  UPDATE Pricing_Config SET Param_Value = '18' WHERE Param_Name = 'HAPPY_HOUR_END';
  -- outside the window now (unless it IS 15-18 UTC): just show the current price
  DBMS_OUTPUT.PUT_LINE('T6b price now (window 15-18): ' || pkg_pricing.line_unit_price(v_drink));
  COMMIT;

  -- 7) legal full lifecycle on a fresh order: Open -> Confirmed -> Ready -> Paid
  DECLARE v_id NUMBER; v_pay NUMBER;
  BEGIN
    INSERT INTO Orders (Order_ID, Customer_ID, Employee_ID, Order_Type, Statues)
    VALUES (ORDER_SEQ.NEXTVAL, (SELECT MIN(Customer_ID) FROM Customers),
            (SELECT MIN(Employee_ID) FROM Employees), 'Dine-in', 'Open')
    RETURNING Order_ID INTO v_id;
    INSERT INTO Order_Items (Item_ID, Order_id_fk, Product_id_fk, Quantity, Unit_Price, Total_Price)
    VALUES (item_seq.NEXTVAL, v_id, v_drink, 6, v_base, 6 * v_base); -- 6 => tier-1 volume discount
    pkg_orders.set_status(v_id, 'Confirmed');
    pkg_orders.set_status(v_id, 'Ready');
    pkg_orders.set_status(v_id, 'Paid', p_pay_method => 'Card');
    SELECT COUNT(*) INTO v_pay FROM Payments WHERE Order_id_fk = v_id;
    SELECT Final_Amount INTO s FROM Orders WHERE Order_ID = v_id;
    DBMS_OUTPUT.PUT_LINE('T7 lifecycle order ' || v_id ||
      ': status=Paid finalAmount=' || s || ' paymentRows=' || v_pay ||
      '  (' || CASE WHEN v_pay = 1 AND s > 0 THEN 'OK' ELSE 'FAIL' END || ')');
    COMMIT;
  END;
END;
/
EXIT;
