import { Routes } from '@angular/router';
import { AccountsComponent } from './accounts.component';
import { ReportGridComponent } from './report-grid.component';
import { OrdersComponent } from './orders.component';

export const routes: Routes = [
  { path: '', redirectTo: 'orders', pathMatch: 'full' },
  { path: 'orders', component: OrdersComponent },
  { path: 'accounts', component: AccountsComponent },
  { path: 'reports/:key', component: ReportGridComponent },
  { path: '**', redirectTo: 'orders' },
];
