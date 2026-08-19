using System;
using System.Collections.Generic;
using System.Data;
using System.Linq;
using System.Threading.Tasks;
using Dapper;
using Oracle.ManagedDataAccess.Client;

namespace Sample.Orders
{
    /// <summary>
    /// Thin gateway service over the authoritative Oracle schema for the ORDERS module.
    /// Replicates the legacy Oracle Forms behaviour exactly (PHASE 1 - REPLICATE):
    ///   - ORDER_ID assigned from ORDER_SEQ.NEXTVAL on insert (PRE-INSERT / PRE-FORM).
    ///   - Line TOTAL_PRICE = NVL(QUANTITY,0)*NVL(UNIT_PRICE,0) (WHEN-VALIDATE-ITEM).
    ///   - Master delete blocked when detail ORDER_ITEMS exist (ON-CHECK-DELETE-MASTER).
    /// </summary>
    public sealed class OrderService
    {
        // Exact legacy message from ON-CHECK-DELETE-MASTER.
        public const string CannotDeleteMasterMessage =
            "Cannot delete master record when matching detail records exist.";

        private readonly string _connectionString;

        public OrderService(string connectionString)
        {
            _connectionString = connectionString
                ?? throw new ArgumentNullException(nameof(connectionString));
        }

        private OracleConnection CreateConnection()
        {
            var conn = new OracleConnection(_connectionString);
            conn.Open();
            return conn;
        }

        // ---------------------------------------------------------------------
        // ORDERS (master)
        // ---------------------------------------------------------------------

        public async Task<Order> GetByIdAsync(decimal orderId)
        {
            const string sql = @"
SELECT ORDER_ID       AS OrderId,
       ORDER_DATA     AS OrderData,
       CUSTOMER_ID    AS CustomerId,
       EMPLOYEE_ID    AS EmployeeId,
       TOTAL_AMOUNT   AS TotalAmount,
       TABLE_NUMBER   AS TableNumber,
       ORDER_TYPE     AS OrderType,
       DISCOUNT       AS Discount,
       FINAL_AMOUNT   AS FinalAmount,
       STATUES        AS Statues
  FROM ORDERS
 WHERE ORDER_ID = :OrderId";

            using var conn = CreateConnection();
            var order = await conn.QuerySingleOrDefaultAsync<Order>(
                sql, new { OrderId = orderId }).ConfigureAwait(false);

            if (order != null)
            {
                order.Items = (await GetItemsInternalAsync(conn, orderId)
                    .ConfigureAwait(false)).ToList();
            }

            return order;
        }

        public async Task<IReadOnlyList<Order>> GetAllAsync()
        {
            const string sql = @"
SELECT ORDER_ID       AS OrderId,
       ORDER_DATA     AS OrderData,
       CUSTOMER_ID    AS CustomerId,
       EMPLOYEE_ID    AS EmployeeId,
       TOTAL_AMOUNT   AS TotalAmount,
       TABLE_NUMBER   AS TableNumber,
       ORDER_TYPE     AS OrderType,
       DISCOUNT       AS Discount,
       FINAL_AMOUNT   AS FinalAmount,
       STATUES        AS Statues
  FROM ORDERS
 ORDER BY ORDER_ID";

            using var conn = CreateConnection();
            var orders = (await conn.QueryAsync<Order>(sql).ConfigureAwait(false)).ToList();
            return orders;
        }

        /// <summary>
        /// Inserts a new order. ORDER_ID is always assigned from ORDER_SEQ.NEXTVAL,
        /// replicating the legacy PRE-INSERT / PRE-FORM triggers. Any client-supplied
        /// ORDER_ID is ignored. Detail line TOTAL_PRICE values are recomputed.
        /// </summary>
        public async Task<decimal> CreateAsync(Order order)
        {
            if (order == null) throw new ArgumentNullException(nameof(order));

            using var conn = CreateConnection();
            using var tx = conn.BeginTransaction();

            var newId = await conn.ExecuteScalarAsync<decimal>(
                "SELECT ORDER_SEQ.NEXTVAL FROM DUAL",
                transaction: tx).ConfigureAwait(false);

            order.OrderId = newId;

            const string insertSql = @"
INSERT INTO ORDERS
    (ORDER_ID, ORDER_DATA, CUSTOMER_ID, EMPLOYEE_ID, TOTAL_AMOUNT,
     TABLE_NUMBER, ORDER_TYPE, DISCOUNT, FINAL_AMOUNT, STATUES)
VALUES
    (:OrderId, NVL(:OrderData, SYSDATE), :CustomerId, :EmployeeId, :TotalAmount,
     :TableNumber, :OrderType, :Discount, :FinalAmount, :Statues)";

            await conn.ExecuteAsync(insertSql, new
            {
                order.OrderId,
                order.OrderData,
                order.CustomerId,
                order.EmployeeId,
                order.TotalAmount,
                order.TableNumber,
                order.OrderType,
                order.Discount,
                order.FinalAmount,
                order.Statues
            }, tx).ConfigureAwait(false);

            if (order.Items != null)
            {
                foreach (var item in order.Items)
                {
                    item.OrderIdFk = newId;
                    await InsertItemInternalAsync(conn, tx, item).ConfigureAwait(false);
                }
            }

            tx.Commit();
            return newId;
        }

        /// <summary>
        /// Updates the mutable columns of an existing order. ORDER_ID is the immutable key.
        /// </summary>
        public async Task UpdateAsync(Order order)
        {
            if (order == null) throw new ArgumentNullException(nameof(order));

            const string sql = @"
UPDATE ORDERS
   SET ORDER_DATA   = :OrderData,
       CUSTOMER_ID  = :CustomerId,
       EMPLOYEE_ID  = :EmployeeId,
       TOTAL_AMOUNT = :TotalAmount,
       TABLE_NUMBER = :TableNumber,
       ORDER_TYPE   = :OrderType,
       DISCOUNT     = :Discount,
       FINAL_AMOUNT = :FinalAmount,
       STATUES      = :Statues
 WHERE ORDER_ID     = :OrderId";

            using var conn = CreateConnection();
            await conn.ExecuteAsync(sql, new
            {
                order.OrderData,
                order.CustomerId,
                order.EmployeeId,
                order.TotalAmount,
                order.TableNumber,
                order.OrderType,
                order.Discount,
                order.FinalAmount,
                order.Statues,
                order.OrderId
            }).ConfigureAwait(false);
        }

        /// <summary>
        /// Deletes a master order. Replicates ON-CHECK-DELETE-MASTER: if any matching
        /// ORDER_ITEMS detail records exist, the delete is blocked with the exact
        /// legacy message and no rows are removed.
        /// </summary>
        public async Task DeleteAsync(decimal orderId)
        {
            using var conn = CreateConnection();
            using var tx = conn.BeginTransaction();

            var detailCount = await conn.ExecuteScalarAsync<decimal>(
                "SELECT COUNT(*) FROM ORDER_ITEMS WHERE ORDER_ID_FK = :OrderId",
                new { OrderId = orderId }, tx).ConfigureAwait(false);

            if (detailCount > 0)
            {
                tx.Rollback();
                throw new InvalidOperationException(CannotDeleteMasterMessage);
            }

            await conn.ExecuteAsync(
                "DELETE FROM ORDERS WHERE ORDER_ID = :OrderId",
                new { OrderId = orderId }, tx).ConfigureAwait(false);

            tx.Commit();
        }

        // ---------------------------------------------------------------------
        // ORDER_ITEMS (detail)
        // ---------------------------------------------------------------------

        public async Task<IReadOnlyList<OrderItem>> GetItemsAsync(decimal orderId)
        {
            using var conn = CreateConnection();
            return (await GetItemsInternalAsync(conn, orderId).ConfigureAwait(false)).ToList();
        }

        /// <summary>
        /// Adds a detail line. TOTAL_PRICE is computed server-side as
        /// NVL(QUANTITY,0)*NVL(UNIT_PRICE,0) (WHEN-VALIDATE-ITEM). ITEM_ID from ITEM_SEQ.
        /// </summary>
        public async Task<decimal> AddItemAsync(OrderItem item)
        {
            if (item == null) throw new ArgumentNullException(nameof(item));

            using var conn = CreateConnection();
            using var tx = conn.BeginTransaction();

            var itemId = await InsertItemInternalAsync(conn, tx, item).ConfigureAwait(false);

            tx.Commit();
            return itemId;
        }

        /// <summary>
        /// Updates a detail line. TOTAL_PRICE is recomputed as
        /// NVL(QUANTITY,0)*NVL(UNIT_PRICE,0) (WHEN-VALIDATE-ITEM).
        /// </summary>
        public async Task UpdateItemAsync(OrderItem item)
        {
            if (item == null) throw new ArgumentNullException(nameof(item));

            item.TotalPrice = ComputeTotalPrice(item.Quantity, item.UnitPrice);

            const string sql = @"
UPDATE ORDER_ITEMS
   SET ORDER_ID_FK   = :OrderIdFk,
       PRODUCT_ID_FK = :ProductIdFk,
       QUANTITY      = :Quantity,
       UNIT_PRICE    = :UnitPrice,
       TOTAL_PRICE   = :TotalPrice
 WHERE ITEM_ID       = :ItemId";

            using var conn = CreateConnection();
            await conn.ExecuteAsync(sql, new
            {
                item.OrderIdFk,
                item.ProductIdFk,
                item.Quantity,
                item.UnitPrice,
                item.TotalPrice,
                item.ItemId
            }).ConfigureAwait(false);
        }

        public async Task DeleteItemAsync(decimal itemId)
        {
            using var conn = CreateConnection();
            await conn.ExecuteAsync(
                "DELETE FROM ORDER_ITEMS WHERE ITEM_ID = :ItemId",
                new { ItemId = itemId }).ConfigureAwait(false);
        }

        // ---------------------------------------------------------------------
        // Internal helpers
        // ---------------------------------------------------------------------

        private static async Task<IEnumerable<OrderItem>> GetItemsInternalAsync(
            IDbConnection conn, decimal orderId)
        {
            const string sql = @"
SELECT ITEM_ID       AS ItemId,
       ORDER_ID_FK   AS OrderIdFk,
       PRODUCT_ID_FK AS ProductIdFk,
       QUANTITY      AS Quantity,
       UNIT_PRICE    AS UnitPrice,
       TOTAL_PRICE   AS TotalPrice
  FROM ORDER_ITEMS
 WHERE ORDER_ID_FK = :OrderId
 ORDER BY ITEM_ID";

            return await conn.QueryAsync<OrderItem>(sql, new { OrderId = orderId })
                .ConfigureAwait(false);
        }

        private static async Task<decimal> InsertItemInternalAsync(
            IDbConnection conn, IDbTransaction tx, OrderItem item)
        {
            item.TotalPrice = ComputeTotalPrice(item.Quantity, item.UnitPrice);

            var itemId = await conn.ExecuteScalarAsync<decimal>(
                "SELECT ITEM_SEQ.NEXTVAL FROM DUAL",
                transaction: tx).ConfigureAwait(false);

            item.ItemId = itemId;

            const string sql = @"
INSERT INTO ORDER_ITEMS
    (ITEM_ID, ORDER_ID_FK, PRODUCT_ID_FK, QUANTITY, UNIT_PRICE, TOTAL_PRICE)
VALUES
    (:ItemId, :OrderIdFk, :ProductIdFk, :Quantity, :UnitPrice, :TotalPrice)";

            await conn.ExecuteAsync(sql, new
            {
                item.ItemId,
                item.OrderIdFk,
                item.ProductIdFk,
                item.Quantity,
                item.UnitPrice,
                item.TotalPrice
            }, tx).ConfigureAwait(false);

            return itemId;
        }

        /// <summary>
        /// Replicates WHEN-VALIDATE-ITEM: TOTAL_PRICE := nvl(QUANTITY,0)*nvl(UNIT_PRICE,0).
        /// </summary>
        private static decimal ComputeTotalPrice(decimal? quantity, decimal? unitPrice)
        {
            return (quantity ?? 0m) * (unitPrice ?? 0m);
        }
    }

    // -------------------------------------------------------------------------
    // DTOs mirroring the authoritative schema
    // -------------------------------------------------------------------------

    public sealed class Order
    {
        public decimal OrderId { get; set; }
        public DateTime? OrderData { get; set; }
        public decimal? CustomerId { get; set; }
        public decimal? EmployeeId { get; set; }
        public decimal? TotalAmount { get; set; }
        public decimal? TableNumber { get; set; }
        public string OrderType { get; set; }
        public decimal? Discount { get; set; }
        public decimal? FinalAmount { get; set; }
        public string Statues { get; set; }

        public List<OrderItem> Items { get; set; } = new List<OrderItem>();
    }

    public sealed class OrderItem
    {
        public decimal ItemId { get; set; }
        public decimal? OrderIdFk { get; set; }
        public decimal? ProductIdFk { get; set; }
        public decimal? Quantity { get; set; }
        public decimal? UnitPrice { get; set; }
        public decimal? TotalPrice { get; set; }
    }
}