using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace Sample.Orders
{
    /// <summary>
    /// Thin gateway controller replicating the legacy Oracle Forms ORDERS module.
    /// Master block = ORDERS, detail block = ORDER_ITEMS.
    /// Business rules are delegated to <see cref="IOrderService"/> and preserved exactly.
    /// </summary>
    [ApiController]
    [Route("api/orders")]
    [Produces("application/json")]
    public sealed class OrdersController : ControllerBase
    {
        private readonly IOrderService _orderService;
        private readonly ILogger<OrdersController> _logger;

        public OrdersController(IOrderService orderService, ILogger<OrdersController> logger)
        {
            _orderService = orderService ?? throw new ArgumentNullException(nameof(orderService));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        /// <summary>
        /// Query all ORDERS master records (default execute-query behaviour of the block).
        /// </summary>
        [HttpGet]
        [ProducesResponseType(typeof(IReadOnlyList<OrderDto>), StatusCodes.Status200OK)]
        public async Task<ActionResult<IReadOnlyList<OrderDto>>> GetOrders(CancellationToken cancellationToken)
        {
            var orders = await _orderService.GetOrdersAsync(cancellationToken).ConfigureAwait(false);
            return Ok(orders);
        }

        /// <summary>
        /// Fetch a single ORDERS master record by its ORDER_ID primary key.
        /// </summary>
        [HttpGet("{orderId:long}")]
        [ProducesResponseType(typeof(OrderDto), StatusCodes.Status200OK)]
        [ProducesResponseType(StatusCodes.Status404NotFound)]
        public async Task<ActionResult<OrderDto>> GetOrder(long orderId, CancellationToken cancellationToken)
        {
            var order = await _orderService.GetOrderAsync(orderId, cancellationToken).ConfigureAwait(false);
            if (order is null)
            {
                return NotFound();
            }

            return Ok(order);
        }

        /// <summary>
        /// ON-POPULATE-DETAILS (ORDERS): populate the ORDER_ITEMS detail block for the given master.
        /// Mirrors Query_Master_Details(rel_id, 'ORDER_ITEMS') when ORDER_ID is not null.
        /// </summary>
        [HttpGet("{orderId:long}/items")]
        [ProducesResponseType(typeof(IReadOnlyList<OrderItemDto>), StatusCodes.Status200OK)]
        public async Task<ActionResult<IReadOnlyList<OrderItemDto>>> GetOrderItems(long orderId, CancellationToken cancellationToken)
        {
            var items = await _orderService.GetOrderItemsAsync(orderId, cancellationToken).ConfigureAwait(false);
            return Ok(items);
        }

        /// <summary>
        /// Create a new ORDERS master record.
        /// PRE-INSERT (ORDERS) assigns ORDER_ID from order_seq.NEXTVAL inside the service.
        /// </summary>
        [HttpPost]
        [ProducesResponseType(typeof(OrderDto), StatusCodes.Status201Created)]
        public async Task<ActionResult<OrderDto>> CreateOrder([FromBody] OrderDto order, CancellationToken cancellationToken)
        {
            var created = await _orderService.CreateOrderAsync(order, cancellationToken).ConfigureAwait(false);
            return CreatedAtAction(nameof(GetOrder), new { orderId = created.OrderId }, created);
        }

        /// <summary>
        /// Update an existing ORDERS master record (COMMIT_FORM on an existing record).
        /// </summary>
        [HttpPut("{orderId:long}")]
        [ProducesResponseType(typeof(OrderDto), StatusCodes.Status200OK)]
        [ProducesResponseType(StatusCodes.Status404NotFound)]
        public async Task<ActionResult<OrderDto>> UpdateOrder(long orderId, [FromBody] OrderDto order, CancellationToken cancellationToken)
        {
            var updated = await _orderService.UpdateOrderAsync(orderId, order, cancellationToken).ConfigureAwait(false);
            if (updated is null)
            {
                return NotFound();
            }

            return Ok(updated);
        }

        /// <summary>
        /// Delete an ORDERS master record.
        /// ON-CHECK-DELETE-MASTER (ORDERS): if matching ORDER_ITEMS detail rows exist the delete is
        /// refused and the legacy message is returned as HTTP 409 Conflict.
        /// </summary>
        [HttpDelete("{orderId:long}")]
        [ProducesResponseType(StatusCodes.Status204NoContent)]
        [ProducesResponseType(StatusCodes.Status404NotFound)]
        [ProducesResponseType(typeof(ProblemDetails), StatusCodes.Status409Conflict)]
        public async Task<IActionResult> DeleteOrder(long orderId, CancellationToken cancellationToken)
        {
            try
            {
                var deleted = await _orderService.DeleteOrderAsync(orderId, cancellationToken).ConfigureAwait(false);
                if (!deleted)
                {
                    return NotFound();
                }

                return NoContent();
            }
            catch (MasterDetailDeleteException ex)
            {
                _logger.LogWarning(ex, "Delete of ORDER_ID {OrderId} blocked by existing ORDER_ITEMS detail rows.", orderId);
                return Conflict(new ProblemDetails
                {
                    Status = StatusCodes.Status409Conflict,
                    Title = "Delete blocked",
                    Detail = ex.Message
                });
            }
        }

        /// <summary>
        /// WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY):
        /// TOTAL_PRICE := nvl(QUANTITY,0) * nvl(UNIT_PRICE,0).
        /// Delegated to the service so the null-coalescing rule stays authoritative and identical.
        /// </summary>
        [HttpPost("items/validate-quantity")]
        [ProducesResponseType(typeof(OrderItemDto), StatusCodes.Status200OK)]
        public ActionResult<OrderItemDto> ValidateQuantity([FromBody] OrderItemDto item)
        {
            var validated = _orderService.ValidateQuantity(item);
            return Ok(validated);
        }
    }
}