import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { environment } from '../../environments/environment';

interface ReportColumn {
  key: string;
  label: string;
  sortable: boolean;
  type: 'number' | 'text' | 'date';
}

interface ReportData {
  columns: ReportColumn[];
  rows: Array<Record<string, unknown>>;
}

type SortDir = 'asc' | 'desc';

@Component({
  selector: 'app-countries-report',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="countries-report">
      <h1>Countries</h1>

      <div *ngIf="loading" class="report-loading">Loading…</div>
      <div *ngIf="error" class="report-error">{{ error }}</div>

      <table *ngIf="data && !loading" class="report-table">
        <thead>
          <tr>
            <th *ngFor="let col of data.columns"
                [class.sortable]="col.sortable"
                [class.sorted-asc]="sortKey === col.key && sortDir === 'asc'"
                [class.sorted-desc]="sortKey === col.key && sortDir === 'desc'"
                (click)="onHeaderClick(col)">
              {{ col.label }}
              <span *ngIf="sortKey === col.key" class="sort-indicator">
                {{ sortDir === 'asc' ? '▲' : '▼' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let row of data.rows">
            <td *ngFor="let col of data.columns"
                [ngClass]="'col-type-' + col.type">
              <ng-container [ngSwitch]="col.type">
                <span *ngSwitchCase="'date'">{{ row[col.key] | date:'medium' }}</span>
                <span *ngSwitchCase="'number'">{{ row[col.key] }}</span>
                <span *ngSwitchDefault>{{ row[col.key] }}</span>
              </ng-container>
            </td>
          </tr>
          <tr *ngIf="data.rows.length === 0">
            <td [attr.colspan]="data.columns.length">No data found.</td>
          </tr>
        </tbody>
      </table>
    </div>
  `
})
export class CountriesReportComponent implements OnInit {
  private readonly apiUrl = `${environment.apiBaseUrl}/api/reports/countries`;

  data: ReportData | null = null;
  loading = false;
  error: string | null = null;

  sortKey: string | null = null;
  sortDir: SortDir = 'asc';

  constructor(
    private readonly http: HttpClient,
    private readonly route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    const sort = qp.get('sort');
    const dir = qp.get('dir');
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

  private fetch(): void {
    this.loading = true;
    this.error = null;

    let params = new HttpParams();
    if (this.sortKey) {
      params = params.set('sort', this.sortKey).set('dir', this.sortDir);
    }

    this.http.get<ReportData>(this.apiUrl, { params }).subscribe({
      next: (res) => {
        this.data = res;
        this.loading = false;
      },
      error: (err) => {
        this.error = 'Failed to load report.';
        this.loading = false;
        console.error('CountriesReportComponent fetch failed', err);
      }
    });
  }
}