import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { environment } from '../../environments/environment';

interface ReportColumn {
  key: string;
  label: string;
  sortable: boolean;
  type: 'number' | 'text' | 'bool' | 'date';
  hidden: boolean;
}

interface ReportData {
  columns: ReportColumn[];
  rows: Record<string, any>[];
}

type SortDir = 'asc' | 'desc';

@Component({
  selector: 'app-accounts-report',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="accounts-report">
      <h1>{{ title }}</h1>

      <div *ngIf="loading" class="report-loading">Loading…</div>
      <div *ngIf="error" class="report-error">{{ error }}</div>

      <table *ngIf="data && !loading" class="report-table">
        <thead>
          <tr>
            <th
              *ngFor="let col of visibleColumns"
              [class.sortable]="col.sortable"
              [class.sorted-asc]="sortKey === col.key && sortDir === 'asc'"
              [class.sorted-desc]="sortKey === col.key && sortDir === 'desc'"
              (click)="onHeaderClick(col)"
            >
              {{ col.label }}
              <span *ngIf="sortKey === col.key" class="sort-indicator">
                {{ sortDir === 'asc' ? '▲' : '▼' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let row of data.rows">
            <td *ngFor="let col of visibleColumns" [attr.data-type]="col.type">
              <ng-container [ngSwitch]="col.type">
                <span *ngSwitchCase="'bool'">
                  {{ formatBool(row[col.key]) }}
                </span>
                <span *ngSwitchCase="'date'">
                  {{ row[col.key] ? (row[col.key] | date: 'medium') : '' }}
                </span>
                <span *ngSwitchCase="'number'">
                  {{ row[col.key] }}
                </span>
                <span *ngSwitchDefault>
                  {{ row[col.key] }}
                </span>
              </ng-container>
            </td>
          </tr>
          <tr *ngIf="data.rows.length === 0">
            <td [attr.colspan]="visibleColumns.length" class="no-data">
              No data found.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `,
})
export class AccountsReportComponent implements OnInit {
  readonly title = 'Accounts';

  data: ReportData | null = null;
  visibleColumns: ReportColumn[] = [];
  loading = false;
  error: string | null = null;

  sortKey: string | null = null;
  sortDir: SortDir = 'asc';

  private readonly endpoint = `${environment.apiBaseUrl}/api/reports/accounts`;

  constructor(
    private readonly http: HttpClient,
    private readonly route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const sort = params.get('sort');
    const dir = params.get('dir');
    if (sort) {
      this.sortKey = sort;
      this.sortDir = dir === 'desc' ? 'desc' : 'asc';
    }
    this.fetch();
  }

  onHeaderClick(col: ReportColumn): void {
    if (!col.sortable) {
      return;
    }
    if (this.sortKey === col.key) {
      this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortKey = col.key;
      this.sortDir = 'asc';
    }
    this.fetch();
  }

  formatBool(value: any): string {
    if (value === null || value === undefined || value === '') {
      return '';
    }
    const truthy =
      value === true ||
      value === 1 ||
      value === '1' ||
      String(value).toUpperCase() === 'Y' ||
      String(value).toUpperCase() === 'YES' ||
      String(value).toUpperCase() === 'TRUE';
    return truthy ? 'Yes' : 'No';
  }

  private fetch(): void {
    this.loading = true;
    this.error = null;

    let url = this.endpoint;
    if (this.sortKey) {
      const query = `sort=${encodeURIComponent(this.sortKey)}&dir=${this.sortDir}`;
      url = `${this.endpoint}?${query}`;
    }

    this.http.get<ReportData>(url).subscribe({
      next: (res) => {
        this.data = res;
        this.visibleColumns = (res?.columns ?? []).filter((c) => !c.hidden);
        this.loading = false;
      },
      error: (err) => {
        this.error = 'Failed to load report.';
        this.loading = false;
        console.error('AccountsReportComponent fetch error', err);
      },
    });
  }
}