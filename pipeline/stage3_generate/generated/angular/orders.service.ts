import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

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
}