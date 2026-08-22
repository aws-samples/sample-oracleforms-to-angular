using System;
using System.Data;
using System.Linq;
using System.Threading.Tasks;
using Dapper;
using Microsoft.AspNetCore.Mvc;
using Oracle.ManagedDataAccess.Client;
using ModernApi.Services;   // IDbConnectionFactory (shared Oracle factory)
using Sample.Orders;        // generated OrderService + Order/OrderItem models

namespace ModernApi.Controllers;

// Modern "after" of the legacy Oracle Forms ORDERS module (master ORDERS / detail ORDER_ITEMS).
// Uses the generated Sample.Orders.OrderService (business rules preserved) over the SAME Oracle
// schema the live Forms "before" runs on. Routes mirror the generated Angular OrdersService.
[ApiController]
[Route("api/orders")]
[Produces("application/json")]
public sealed class OrdersController : ControllerBase
{
    private readonly OrderService _svc;
    private readonly IDbConnectionFactory _factory;

    public OrdersController(OrderService svc, IDbConnectionFactory factory)
    {
        _svc = svc;
        _factory = factory;
    }

    [HttpGet]
    public async Task<IActionResult> GetOrders() => Ok(await _svc.GetAllAsync());

    [HttpGet("{orderId:long}")]
    public async Task<IActionResult> GetOrder(long orderId)
    {
        var o = await _svc.GetByIdAsync(orderId);
        return o is null ? NotFound() : Ok(o);
    }

    [HttpGet("{orderId:long}/with-items")]
    public async Task<IActionResult> GetWithItems(long orderId)
    {
        var o = await _svc.GetByIdAsync(orderId);
        if (o is null) return NotFound();
        return Ok(new { order = o, items = o.Items });
    }

    [HttpGet("{orderId:long}/items")]
    public async Task<IActionResult> GetItems(long orderId) => Ok(await _svc.GetItemsAsync(orderId));

    // PRE-FORM / PRE-INSERT: SELECT order_seq.NEXTVAL FROM DUAL
    [HttpGet("next-id")]
    public async Task<IActionResult> NextId()
    {
        using IDbConnection c = _factory.Create();
        var id = await c.ExecuteScalarAsync<decimal>("SELECT ORDER_SEQ.NEXTVAL FROM DUAL");
        return Ok(new { orderId = id });
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] Order order)
    {
        var id = await _svc.CreateAsync(order);
        var created = await _svc.GetByIdAsync(id);
        return CreatedAtAction(nameof(GetOrder), new { orderId = id }, created);
    }

    [HttpPut("{orderId:long}")]
    public async Task<IActionResult> Update(long orderId, [FromBody] Order order)
    {
        order.OrderId = orderId;
        await _svc.UpdateAsync(order);
        return Ok(await _svc.GetByIdAsync(orderId));
    }

    // ON-CHECK-DELETE-MASTER: blocked (409) when ORDER_ITEMS detail rows exist
    [HttpDelete("{orderId:long}")]
    public async Task<IActionResult> Delete(long orderId)
    {
        try
        {
            await _svc.DeleteAsync(orderId);
            return Ok(new { success = true, message = (string?)null });
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new { success = false, message = ex.Message });
        }
    }

    [HttpGet("{orderId:long}/items/{itemId:long}")]
    public async Task<IActionResult> GetItem(long orderId, long itemId)
    {
        var items = await _svc.GetItemsAsync(orderId);
        foreach (var it in items) if (it.ItemId == itemId) return Ok(it);
        return NotFound();
    }

    // Detail mutations hit the legacy DB triggers (line freeze ORA-20004,
    // stock guard ORA-20001) — surface them as 409 {code,message}.
    [HttpPost("{orderId:long}/items")]
    public async Task<IActionResult> AddItem(long orderId, [FromBody] OrderItem item)
    {
        try
        {
            item.OrderIdFk = orderId;
            var id = await _svc.AddItemAsync(item);
            item.ItemId = id;
            return Ok(item);
        }
        catch (OracleException ex) when (ex.Number is >= 20001 and <= 20006)
        {
            return Conflict(BusinessError(ex));
        }
    }

    [HttpPut("{orderId:long}/items/{itemId:long}")]
    public async Task<IActionResult> UpdateItem(long orderId, long itemId, [FromBody] OrderItem item)
    {
        try
        {
            item.OrderIdFk = orderId;
            item.ItemId = itemId;
            await _svc.UpdateItemAsync(item);
            return Ok(item);
        }
        catch (OracleException ex) when (ex.Number is >= 20001 and <= 20006)
        {
            return Conflict(BusinessError(ex));
        }
    }

    [HttpDelete("{orderId:long}/items/{itemId:long}")]
    public async Task<IActionResult> DeleteItem(long orderId, long itemId)
    {
        try
        {
            await _svc.DeleteItemAsync(itemId);
            return NoContent();
        }
        catch (OracleException ex) when (ex.Number is >= 20001 and <= 20006)
        {
            return Conflict(BusinessError(ex));
        }
    }

    // COMMIT_FORM: persist master + reconcile details in ONE database
    // transaction — items absent from the payload are deleted, and a
    // business-rule violation anywhere rolls the whole commit back.
    [HttpPost("commit")]
    public async Task<IActionResult> Commit([FromBody] CommitDto dto)
    {
        if (dto?.Order is null) return BadRequest(new { code = 0, message = "order is required" });
        try
        {
            var orderId = await _svc.CommitAsync(dto.Order, dto.Items);
            var saved = await _svc.GetByIdAsync(orderId);
            return Ok(new { success = true, message = "Saved.", order = saved, items = saved?.Items });
        }
        catch (OracleException ex) when (ex.Number is >= 20001 and <= 20006)
        {
            return Conflict(BusinessError(ex));
        }
    }

    // ---- Tier-1 business rules: pkg_pricing / pkg_orders (thin gateway) ----

    // pkg_pricing.order_totals: subtotal, volume discount, GST, QST, cash-rounded total
    [HttpGet("{orderId:long}/totals")]
    public async Task<IActionResult> Totals(long orderId) => Ok(await _svc.GetTotalsAsync(orderId));

    // pkg_orders.set_status: Open -> Confirmed -> Ready -> Paid / Cancelled.
    // Rule violations map ORA-20001..-20006 to 409 { code, message } — the
    // frontend localizes by code (legacy messages are hardcoded English).
    [HttpPost("{orderId:long}/status")]
    public async Task<IActionResult> SetStatus(long orderId, [FromBody] StatusChangeDto dto)
    {
        if (string.IsNullOrWhiteSpace(dto?.Status))
            return BadRequest(new { code = 0, message = "status is required" });
        try
        {
            await _svc.SetStatusAsync(orderId, dto.Status, dto.Reason, dto.PayMethod);
            var order = await _svc.GetByIdAsync(orderId);
            return Ok(new { success = true, order });
        }
        catch (OracleException ex) when (ex.Number is >= 20001 and <= 20006)
        {
            return Conflict(BusinessError(ex));
        }
    }

    // pkg_pricing.line_unit_price: effective (happy-hour aware) unit price
    [HttpGet("price/{productId:long}")]
    public async Task<IActionResult> Price(long productId)
    {
        try
        {
            var price = await _svc.GetUnitPriceAsync(productId);
            return Ok(new { productId, unitPrice = price });
        }
        catch (OracleException ex) when (ex.Number is >= 20001 and <= 20006)
        {
            return Conflict(BusinessError(ex));
        }
    }

    // EXECUTE_QUERY in enter-query mode: the client sends any OrderDto field
    // as an exact-match criterion. Filtered in memory over the (small) sample
    // dataset — no dynamic SQL.
    [HttpGet("search")]
    public async Task<IActionResult> Search(
        [FromQuery] long? orderId, [FromQuery] long? customerId,
        [FromQuery] long? employeeId, [FromQuery] long? tableNumber,
        [FromQuery] string? orderType, [FromQuery] string? statues)
    {
        var all = await _svc.GetAllAsync();
        var filtered = all.Where(o =>
            (orderId is null || o.OrderId == orderId) &&
            (customerId is null || o.CustomerId == customerId) &&
            (employeeId is null || o.EmployeeId == employeeId) &&
            (tableNumber is null || o.TableNumber == tableNumber) &&
            (orderType is null || string.Equals(o.OrderType, orderType, StringComparison.OrdinalIgnoreCase)) &&
            (statues is null || string.Equals(o.Statues, statues, StringComparison.OrdinalIgnoreCase)));
        return Ok(filtered);
    }

    // First message line without the "ORA-2000x: " prefix; code carried separately.
    private static object BusinessError(OracleException ex)
    {
        var line = ex.Message.Split('\n')[0].Trim();
        var colon = line.IndexOf(':');
        if (line.StartsWith("ORA-", StringComparison.Ordinal) && colon > 0)
            line = line[(colon + 1)..].Trim();
        return new { code = ex.Number, message = line };
    }
}

public sealed class CommitDto
{
    public Order? Order { get; set; }
    public System.Collections.Generic.List<OrderItem>? Items { get; set; }
}

public sealed class StatusChangeDto
{
    public string? Status { get; set; }
    public string? Reason { get; set; }
    public string? PayMethod { get; set; }
}
