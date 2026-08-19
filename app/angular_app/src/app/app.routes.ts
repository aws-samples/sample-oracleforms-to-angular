import { Routes } from '@angular/router';
import { AccountsComponent } from './accounts.component';
import { ReportGridComponent } from './report-grid.component';

export const routes: Routes = [
  { path: '', redirectTo: 'accounts', pathMatch: 'full' },
  { path: 'accounts', component: AccountsComponent },
  { path: 'reports/:key', component: ReportGridComponent },
  { path: '**', redirectTo: 'accounts' },
];
