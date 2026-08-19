----TABLE EL CATEGORIES :-

CREATE TABLE Categories (
    Category_ID NUMBER PRIMARY KEY ,
    Category_Name VARCHAR2(100) NOT NULL,
    Descriptions VARCHAR2(255)
);

CREATE SEQUENCE cat_seq START WITH 1 INCREMENT BY 1;

----TABLE EL CUSTOMERS :-

CREATE TABLE Customers(
    Customer_ID NUMBER PRIMARY KEY,
    Name VARCHAR2(100) NOT NULL,
    Phone VARCHAR2(15),
    Register_Data DATE DEFAULT SYSDATE
);

CREATE SEQUENCE cust_seq START WITH 1 INCREMENT BY 1;

----TABLE EL EMPLOYEES :-

CREATE TABLE Employees (
    Employee_ID NUMBER PRIMARY KEY,
    Name VARCHAR2(100) NOT NULL,
    phone VARCHAR2(15),
    Role VARCHAR2(60),
    Salary NUMBER(10,2)
);

CREATE SEQUENCE emp_seq START WITH 1 INCREMENT BY 1;

----TABLE EL PRODUCTS :-

CREATE TABLE Products(
    Product_ID NUMBER PRIMARY KEY ,
    Name VARCHAR2(60) NOT NULL,
    Price NUMBER(8,2) NOT NULL,
    Category_ID_fk NUMBER,
    Cost NUMBER(8,2),
    Available VARCHAR2(20),
    CONSTRAINT fk_category FOREIGN KEY (Category_ID_fk) REFERENCES Categories(Category_ID)
);

CREATE SEQUENCE Prod_seq START WITH 1 INCREMENT BY 1;

----TABLE EL ORDERS :-

CREATE TABLE Orders(
    Order_ID NUMBER PRIMARY KEY,
    Order_Data DATE DEFAULT SYSDATE,
    Customer_ID NUMBER,
    Employee_ID NUMBER,
    Total_Amount NUMBER(10,2),
    Table_Number NUMBER,
    Order_Type VARCHAR2(50),
    Discount NUMBER(10,2),
    Final_Amount Number(10,2),
    Statues VARCHAR2(50),
    CONSTRAINT fk_cust FOREIGN KEY (Customer_ID) REFERENCES Customers(Customer_ID),
    CONSTRAINT fk_emp FOREIGN KEY (Employee_ID) REFERENCES Employees(Employee_ID)
);

CREATE SEQUENCE Ord_seq START WITH 1 INCREMENT BY 1;

----TABLE EL ORDERED ITEMS :-

CREATE TABLE Order_Items(
    Item_ID NUMBER PRIMARY KEY,
    Order_id_fk NUMBER,
    Product_id_fk number,
    Quantity NUMBER NOT NULL,
    Unit_Price NUMBER(8,2),
    Total_Price NUMBER(10,2),
    CONSTRAINT fk_order_link FOREIGN KEY (Order_id_fk) REFERENCES Orders(Order_id),
    CONSTRAINT fk_prod_link FOREIGN KEY (Product_id_fk) REFERENCES Products(Product_id)
);

CREATE SEQUENCE item_seq START WITH 1 INCREMENT BY 1;

--TABLE EL PAYMENTS :-

CREATE TABLE Payments(
    Payment_ID NUMBER PRIMARY KEY,
    Order_id_fk NUMBER,
    Payment_Method VARCHAR2(50),
    Amount_Payed NUMBER(10,2),
    Payment_Date DATE DEFAULT SYSDATE,
    CONSTRAINT fk_payment_order FOREIGN KEY (Order_id_fk) REFERENCES Orders(Order_id)
);

CREATE SEQUENCE pay_seq START WITH 1 INCREMENT BY 1;

SELECT table_name FROM user_tables;

