import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../environments/environment';

// Modern "after" of the APEX Opportunities CRM "Account Details" page.
// Lists EBA_SALES_CUSTOMERS (the same table the legacy APEX app uses)
// and edits a record through the .NET API, which enforces the recovered APEX
// validations server-side. This is the AI-migrated counterpart of the live APEX
// legacy app — before/after on identical data.

interface Account {
  id: string;
  customerName: string;
  tags?: string;
  customerWebSite?: string;
  customerLinkedin?: string;
  customerFacebook?: string;
  customerTwitter?: string;
  customerTerritoryId?: string;
}

interface Territory { id: string; name: string; }

@Component({
  selector: 'app-accounts',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="acc-shell">
      <div class="topbar">
        <div class="left">
          <div class="mark">M</div>
          <div class="title">Opportunities CRM <small>Account Details · migrated from Oracle APEX</small></div>
        </div>
        <div class="tag">AI-migrated "after" · Angular + .NET → Oracle</div>
      </div>

      <div class="wrap">
        <div class="grid">
          <!-- list -->
          <div class="panel list">
            <div class="p-head">
              <h2>Accounts <span class="count">{{ accounts.length }}</span></h2>
              <input class="search" [(ngModel)]="search" (input)="load()" placeholder="Search name or tags…" />
            </div>
            <div class="rows">
              <button class="row" *ngFor="let a of accounts"
                      [class.sel]="selected?.id === a.id" (click)="edit(a)">
                <span class="nm">{{ a.customerName }}</span>
                <span class="tg" *ngIf="a.tags">{{ a.tags }}</span>
              </button>
            </div>
          </div>

          <!-- editor -->
          <div class="panel edit" *ngIf="model">
            <div class="p-head"><h2>{{ model.id ? 'Edit account #' + model.id : 'New account' }}</h2></div>
            <label>Customer name
              <input [(ngModel)]="model.customerName" (blur)="checkName()" />
            </label>
            <label>Territory <span class="req">*</span>
              <select [(ngModel)]="model.customerTerritoryId">
                <option [ngValue]="undefined">— select a territory —</option>
                <option *ngFor="let t of territories" [ngValue]="t.id">{{ t.name }}</option>
              </select>
            </label>
            <label>Tags
              <input [(ngModel)]="model.tags" placeholder="space-separated tags" />
            </label>
            <label>Website
              <input [(ngModel)]="model.customerWebSite" placeholder="http://…" />
            </label>
            <label>LinkedIn
              <input [(ngModel)]="model.customerLinkedin" placeholder="http://…" />
            </label>
            <label>Facebook
              <input [(ngModel)]="model.customerFacebook" placeholder="http://…" />
            </label>
            <label>Twitter
              <input [(ngModel)]="model.customerTwitter" placeholder="http://…" />
            </label>

            <div class="errors" *ngIf="errors.length">
              <div class="err" *ngFor="let e of errors">⚠ {{ e }}</div>
            </div>
            <div class="ok" *ngIf="saved">✓ Saved to Oracle</div>

            <div class="actions">
              <button class="save" (click)="save()">Save</button>
              <button class="new" (click)="newAccount()">+ New</button>
            </div>
            <p class="hint">Try tags with a <code>#</code> or <code>/</code>, or a URL without "http" —
              the same APEX validations (recovered by the pipeline) fire server-side.</p>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .acc-shell{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a;background:#f4f5f7;min-height:100vh}
    .topbar{display:flex;justify-content:space-between;align-items:center;background:#0a1929;color:#fff;padding:14px 24px}
    .left{display:flex;align-items:center;gap:12px}
    .mark{background:#146eb4;font-weight:700;width:38px;height:38px;border-radius:6px;display:grid;place-items:center}
    .title{font-size:18px;font-weight:600}.title small{display:block;font-size:11px;color:#9fb3c8;font-weight:400}
    .tag{font-size:12px;color:#9fb3c8}
    .wrap{padding:24px;max-width:1200px;margin:0 auto}
    .grid{display:grid;grid-template-columns:340px 1fr;gap:20px}
    .panel{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:18px}
    .p-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
    .p-head h2{font-size:15px;margin:0}.count{background:#eef;border-radius:10px;padding:1px 8px;font-size:12px;margin-left:6px}
    .search{border:1px solid #d0d7de;border-radius:6px;padding:6px 8px;font-size:13px;width:150px}
    .rows{display:flex;flex-direction:column;gap:2px;max-height:65vh;overflow:auto}
    .row{text-align:left;border:0;background:transparent;padding:9px 10px;border-radius:6px;cursor:pointer;display:flex;flex-direction:column;gap:2px;color:#1a1a1a;font-family:inherit}
    .row:hover{background:#f0f3f6}.row.sel{background:#e8f0fe}
    .nm{font-weight:600;font-size:14px;color:#1a1a1a}.row.sel .nm{color:#0a1929}
    .tg{font-size:11px;color:#6a737d}
    .edit label{display:block;font-size:12px;color:#57606a;margin-bottom:12px;font-weight:600}
    .edit input,.edit select{display:block;width:100%;box-sizing:border-box;border:1px solid #d0d7de;border-radius:6px;padding:8px 10px;margin-top:4px;font-size:14px;color:#111;font-weight:400;background:#fff}
    .req{color:#146eb4}
    .errors{margin:10px 0}.err{background:#fde8e8;color:#a61b1b;padding:7px 10px;border-radius:6px;font-size:13px;margin-bottom:4px}
    .ok{background:#e6f4ea;color:#1e7e34;padding:7px 10px;border-radius:6px;font-size:13px;margin:10px 0}
    .actions{display:flex;gap:8px;margin-top:8px}
    .save{background:#146eb4;color:#fff;border:0;border-radius:6px;padding:9px 18px;font-weight:600;cursor:pointer}
    .new{background:#eef1f4;border:0;border-radius:6px;padding:9px 14px;cursor:pointer;color:#1a1a1a;font-weight:600}
    .hint{font-size:12px;color:#6a737d;margin-top:14px}.hint code{background:#eef;padding:1px 5px;border-radius:4px}
  `],
})
export class AccountsComponent implements OnInit {
  private http = inject(HttpClient);
  private base = environment.apiBaseUrl;

  accounts: Account[] = [];
  territories: Territory[] = [];
  selected: Account | null = null;
  model: Account | null = null;
  errors: string[] = [];
  saved = false;
  search = '';

  ngOnInit() {
    this.load();
    this.http.get<Territory[]>(`${this.base}/api/accounts/territories`).subscribe(t => (this.territories = t));
    this.newAccount();
  }

  load() {
    const q = this.search ? `?search=${encodeURIComponent(this.search)}` : '';
    this.http.get<Account[]>(`${this.base}/api/accounts${q}`).subscribe(a => (this.accounts = a));
  }

  edit(a: Account) {
    this.selected = a;
    this.model = { ...a };
    this.errors = []; this.saved = false;
  }

  newAccount() {
    this.selected = null;
    this.model = { id: '', customerName: '' };
    this.errors = []; this.saved = false;
  }

  // Live NOT_EXISTS check, exactly like the APEX on-blur validation.
  checkName() {
    if (!this.model?.customerName) return;
    const ex = this.model.id ? `&excludeId=${this.model.id}` : '';
    this.http.get<{ available: boolean; message?: string }>(
      `${this.base}/api/accounts/validate-name?customerName=${encodeURIComponent(this.model.customerName)}${ex}`
    ).subscribe(r => {
      this.errors = r.available ? [] : [r.message || 'An account with that name already exists.'];
    });
  }

  save() {
    if (!this.model) return;
    this.errors = []; this.saved = false;
    const body = { ...this.model };
    const req = this.model.id
      ? this.http.put(`${this.base}/api/accounts/${this.model.id}`, body)
      : this.http.post(`${this.base}/api/accounts`, body);
    req.subscribe({
      next: () => { this.saved = true; this.load(); },
      error: (e) => { this.errors = e?.error?.errors ?? ['Save failed.']; },
    });
  }
}
