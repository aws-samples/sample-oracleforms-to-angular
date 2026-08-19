using System;
using System.Collections.Generic;

namespace Sample.Orders
{
    /// <summary>
    /// Master DTO representing a row of the ORDERS table together with its
    /// ORDER_ITEMS detail records (master-detail relation ORDERS_ORDER_ITEMS).
    /// Column names/types mirror the authoritative Oracle DDL.
    /// </summary>
    public sealed record OrderDto
    {
        /// <summary>ORDERS.ORDER_ID (NUMBER, PK, sequence Ord_seq).</summary>
        public decimal OrderId { get; init; }

        /// <summary>ORDERS.ORDER_DATA (DATE DEFAULT SYSDATE).</summary>
        public DateTime? OrderData { get; init; }

        /// <summary>ORDERS.CUSTOMER_ID (NUMBER, FK -> CUSTOMERS).</summary>
        public decimal? CustomerId { get; init; }

        /// <summary>ORDERS.EMPLOYEE_ID (NUMBER, FK -> EMPLOYEES).</summary>
        public decimal? EmployeeId { get; init; }

        /// <summary>ORDERS.TOTAL_AMOUNT (NUMBER(10,2)).</summary>
        public decimal? TotalAmount { get; init; }

        /// <summary>ORDERS.TABLE_NUMBER (NUMBER).</summary>
        public decimal? TableNumber { get; init; }

        /// <summary>ORDERS.ORDER_TYPE (VARCHAR2(50)).</summary>
        public string? OrderType { get; init; }

        /// <summary>ORDERS.DISCOUNT (NUMBER(10,2)).</summary>
        public decimal? Discount { get; init; }

        /// <summary>ORDERS.FINAL_AMOUNT (NUMBER(10,2)).</summary>
        public decimal? FinalAmount { get; init; }

        /// <summary>ORDERS.STATUES (VARCHAR2(50)) — legacy column spelling preserved.</summary>
        public string? Statues { get; init; }

        /// <summary>Detail block ORDER_ITEMS for this order.</summary>
        public IReadOnlyList<OrderItemDto> Items { get; init; } = new List<OrderItemDto>();
    }

    /// <summary>
    /// Detail DTO representing a row of the ORDER_ITEMS table
    /// (FK ORDER_ID_FK -> ORDERS, FK PRODUCT_ID_FK -> PRODUCTS).
    /// </summary>
    public sealed record OrderItemDto
    {
        /// <summary>ORDER_ITEMS.ITEM_ID (NUMBER, PK, sequence item_seq).</summary>
        public decimal ItemId { get; init; }

        /// <summary>ORDER_ITEMS.ORDER_ID_FK (NUMBER, FK -> ORDERS.ORDER_ID).</summary>
        public decimal? OrderIdFk { get; init; }

        /// <summary>ORDER_ITEMS.PRODUCT_ID_FK (NUMBER, FK -> PRODUCTS.PRODUCT_ID).</summary>
        public decimal? ProductIdFk { get; init; }

        /// <summary>ORDER_ITEMS.QUANTITY (NUMBER NOT NULL).</summary>
        public decimal Quantity { get; init; }

        /// <summary>ORDER_ITEMS.UNIT_PRICE (NUMBER(8,2)).</summary>
        public decimal? UnitPrice { get; init; }

        /// <summary>
        /// ORDER_ITEMS.TOTAL_PRICE (NUMBER(10,2)).
        /// WHEN-VALIDATE-ITEM rule: TOTAL_PRICE = NVL(QUANTITY,0) * NVL(UNIT_PRICE,0).
        /// </summary>
        public decimal? TotalPrice { get; init; }
    }

    /// <summary>
    /// Request DTO for creating a new order (master + details).
    /// ORDER_ID is assigned server-side from Ord_seq.NEXTVAL (PRE-INSERT),
    /// so it is NOT accepted from the client.
    /// </summary>
    public sealed record CreateOrderRequest
    {
        /// <summary>ORDERS.ORDER_DATA — DATE DEFAULT SYSDATE when null.</summary>
        public DateTime? OrderData { get; init; }

        /// <summary>ORDERS.CUSTOMER_ID (FK -> CUSTOMERS).</summary>
        public decimal? CustomerId { get; init; }

        /// <summary>ORDERS.EMPLOYEE_ID (FK -> EMPLOYEES).</summary>
        public decimal? EmployeeId { get; init; }

        /// <summary>ORDERS.TOTAL_AMOUNT (NUMBER(10,2)).</summary>
        public decimal? TotalAmount { get; init; }

        /// <summary>ORDERS.TABLE_NUMBER (NUMBER).</summary>
        public decimal? TableNumber { get; init; }

        /// <summary>ORDERS.ORDER_TYPE (VARCHAR2(50)).</summary>
        public string? OrderType { get; init; }

        /// <summary>ORDERS.DISCOUNT (NUMBER(10,2)).</summary>
        public decimal? Discount { get; init; }

        /// <summary>ORDERS.FINAL_AMOUNT (NUMBER(10,2)).</summary>
        public decimal? FinalAmount { get; init; }

        /// <summary>ORDERS.STATUES (VARCHAR2(50)) — legacy column spelling preserved.</summary>
        public string? Statues { get; init; }

        /// <summary>Detail rows for ORDER_ITEMS to be inserted with this order.</summary>
        public IReadOnlyList<CreateOrderItemRequest> Items { get; init; } = new List<CreateOrderItemRequest>();
    }

    /// <summary>
    /// Request DTO for creating a new detail row in ORDER_ITEMS.
    /// ITEM_ID is assigned server-side from item_seq.NEXTVAL,
    /// ORDER_ID_FK is bound to the owning order (master-detail relation).
    /// </summary>
    public sealed record CreateOrderItemRequest
    {
        /// <summary>ORDER_ITEMS.PRODUCT_ID_FK (FK -> PRODUCTS.PRODUCT_ID).</summary>
        public decimal? ProductIdFk { get; init; }

        /// <summary>ORDER_ITEMS.QUANTITY (NUMBER NOT NULL).</summary>
        public decimal Quantity { get; init; }

        /// <summary>ORDER_ITEMS.UNIT_PRICE (NUMBER(8,2)).</summary>
        public decimal? UnitPrice { get; init; }

        /// <summary>
        /// ORDER_ITEMS.TOTAL_PRICE (NUMBER(10,2)).
        /// If not supplied, gateway recomputes as NVL(QUANTITY,0) * NVL(UNIT_PRICE,0).
        /// </summary>
        public decimal? TotalPrice { get; init; }
    }

    /// <summary>
    /// Request DTO for updating an existing order (master + details).
    /// ORDER_ID identifies the master row; it is not modifiable.
    /// </summary>
    public sealed record UpdateOrderRequest
    {
        /// <summary>ORDERS.ORDER_ID (NUMBER, PK) — target master row.</summary>
        public decimal OrderId { get; init; }

        /// <summary>ORDERS.ORDER_DATA (DATE).</summary>
        public DateTime? OrderData { get; init; }

        /// <summary>ORDERS.CUSTOMER_ID (FK -> CUSTOMERS).</summary>
        public decimal? CustomerId { get; init; }

        /// <summary>ORDERS.EMPLOYEE_ID (FK -> EMPLOYEES).</summary>
        public decimal? EmployeeId { get; init; }

        /// <summary>ORDERS.TOTAL_AMOUNT (NUMBER(10,2)).</summary>
        public decimal? TotalAmount { get; init; }

        /// <summary>ORDERS.TABLE_NUMBER (NUMBER).</summary>
        public decimal? TableNumber { get; init; }

        /// <summary>ORDERS.ORDER_TYPE (VARCHAR2(50)).</summary>
        public string? OrderType { get; init; }

        /// <summary>ORDERS.DISCOUNT (NUMBER(10,2)).</summary>
        public decimal? Discount { get; init; }

        /// <summary>ORDERS.FINAL_AMOUNT (NUMBER(10,2)).</summary>
        public decimal? FinalAmount { get; init; }

        /// <summary>ORDERS.STATUES (VARCHAR2(50)) — legacy column spelling preserved.</summary>
        public string? Statues { get; init; }

        /// <summary>Detail rows for ORDER_ITEMS to be synchronized with this order.</summary>
        public IReadOnlyList<UpdateOrderItemRequest> Items { get; init; } = new List<UpdateOrderItemRequest>();
    }

    /// <summary>
    /// Request DTO for updating/inserting a detail row in ORDER_ITEMS.
    /// A null or zero ItemId indicates a new detail row (item_seq.NEXTVAL assigned).
    /// </summary>
    public sealed record UpdateOrderItemRequest
    {
        /// <summary>ORDER_ITEMS.ITEM_ID (NUMBER, PK). Null/0 => new detail row.</summary>
        public decimal? ItemId { get; init; }

        /// <summary>ORDER_ITEMS.ORDER_ID_FK (FK -> ORDERS.ORDER_ID).</summary>
        public decimal? OrderIdFk { get; init; }

        /// <summary>ORDER_ITEMS.PRODUCT_ID_FK (FK -> PRODUCTS.PRODUCT_ID).</summary>
        public decimal? ProductIdFk { get; init; }

        /// <summary>ORDER_ITEMS.QUANTITY (NUMBER NOT NULL).</summary>
        public decimal Quantity { get; init; }

        /// <summary>ORDER_ITEMS.UNIT_PRICE (NUMBER(8,2)).</summary>
        public decimal? UnitPrice { get; init; }

        /// <summary>
        /// ORDER_ITEMS.TOTAL_PRICE (NUMBER(10,2)).
        /// If not supplied, gateway recomputes as NVL(QUANTITY,0) * NVL(UNIT_PRICE,0).
        /// </summary>
        public decimal? TotalPrice { get; init; }
    }
}