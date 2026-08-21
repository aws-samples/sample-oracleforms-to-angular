import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';

export interface OrderDto {
  orderId: number;
  orderData: string | null;
  customerId: number | null;
  employeeId: number | null;
  totalAmount: number | null;
  tableNumber: number | null;
  orderType: string | null;
  discount: number | null;
  finalAmount: number | null;
  statues: string | null;
}

export interface OrderItemDto {
  itemId: number;
  orderIdFk: number | null;
  productIdFk: number | null;
  quantity: number;
  unitPrice: number | null;
  totalPrice: number | null;
}

export interface CreateOrderDto {
  orderData: string | null;
  customerId: number | null;
  employeeId: number | null;
  totalAmount: number | null;
  tableNumber: number | null;
  orderType: string | null;
  discount: number | null;
  finalAmount: number | null;
  statues: string | null;
}

export interface UpdateOrderDto {
  orderId: number;
  orderData: string | null;
  customerId: number | null;
  employeeId: number | null;
  totalAmount: number | null;
  tableNumber: number | null;
  orderType: string | null;
  discount: number | null;
  finalAmount: number | null;
  statues: string | null;
}

export interface CreateOrderItemDto {
  orderIdFk: number | null;
  productIdFk: number | null;
  quantity: number;
  unitPrice: number | null;
  totalPrice: number | null;
}

export interface UpdateOrderItemDto {
  itemId: number;
  orderIdFk: number | null;
  productIdFk: number | null;
  quantity: number;
  unitPrice: number | null;
  totalPrice: number | null;
}

export interface OrderWithItemsDto {
  order: OrderDto;
  items: OrderItemDto[];
}

export interface NextSequenceDto {
  orderId: number;
}

export interface CommitResultDto {
  success: boolean;
  message: string | null;
  order?: OrderDto;
  items?: OrderItemDto[];
}

export interface OrderTotalsDto {
  subtotal: number;
  discount: number;
  gst: number;
  qst: number;
  total: number;
}

export interface StatusChangeDto {
  status: string;
  reason?: string | null;
  payMethod?: string | null;
}

@Injectable({ providedIn: 'root' })
export class OrdersService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/orders';

  getOrders(): Observable<OrderDto[]> {
    return this.http.get<OrderDto[]>(this.baseUrl);
  }

  getOrder(orderId: number): Observable<OrderDto> {
    return this.http.get<OrderDto>(`${this.baseUrl}/${orderId}`);
  }

  getOrderWithItems(orderId: number): Observable<OrderWithItemsDto> {
    return this.http.get<OrderWithItemsDto>(`${this.baseUrl}/${orderId}/with-items`);
  }

  // PRE-FORM / PRE-INSERT: SELECT order_seq.NEXTVAL INTO :ORDERS.ORDER_ID FROM DUAL
  getNextOrderId(): Observable<NextSequenceDto> {
    return this.http.get<NextSequenceDto>(`${this.baseUrl}/next-id`);
  }

  createOrder(dto: CreateOrderDto): Observable<OrderDto> {
    return this.http.post<OrderDto>(this.baseUrl, dto);
  }

  updateOrder(dto: UpdateOrderDto): Observable<OrderDto> {
    return this.http.put<OrderDto>(`${this.baseUrl}/${dto.orderId}`, dto);
  }

  // ON-CHECK-DELETE-MASTER: guarded server-side against existing ORDER_ITEMS
  deleteOrder(orderId: number): Observable<CommitResultDto> {
    return this.http.delete<CommitResultDto>(`${this.baseUrl}/${orderId}`);
  }

  // ON-POPULATE-DETAILS: query detail block ORDER_ITEMS for a master ORDER_ID
  getOrderItems(orderId: number): Observable<OrderItemDto[]> {
    return this.http.get<OrderItemDto[]>(`${this.baseUrl}/${orderId}/items`);
  }

  getOrderItem(orderId: number, itemId: number): Observable<OrderItemDto> {
    return this.http.get<OrderItemDto>(`${this.baseUrl}/${orderId}/items/${itemId}`);
  }

  createOrderItem(orderId: number, dto: CreateOrderItemDto): Observable<OrderItemDto> {
    return this.http.post<OrderItemDto>(`${this.baseUrl}/${orderId}/items`, dto);
  }

  updateOrderItem(orderId: number, dto: UpdateOrderItemDto): Observable<OrderItemDto> {
    return this.http.put<OrderItemDto>(`${this.baseUrl}/${orderId}/items/${dto.itemId}`, dto);
  }

  deleteOrderItem(orderId: number, itemId: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/${orderId}/items/${itemId}`);
  }

  // WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY):
  // TOTAL_PRICE := nvl(QUANTITY,0) * nvl(UNIT_PRICE,0)
  computeItemTotalPrice(quantity: number | null, unitPrice: number | null): number {
    return (quantity ?? 0) * (unitPrice ?? 0);
  }

  // COMMIT_FORM equivalent: persist master + details in a single transaction
  commitOrder(payload: OrderWithItemsDto): Observable<CommitResultDto> {
    return this.http.post<CommitResultDto>(`${this.baseUrl}/commit`, payload);
  }

  searchOrders(criteria: Partial<OrderDto>): Observable<OrderDto[]> {
    let params = new HttpParams();
    Object.entries(criteria).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        params = params.set(key, String(value));
      }
    });
    return this.http.get<OrderDto[]>(`${this.baseUrl}/search`, { params });
  }

  // ---- Tier-1 business rules (pkg_pricing / pkg_orders via the thin API) ----

  // pkg_pricing.order_totals
  getTotals(orderId: number): Observable<OrderTotalsDto> {
    return this.http.get<OrderTotalsDto>(`${this.baseUrl}/${orderId}/totals`);
  }

  // pkg_orders.set_status (Open -> Confirmed -> Ready -> Paid / Cancelled)
  setStatus(orderId: number, change: StatusChangeDto): Observable<{ success: boolean; order: OrderDto }> {
    return this.http.post<{ success: boolean; order: OrderDto }>(`${this.baseUrl}/${orderId}/status`, change);
  }

  // pkg_pricing.line_unit_price (happy-hour aware)
  getUnitPrice(productId: number): Observable<number> {
    return this.http
      .get<{ productId: number; unitPrice: number }>(`${this.baseUrl}/price/${productId}`)
      .pipe(map(d => d.unitPrice));
  }

  // ---- compatibility wrappers expected by orders.component.ts ----
  nextOrderId(): Observable<number> {
    return this.getNextOrderId().pipe(map(d => d.orderId));
  }

  hasOrderItems(orderId: number): Observable<boolean> {
    return this.getOrderItems(orderId).pipe(map(items => (items?.length ?? 0) > 0));
  }

  saveOrder(payload: any): Observable<OrderWithItemsDto> {
    const order = (payload && payload.order) ? payload.order : payload;
    const items = (payload && payload.items) ? payload.items : [];
    // commit returns the persisted master + details (ids are server-assigned)
    return this.commitOrder({ order, items } as OrderWithItemsDto).pipe(
      map(res => ({ order: (res.order ?? order) as OrderDto, items: res.items ?? items }))
    );
  }

}
