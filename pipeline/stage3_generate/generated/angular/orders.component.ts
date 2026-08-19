import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { OrdersService } from './orders.service';

export interface OrderItem {
  itemId: number | null;
  orderIdFk: number | null;
  productIdFk: number | null;
  quantity: number | null;
  unitPrice: number | null;
  totalPrice: number | null;
}

export interface Order {
  orderId: number | null;
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

@Component({
  selector: 'app-orders',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './orders.component.html',
})
export class OrdersComponent implements OnInit {
  private readonly ordersService = inject(OrdersService);

  // Master block records (ORDERS) — navigated like the Forms runtime.
  orders: Order[] = [];
  currentIndex = 0;

  // Detail block records (ORDER_ITEMS) for the current master.
  items: OrderItem[] = [];

  // Status message mirroring Forms MESSAGE() output.
  statusMessage = '';

  // Tracks whether the current master record is a freshly created (unsaved) row.
  private newRecord = false;

  ngOnInit(): void {
    // PRE-FORM: allocate a sequence value for a starting blank order.
    this.loadAllOrders(true);
  }

  private loadAllOrders(startBlank: boolean): void {
    this.ordersService.getOrders().subscribe({
      next: (data) => {
        this.orders = data ?? [];
        if (startBlank || this.orders.length === 0) {
          // Emulate PRE-FORM: begin on a new blank record with a reserved ORDER_ID.
          this.createRecord();
        } else {
          this.currentIndex = 0;
          this.newRecord = false;
          this.populateDetails();
        }
      },
      error: () => {
        this.orders = [];
        this.createRecord();
      },
    });
  }

  get currentOrder(): Order | null {
    return this.orders.length > 0 ? this.orders[this.currentIndex] : null;
  }

  // ON-POPULATE-DETAILS (ORDERS): query ORDER_ITEMS for the current master.
  private populateDetails(): void {
    const order = this.currentOrder;
    if (order && order.orderId != null && !this.newRecord) {
      this.ordersService.getOrderItems(order.orderId).subscribe({
        next: (data) => {
          this.items = data ?? [];
        },
        error: () => {
          this.items = [];
        },
      });
    } else {
      this.items = [];
    }
  }

  // WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY):
  // TOTAL_PRICE := nvl(QUANTITY,0) * nvl(UNIT_PRICE,0)
  recomputeLineTotal(item: OrderItem): void {
    const qty = item.quantity ?? 0;
    const price = item.unitPrice ?? 0;
    item.totalPrice = qty * price;
  }

  // Detail grid: add a blank line item.
  addItem(): void {
    const order = this.currentOrder;
    this.items.push({
      itemId: null,
      orderIdFk: order ? order.orderId : null,
      productIdFk: null,
      quantity: null,
      unitPrice: null,
      totalPrice: null,
    });
  }

  removeItem(index: number): void {
    if (index >= 0 && index < this.items.length) {
      this.items.splice(index, 1);
    }
  }

  // WHEN-BUTTON-PRESSED: CREATE_RECORD — a new blank master with reserved ORDER_ID.
  createRecord(): void {
    this.ordersService.nextOrderId().subscribe({
      next: (nextId) => {
        const blank: Order = {
          orderId: nextId,
          orderData: null,
          customerId: null,
          employeeId: null,
          totalAmount: null,
          tableNumber: null,
          orderType: null,
          discount: null,
          finalAmount: null,
          statues: null,
        };
        this.orders.push(blank);
        this.currentIndex = this.orders.length - 1;
        this.newRecord = true;
        this.items = [];
      },
      error: () => {
        const blank: Order = {
          orderId: null,
          orderData: null,
          customerId: null,
          employeeId: null,
          totalAmount: null,
          tableNumber: null,
          orderType: null,
          discount: null,
          finalAmount: null,
          statues: null,
        };
        this.orders.push(blank);
        this.currentIndex = this.orders.length - 1;
        this.newRecord = true;
        this.items = [];
      },
    });
  }

  // WHEN-BUTTON-PRESSED: FIRST_RECORD
  firstRecord(): void {
    if (this.orders.length === 0) {
      return;
    }
    this.currentIndex = 0;
    this.newRecord = false;
    this.populateDetails();
  }

  // WHEN-BUTTON-PRESSED: LAST_RECORD
  lastRecord(): void {
    if (this.orders.length === 0) {
      return;
    }
    this.currentIndex = this.orders.length - 1;
    this.newRecord = false;
    this.populateDetails();
  }

  // WHEN-BUTTON-PRESSED: NEXT_RECORD
  nextRecord(): void {
    if (this.orders.length === 0) {
      return;
    }
    if (this.currentIndex < this.orders.length - 1) {
      this.currentIndex++;
      this.newRecord = false;
      this.populateDetails();
    }
  }

  // WHEN-BUTTON-PRESSED: PREVIOUS_RECORD
  previousRecord(): void {
    if (this.orders.length === 0) {
      return;
    }
    if (this.currentIndex > 0) {
      this.currentIndex--;
      this.newRecord = false;
      this.populateDetails();
    }
  }

  // WHEN-BUTTON-PRESSED: COMMIT_FORM
  save(): void {
    const order = this.currentOrder;
    if (!order) {
      return;
    }

    // PRE-INSERT (ORDERS): ensure ORDER_ID is populated from order_seq for new rows.
    const persist = () => {
      const payload = {
        order,
        items: this.items,
      };
      this.ordersService.saveOrder(payload).subscribe({
        next: (saved) => {
          if (saved && saved.order) {
            this.orders[this.currentIndex] = saved.order;
            this.items = saved.items ?? this.items;
          }
          this.newRecord = false;
          // FORM_SUCCESS branch.
          this.statusMessage = '!';
        },
        error: () => {
          // ELSE branch of the commit trigger.
          this.statusMessage = '';
        },
      });
    };

    if (this.newRecord && order.orderId == null) {
      this.ordersService.nextOrderId().subscribe({
        next: (nextId) => {
          order.orderId = nextId;
          persist();
        },
        error: () => {
          this.statusMessage = '';
        },
      });
    } else {
      persist();
    }
  }

  // WHEN-BUTTON-PRESSED: DELETE_RECORD; COMMIT_FORM;
  // ON-CHECK-DELETE-MASTER (ORDERS): block delete when detail rows exist.
  deleteRecord(): void {
    const order = this.currentOrder;
    if (!order) {
      return;
    }

    if (this.newRecord || order.orderId == null) {
      // Unsaved master — just remove it locally.
      this.removeCurrentMasterLocally();
      return;
    }

    this.ordersService.hasOrderItems(order.orderId).subscribe({
      next: (hasDetails) => {
        if (hasDetails) {
          // ON-CHECK-DELETE-MASTER: matching detail records exist.
          this.statusMessage =
            'Cannot delete master record when matching detail records exist.';
          return;
        }
        this.ordersService.deleteOrder(order.orderId as number).subscribe({
          next: () => {
            this.removeCurrentMasterLocally();
          },
          error: () => {
            this.statusMessage = '';
          },
        });
      },
      error: () => {
        this.statusMessage = '';
      },
    });
  }

  private removeCurrentMasterLocally(): void {
    if (this.orders.length === 0) {
      return;
    }
    this.orders.splice(this.currentIndex, 1);
    if (this.orders.length === 0) {
      this.createRecord();
      return;
    }
    if (this.currentIndex >= this.orders.length) {
      this.currentIndex = this.orders.length - 1;
    }
    this.newRecord = false;
    this.populateDetails();
  }

  // WHEN-BUTTON-PRESSED: EXIT_FORM(NO_VALIDATE)
  exit(): void {
    this.statusMessage = '';
    // In the migrated shell, exit is handled by the router/host container.
  }

  // BLOCK7.ITEM12: CALL_FORM(categories_form) — preserved as a navigation stub.
  openCategoriesForm(): void {
    // Original: CALL_FORM('D:\dp_project\categories_form.fmx');
  }

  trackByIndex(index: number): number {
    return index;
  }
}