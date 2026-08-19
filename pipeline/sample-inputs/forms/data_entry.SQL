-- ADD CATEGORIES

INSERT INTO Categories VALUES (cat_seq.NEXTVAL, 'Drinks', 'Hot and Cold');

--ADD PRODUCTS

INSERT INTO Products (Product_ID, Name, Price, Category_ID_fk, Cost, Available) 
VALUES (prod_seq.NEXTVAL, 'Latte', 55.00, cat_seq.CURRVAL, 20.00, 'Yes');

-- ADD EMPLOYEES

INSERT INTO Employees VALUES (emp_seq.NEXTVAL, 'Sample Employee', '555-0101', 'Manager', 15000);

-- SAVE IT

COMMIT;