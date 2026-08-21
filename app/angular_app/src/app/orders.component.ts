import { Component, OnInit, inject, ChangeDetectionStrategy } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { OrdersService, OrderTotalsDto } from './orders.service';

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

type Lang = 'en' | 'fr';

// UI chrome is bilingual; the field prompts keep the legacy English quirks
// ("Order Data", "Statues") in both languages, faithful to the source form.
const LABELS: Record<string, Record<Lang, string>> = {
  title:          { en: 'Orders Management', fr: 'Gestion des commandes' },
  orderHeader:    { en: 'Order Header', fr: 'En-tête de commande' },
  orderLines:     { en: 'Order Lines', fr: 'Lignes de commande' },
  next:           { en: 'NEXT', fr: 'SUIVANT' },
  previous:       { en: 'PREVIOUS', fr: 'PRÉCÉDENT' },
  addNew:         { en: 'ADD NEW', fr: 'AJOUTER' },
  delete:         { en: 'DELETE', fr: 'SUPPRIMER' },
  save:           { en: 'SAVE', fr: 'ENREGISTRER' },
  first:          { en: 'FIRST', fr: 'PREMIER' },
  last:           { en: 'LAST', fr: 'DERNIER' },
  addLine:        { en: 'ADD LINE', fr: 'AJOUTER LIGNE' },
  removeLine:     { en: 'Remove', fr: 'Retirer' },
  computeTotals:  { en: 'COMPUTE TOTALS', fr: 'CALCULER LES TOTAUX' },
  confirm:        { en: 'CONFIRM', fr: 'CONFIRMER' },
  markReady:      { en: 'MARK READY', fr: 'MARQUER PRÊT' },
  pay:            { en: 'PAY', fr: 'PAYER' },
  cancelOrder:    { en: 'CANCEL ORDER', fr: 'ANNULER LA COMMANDE' },
  cancelReason:   { en: 'Cancel Reason', fr: "Motif d'annulation" },
  payMethod:      { en: 'Pay Method', fr: 'Mode de paiement' },
  subtotal:       { en: 'Subtotal', fr: 'Sous-total' },
  volumeDiscount: { en: 'Volume Discount', fr: 'Remise volume' },
  gst:            { en: 'GST', fr: 'TPS' },
  qst:            { en: 'QST', fr: 'TVQ' },
  totalDue:       { en: 'Total Due', fr: 'Total dû' },
  record:         { en: 'Record', fr: 'Enregistrement' },
  newRecord:      { en: '(new)', fr: '(nouveau)' },
  saved:          { en: 'Order saved successfully.', fr: 'Commande enregistrée avec succès.' },
  saveFailed:     { en: 'Could not save the order - check the data and try again.',
                    fr: "Impossible d'enregistrer la commande - vérifiez les données et réessayez." },
  saveFirst:      { en: 'Save the order first.', fr: "Enregistrez d'abord la commande." },
  nowStatus:      { en: 'Order {id} is now {status}.', fr: 'La commande {id} est maintenant {status}.' },
};

// The legacy PL/SQL raises hardcoded ENGLISH messages (ORA-20001..-20006);
// the modern app localizes them by error code — the migration talking point.
const ORA_MESSAGES: Record<number, Record<Lang, string>> = {
  20001: { en: 'Insufficient stock for this product.', fr: 'Stock insuffisant pour ce produit.' },
  20002: { en: 'Invalid status transition.', fr: 'Transition de statut invalide.' },
  20003: { en: 'A cancellation reason is required.', fr: "Un motif d'annulation est requis." },
  20004: { en: 'Order lines can only be modified while the order is Open.',
           fr: 'Les lignes ne sont modifiables que lorsque la commande est Open.' },
  20005: { en: 'Unknown product id.', fr: 'Produit inconnu.' },
  20006: { en: 'Unknown order id.', fr: 'Commande inconnue.' },
};

@Component({
    selector: 'app-orders',
    imports: [FormsModule],
    changeDetection: ChangeDetectionStrategy.Eager,
    templateUrl: './orders.component.html'
})
export class OrdersComponent implements OnInit {
  private readonly ordersService = inject(OrdersService);

  // Master block records (ORDERS) — navigated like the Forms runtime.
  orders: Order[] = [];
  currentIndex = 0;

  // Detail block records (ORDER_ITEMS) for the current master.
  items: OrderItem[] = [];

  // Lifecycle panel state (CTRL block in the v2 form).
  totals: OrderTotalsDto | null = null;
  cancelReason = '';
  payMethod = 'Cash';

  // Status message mirroring Forms MESSAGE() output.
  statusMessage = '';

  lang: Lang = 'en';

  orderTypes = ['Takeaway', 'Delivery', 'Dine-in'];
  payMethods = ['Cash', 'Card', 'Online'];

  // Tracks whether the current master record is a freshly created (unsaved) row.
  private newRecord = false;

  t(key: string): string {
    return LABELS[key]?.[this.lang] ?? key;
  }

  toggleLang(): void {
    this.lang = this.lang === 'en' ? 'fr' : 'en';
  }

  ngOnInit(): void {
    // WHEN-NEW-FORM-INSTANCE (v2 form): open on the saved orders, first record.
    this.loadAllOrders();
  }

  private loadAllOrders(): void {
    this.ordersService.getOrders().subscribe({
      next: (data) => {
        this.orders = data ?? [];
        if (this.orders.length === 0) {
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

  get isNewRecord(): boolean {
    return this.newRecord;
  }

  // ON-POPULATE-DETAILS (ORDERS) + WHEN-NEW-RECORD-INSTANCE (clear CTRL totals).
  private populateDetails(): void {
    this.totals = null;
    this.statusMessage = '';
    const order = this.currentOrder;
    if (order && order.orderId != null && !this.newRecord) {
      this.ordersService.getOrderItems(order.orderId).subscribe({
        next: (data) => (this.items = data ?? []),
        error: () => (this.items = []),
      });
    } else {
      this.items = [];
    }
  }

  // WHEN-VALIDATE-ITEM (ORDER_ITEMS.PRODUCT_ID_FK): effective price via pkg_pricing.
  onProductChange(item: OrderItem): void {
    if (item.productIdFk == null) {
      return;
    }
    this.ordersService.getUnitPrice(item.productIdFk).subscribe({
      next: (price) => {
        item.unitPrice = price;
        this.recomputeLineTotal(item);
      },
      error: (err) => this.showBusinessError(err),
    });
  }

  // WHEN-VALIDATE-ITEM (ORDER_ITEMS.QUANTITY).
  recomputeLineTotal(item: OrderItem): void {
    item.totalPrice = (item.quantity ?? 0) * (item.unitPrice ?? 0);
  }

  addItem(): void {
    const order = this.currentOrder;
    this.items.push({
      itemId: null,
      orderIdFk: order ? order.orderId : null,
      productIdFk: null,
      quantity: 1, // v2 form: quantity defaults to 1
      unitPrice: null,
      totalPrice: null,
    });
  }

  removeItem(index: number): void {
    if (index < 0 || index >= this.items.length) {
      return;
    }
    const item = this.items[index];
    const order = this.currentOrder;
    if (item.itemId != null && order?.orderId != null) {
      this.ordersService.deleteOrderItem(order.orderId, item.itemId).subscribe({
        next: () => this.items.splice(index, 1),
        error: (err) => this.showBusinessError(err),
      });
    } else {
      this.items.splice(index, 1);
    }
  }

  // CREATE_RECORD — ORDER_ID is server-assigned at save (PRE-INSERT), and the
  // v2 form initializes STATUES as Open so the lifecycle works on new orders.
  createRecord(): void {
    this.orders.push({
      orderId: null,
      orderData: null,
      customerId: null,
      employeeId: null,
      totalAmount: null,
      tableNumber: null,
      orderType: null,
      discount: null,
      finalAmount: null,
      statues: 'Open',
    });
    this.currentIndex = this.orders.length - 1;
    this.newRecord = true;
    this.items = [];
    this.totals = null;
    this.statusMessage = '';
  }

  firstRecord(): void {
    if (!this.orders.length) return;
    this.currentIndex = 0;
    this.newRecord = false;
    this.populateDetails();
  }

  lastRecord(): void {
    if (!this.orders.length) return;
    this.currentIndex = this.orders.length - 1;
    this.newRecord = false;
    this.populateDetails();
  }

  nextRecord(): void {
    if (this.currentIndex < this.orders.length - 1) {
      this.currentIndex++;
      this.newRecord = false;
      this.populateDetails();
    }
  }

  previousRecord(): void {
    if (this.currentIndex > 0) {
      this.currentIndex--;
      this.newRecord = false;
      this.populateDetails();
    }
  }

  // COMMIT_FORM: persist master + details together.
  save(): void {
    const order = this.currentOrder;
    if (!order) return;
    this.ordersService.saveOrder({ order, items: this.items }).subscribe({
      next: (saved) => {
        if (saved?.order) {
          this.orders[this.currentIndex] = saved.order as Order;
          this.items = (saved.items as OrderItem[]) ?? this.items;
        }
        this.newRecord = false;
        this.statusMessage = this.t('saved');
      },
      error: (err) => this.showBusinessError(err, this.t('saveFailed')),
    });
  }

  deleteRecord(): void {
    const order = this.currentOrder;
    if (!order) return;
    if (this.newRecord || order.orderId == null) {
      this.removeCurrentMasterLocally();
      return;
    }
    this.ordersService.deleteOrder(order.orderId).subscribe({
      next: () => this.removeCurrentMasterLocally(),
      error: (err) => {
        // ON-CHECK-DELETE-MASTER: 409 with the exact legacy message.
        const msg = err?.error?.message;
        this.statusMessage = msg || this.t('saveFailed');
      },
    });
  }

  private removeCurrentMasterLocally(): void {
    if (!this.orders.length) return;
    this.orders.splice(this.currentIndex, 1);
    if (!this.orders.length) {
      this.createRecord();
      return;
    }
    if (this.currentIndex >= this.orders.length) {
      this.currentIndex = this.orders.length - 1;
    }
    this.newRecord = false;
    this.populateDetails();
  }

  // ---- CTRL panel: Tier-1 business rules via pkg_pricing / pkg_orders ------

  computeTotals(): void {
    const order = this.currentOrder;
    if (!order) return;
    if (this.newRecord || order.orderId == null) {
      this.statusMessage = this.t('saveFirst');
      return;
    }
    this.ordersService.getTotals(order.orderId).subscribe({
      next: (t) => {
        this.totals = t;
        this.statusMessage = '';
      },
      error: (err) => this.showBusinessError(err),
    });
  }

  confirmOrder(): void  { this.applyStatus('Confirmed'); }
  markReady(): void     { this.applyStatus('Ready'); }
  payOrder(): void      { this.applyStatus('Paid'); }
  cancelOrder(): void   { this.applyStatus('Cancelled'); }

  private applyStatus(status: string): void {
    const order = this.currentOrder;
    if (!order) return;
    if (this.newRecord || order.orderId == null) {
      this.statusMessage = this.t('saveFirst');
      return;
    }
    this.ordersService
      .setStatus(order.orderId, {
        status,
        reason: status === 'Cancelled' ? this.cancelReason : null,
        payMethod: status === 'Paid' ? this.payMethod : null,
      })
      .subscribe({
        next: (res) => {
          if (res?.order) {
            this.orders[this.currentIndex] = res.order as Order;
          }
          this.statusMessage = this.t('nowStatus')
            .replace('{id}', String(order.orderId))
            .replace('{status}', status);
          if (status === 'Confirmed') this.computeTotals();
        },
        error: (err) => this.showBusinessError(err),
      });
  }

  // Localize legacy ORA-2000x errors by code; keep the raw English legacy
  // message as the detail line, exactly as recovered from the PL/SQL.
  private showBusinessError(err: any, fallback?: string): void {
    const code: number | undefined = err?.error?.code;
    const raw: string | undefined = err?.error?.message;
    const localized = code ? ORA_MESSAGES[code]?.[this.lang] : undefined;
    if (localized) {
      this.statusMessage = raw && raw !== localized ? `${localized} — ${raw}` : localized;
    } else {
      this.statusMessage = raw || fallback || this.t('saveFailed');
    }
  }
}
