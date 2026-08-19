import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { environment } from '../environments/environment';

// Modern "after" of an APEX Interactive Report — rendered as a full SaaS-style
// application: left nav rail, top bar, a filter panel, and a responsive card grid
// (with a table toggle). Reads /api/reports/:key; the registry marks which columns
// are business-visible; cards surface the key metrics. Deliberately reads as a
// modern app, not a bare report — the point of the migration.

interface ReportColumn {
  key: string; label: string; sortable: boolean;
  type?: 'text' | 'number' | 'date' | 'bool'; hidden?: boolean;
}
interface ReportData { title: string; columns: ReportColumn[]; rows: Record<string, any>[]; }

@Component({
  selector: 'app-report-grid',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
  <div class="app" *ngIf="data as d">
    <!-- ── left nav rail ── -->
    <aside class="nav">
      <div class="logo"><div class="mark">M</div><span>Opportunities</span></div>
      <nav>
        <a class="item"><i>⌂</i> Home</a>
        <a class="item"><i>◎</i> Leads <b class="pill-n">16</b></a>
        <a class="item"><i>◈</i> Opportunities <b class="pill-n">19</b></a>
        <a class="item"><i>◍</i> Territories <b class="pill-n">12</b></a>
        <a class="item active"><i>◭</i> Accounts <b class="pill-n">{{ d.rows.length }}</b></a>
        <a class="item"><i>◑</i> Contacts</a>
        <a class="item"><i>▤</i> Products <b class="pill-n">12</b></a>
        <a class="item"><i>▦</i> Reports</a>
      </nav>
      <div class="nav-foot">migrated from Oracle APEX<br><b>Angular + .NET</b></div>
    </aside>

    <!-- ── main ── -->
    <div class="main">
      <header class="top">
        <h1>{{ d.title }}</h1>
        <div class="top-r">
          <div class="views">
            <button [class.on]="view==='cards'" (click)="view='cards'" title="Cards">▦</button>
            <button [class.on]="view==='table'" (click)="view='table'" title="Table">☰</button>
          </div>
          <button class="create">+ Create Account</button>
        </div>
      </header>

      <div class="body">
        <!-- filter rail -->
        <div class="filters">
          <div class="search">
            <svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z"/></svg>
            <input [(ngModel)]="q" (ngModelChange)="apply()" placeholder="Search Accounts" />
          </div>
          <label class="fl">Territory
            <select [(ngModel)]="fTerr" (ngModelChange)="apply()">
              <option value="">– All –</option>
              <option *ngFor="let t of territories" [value]="t">{{ t }}</option>
            </select>
          </label>
          <label class="fl">Key Accounts
            <select [(ngModel)]="fKey" (ngModelChange)="apply()">
              <option value="">– All –</option>
              <option value="Yes">Yes</option><option value="No">No</option>
            </select>
          </label>
          <label class="fl">Sort
            <select [(ngModel)]="sortSel" (ngModelChange)="applySort()">
              <option value="CUSTOMER_NAME">Account</option>
              <option value="OPEN_DEALS">Open Opportunities</option>
              <option value="LEADS">Leads</option>
              <option value="TERRITORY_NAME">Territory</option>
            </select>
          </label>
          <button class="reset" (click)="reset()">↺ Reset</button>
          <div class="fcount"><b>{{ view2.length }}</b> of {{ d.rows.length }} accounts</div>
        </div>

        <!-- CARD VIEW -->
        <div class="cards" *ngIf="view==='cards'">
          <article class="card" *ngFor="let r of view2; let i=index" [style.--accent]="accent(i)"
                   (click)="open(r)" tabindex="0" (keyup.enter)="open(r)">
            <div class="c-head">
              <h3>{{ r['CUSTOMER_NAME'] }}</h3>
              <span class="key" *ngIf="isYes(r['CUSTOMER_IS_KEY_ACCOUNT_YN'])">★ Key</span>
            </div>
            <div class="c-terr">{{ r['TERRITORY_NAME'] || '—' }}</div>
            <div class="c-metrics">
              <div class="m"><span class="mv" [class.z]="!r['OPEN_DEALS']">{{ r['OPEN_DEALS'] ?? 0 }}</span><span class="ml">Open</span></div>
              <div class="m"><span class="mv" [class.z]="!r['PAST_DUE']">{{ r['PAST_DUE'] ?? 0 }}</span><span class="ml">Past Due</span></div>
              <div class="m"><span class="mv" [class.z]="!r['LEADS']">{{ r['LEADS'] ?? 0 }}</span><span class="ml">Leads</span></div>
            </div>
            <div class="c-foot">Updated {{ fmtDate(r['UPDATED']) }} <span class="c-open">View →</span></div>
          </article>
          <div class="empty" *ngIf="!view2.length">No matching accounts</div>
        </div>

        <!-- TABLE VIEW -->
        <div class="card-wrap" *ngIf="view==='table'">
          <table>
            <thead><tr>
              <th *ngFor="let c of cols()" [class.num]="c.type==='number'"
                  [class.sortable]="c.sortable" [class.active]="sort===c.key"
                  (click)="c.sortable && sortBy(c.key)">
                {{ c.label }}<i class="arr" *ngIf="sort===c.key">{{ dir==='asc'?'↑':'↓' }}</i>
              </th>
            </tr></thead>
            <tbody>
              <tr *ngFor="let r of view2" (click)="open(r)" class="row-click">
                <td *ngFor="let c of cols()" [class.num]="c.type==='number'">
                  <ng-container [ngSwitch]="c.type">
                    <span *ngSwitchCase="'bool'" class="badge" [class.yes]="isYes(r[c.key])">{{ r[c.key] }}</span>
                    <span *ngSwitchCase="'number'" [class.z]="!r[c.key]">{{ r[c.key] ?? 0 }}</span>
                    <span *ngSwitchCase="'date'" class="mono">{{ fmtDate(r[c.key]) }}</span>
                    <span *ngSwitchDefault [class.strong]="c.key==='CUSTOMER_NAME'">{{ r[c.key] }}</span>
                  </ng-container>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── detail drawer (opens when an account is clicked, like APEX) ── -->
    <div class="scrim" *ngIf="sel" (click)="sel=null"></div>
    <aside class="drawer" *ngIf="sel as s" [class.open]="!!sel">
      <div class="d-head">
        <div>
          <div class="d-crumb">Accounts / Detail</div>
          <h2>{{ s['CUSTOMER_NAME'] }}</h2>
          <span class="key" *ngIf="isYes(s['CUSTOMER_IS_KEY_ACCOUNT_YN'])">★ Key Account</span>
        </div>
        <button class="d-close" (click)="sel=null">✕</button>
      </div>
      <div class="d-metrics">
        <div class="dm"><span class="dmv">{{ s['OPEN_DEALS'] ?? 0 }}</span><span class="dml">Open Opportunities</span></div>
        <div class="dm"><span class="dmv">{{ s['PAST_DUE'] ?? 0 }}</span><span class="dml">Past Due</span></div>
        <div class="dm"><span class="dmv">{{ s['LEADS'] ?? 0 }}</span><span class="dml">Leads</span></div>
      </div>
      <div class="d-fields">
        <div class="df" *ngFor="let c of detailCols()">
          <span class="dfl">{{ c.label }}</span>
          <span class="dfv" [class.strong]="c.key==='CUSTOMER_NAME'">
            <ng-container [ngSwitch]="c.type">
              <span *ngSwitchCase="'date'">{{ fmtDate(s[c.key]) }}</span>
              <span *ngSwitchCase="'bool'" class="badge" [class.yes]="isYes(s[c.key])">{{ s[c.key] }}</span>
              <span *ngSwitchDefault>{{ s[c.key] === null || s[c.key] === '' ? '—' : s[c.key] }}</span>
            </ng-container>
          </span>
        </div>
      </div>
      <div class="d-foot">Sourced live from Oracle · migrated from APEX Account Details (page 3)</div>
    </aside>
  </div>
  `,
  styles: [`
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');
    :host{--ink:#14171a;--muted:#6b7480;--line:#e7e9ec;--bg:#f4f5f7;--card:#fff;--accent:#146eb4;--navy:#0d1b2a;--navy2:#13293d;font-family:'IBM Plex Sans',sans-serif}
    *{box-sizing:border-box}
    .app{display:flex;min-height:100vh;background:var(--bg);color:var(--ink)}
    /* nav */
    .nav{width:230px;background:var(--navy);color:#c7d2dd;display:flex;flex-direction:column;flex-shrink:0}
    .logo{display:flex;align-items:center;gap:10px;padding:18px 18px;font-size:16px;font-weight:600;color:#fff;border-bottom:1px solid #1d3247}
    .mark{background:var(--accent);width:34px;height:34px;border-radius:7px;display:grid;place-items:center;font-weight:700;font-size:13px;color:#fff}
    nav{padding:10px 0;flex:1}
    .item{display:flex;align-items:center;gap:11px;padding:11px 20px;font-size:14px;color:#aeb9c5;cursor:pointer;border-left:3px solid transparent}
    .item i{font-style:normal;width:16px;text-align:center;opacity:.8}
    .item:hover{background:#132537;color:#fff}
    .item.active{background:#132537;color:#fff;border-left-color:var(--accent);font-weight:600}
    .pill-n{margin-left:auto;background:#20364b;color:#c7d2dd;font-size:11px;font-weight:600;padding:1px 8px;border-radius:10px}
    .nav-foot{padding:16px 20px;font-size:11px;color:#6b7d8f;border-top:1px solid #1d3247;line-height:1.5}
    .nav-foot b{color:#aeb9c5}
    /* main */
    .main{flex:1;min-width:0;display:flex;flex-direction:column}
    .top{display:flex;justify-content:space-between;align-items:center;padding:20px 30px;background:var(--card);border-bottom:1px solid var(--line)}
    .top h1{margin:0;font-size:26px;font-weight:600;letter-spacing:-.4px}
    .top-r{display:flex;align-items:center;gap:14px}
    .views{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
    .views button{border:0;background:#fff;padding:8px 12px;cursor:pointer;color:var(--muted);font-size:14px}
    .views button.on{background:var(--navy);color:#fff}
    .create{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 18px;font-weight:600;font-size:13.5px;cursor:pointer}
    .create:hover{background:#0d4a7a}
    .body{display:flex;gap:0;flex:1;align-items:stretch}
    /* filters */
    .filters{width:250px;flex-shrink:0;padding:22px 22px;border-right:1px solid var(--line);background:var(--card);display:flex;flex-direction:column;align-self:stretch}
    .search{display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:8px;padding:9px 11px;color:var(--muted);margin-bottom:20px}
    .search:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(20,110,180,.08)}
    .search input{border:0;outline:0;font:inherit;font-size:13.5px;width:100%;color:var(--ink)}
    .fl{display:block;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:16px}
    .fl select{display:block;width:100%;margin-top:6px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;font-size:13.5px;color:var(--ink);background:#fff;font-weight:400;text-transform:none;letter-spacing:0}
    .reset{background:#f0f1f3;border:0;border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer;color:var(--ink);font-weight:500}
    .fcount{margin-top:20px;font-size:12.5px;color:var(--muted)}.fcount b{color:var(--ink);font-weight:600}
    /* cards */
    .cards{flex:1;padding:24px 30px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;align-content:start}
    .card{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--accent,#146eb4);border-radius:11px;padding:18px 20px;box-shadow:0 1px 2px rgba(16,24,40,.04);transition:box-shadow .16s,transform .16s}
    .card:hover{box-shadow:0 10px 28px -14px rgba(16,24,40,.35);transform:translateY(-2px)}
    .c-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
    .c-head h3{margin:0;font-size:16px;font-weight:600;letter-spacing:-.2px;line-height:1.25}
    .key{flex-shrink:0;background:#fdeef0;color:var(--accent);font-size:11px;font-weight:600;padding:3px 9px;border-radius:20px;white-space:nowrap}
    .c-terr{font-size:13px;color:var(--muted);margin:6px 0 16px}
    .c-metrics{display:flex;gap:22px;padding:14px 0;border-top:1px solid #f1f2f4;border-bottom:1px solid #f1f2f4}
    .m{display:flex;flex-direction:column;gap:2px}
    .mv{font-family:'IBM Plex Mono',monospace;font-size:20px;font-weight:500;color:var(--ink)}
    .mv.z{color:#c9ced4}
    .ml{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
    .c-foot{font-size:12px;color:#9aa2ab;margin-top:13px}
    .empty{grid-column:1/-1;text-align:center;color:var(--muted);padding:60px}
    /* table */
    .card-wrap{flex:1;margin:24px 30px;background:var(--card);border:1px solid var(--line);border-radius:11px;overflow:auto;align-self:start;max-width:calc(100% - 60px)}
    table{width:100%;border-collapse:collapse}
    thead th{position:sticky;top:0;background:#f4f5f6;text-align:left;padding:12px 16px;font-size:11px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--line);white-space:nowrap;user-select:none}
    thead th.sortable{cursor:pointer}thead th.sortable:hover{color:var(--ink)}
    thead th.active{color:var(--accent)}th.num,td.num{text-align:right}
    .arr{margin-left:5px;font-style:normal;color:var(--accent)}
    tbody td{padding:12px 16px;font-size:13.5px;border-bottom:1px solid #f1f2f4;color:#3a4048;white-space:nowrap}
    tbody tr:hover{background:#f6f4f1}.strong{font-weight:600;color:var(--ink)}
    .mono{font-family:'IBM Plex Mono',monospace;font-size:12.5px;color:var(--muted)}
    .num span{font-family:'IBM Plex Mono',monospace}.z{color:#c9ced4}
    .badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:600;background:#f0f1f3;color:#8a929c}
    .badge.yes{background:#e7f4ec;color:#137a3d}
    /* clickable affordances */
    .card{cursor:pointer;outline:none}
    .card:focus-visible{box-shadow:0 0 0 3px rgba(20,110,180,.3)}
    .c-foot{display:flex;justify-content:space-between;align-items:center}
    .c-open{color:var(--accent);font-weight:600;opacity:0;transition:opacity .15s}
    .card:hover .c-open{opacity:1}
    .row-click{cursor:pointer}
    /* detail drawer */
    .scrim{position:fixed;inset:0;background:rgba(13,27,42,.4);z-index:40;animation:fade .15s ease}
    @keyframes fade{from{opacity:0}to{opacity:1}}
    .drawer{position:fixed;top:0;right:0;height:100vh;width:460px;max-width:92vw;background:#fff;z-index:50;box-shadow:-16px 0 48px -18px rgba(16,24,40,.4);display:flex;flex-direction:column;animation:slide .22s cubic-bezier(.2,.7,.3,1)}
    @keyframes slide{from{transform:translateX(100%)}to{transform:translateX(0)}}
    .d-head{padding:24px 26px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:flex-start;gap:14px}
    .d-crumb{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:6px}
    .d-head h2{margin:0 0 8px;font-size:22px;font-weight:600;letter-spacing:-.3px}
    .d-close{border:0;background:#f0f1f3;width:34px;height:34px;border-radius:8px;cursor:pointer;font-size:15px;color:var(--muted);flex-shrink:0}
    .d-close:hover{background:#e5e7ea;color:var(--ink)}
    .d-metrics{display:flex;gap:0;padding:20px 26px;border-bottom:1px solid var(--line);background:#fafbfc}
    .dm{flex:1;display:flex;flex-direction:column;gap:3px}
    .dmv{font-family:'IBM Plex Mono',monospace;font-size:26px;font-weight:500;color:var(--navy)}
    .dml{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
    .d-fields{flex:1;overflow-y:auto;padding:8px 26px}
    .df{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid #f1f2f4;font-size:13.5px}
    .df:last-child{border-bottom:0}
    .dfl{color:var(--muted);flex-shrink:0}
    .dfv{text-align:right;color:#3a4048}.dfv.strong{font-weight:600;color:var(--ink)}
    .d-foot{padding:16px 26px;border-top:1px solid var(--line);font-size:11.5px;color:#9aa2ab;background:#fafbfc}
  `],
})
export class ReportGridComponent implements OnInit {
  private http = inject(HttpClient);
  private route = inject(ActivatedRoute);
  private base = environment.apiBaseUrl;

  data: ReportData | null = null;
  view2: Record<string, any>[] = [];
  territories: string[] = [];
  key=''; q=''; sort=''; dir:'asc'|'desc'='asc';
  view:'cards'|'table'='cards';
  fTerr=''; fKey=''; sortSel='CUSTOMER_NAME';
  sel: Record<string, any> | null = null;   // account open in the detail drawer

  private accents = ['#146eb4','#0d6efd','#198754','#fd7e14','#6f42c1','#0dcaf0','#d63384','#20c997'];
  accent(i:number){ return this.accents[i % this.accents.length]; }

  ngOnInit(){ this.key=this.route.snapshot.paramMap.get('key')||''; this.load(); }

  load(){
    let url=`${this.base}/api/reports/${this.key}`;
    if(this.sort) url+=`?sort=${this.sort}&dir=${this.dir}`;
    this.http.get<ReportData>(url).subscribe(d=>{
      this.data=d;
      this.territories=[...new Set(d.rows.map(r=>r['TERRITORY_NAME']).filter(Boolean))].sort();
      this.apply();
    });
  }

  cols(){ return (this.data?.columns||[]).filter(c=>!c.hidden); }

  // detail drawer: show ALL columns (incl. otherwise-hidden id/audit) except row_key noise
  detailCols(){ return (this.data?.columns||[]).filter(c=>c.key!=='ROW_KEY'); }
  open(r: Record<string, any>){ this.sel = r; }

  apply(){
    const rows=this.data?.rows||[]; const q=this.q.trim().toLowerCase();
    this.view2=rows.filter(r=>{
      if(this.fTerr && r['TERRITORY_NAME']!==this.fTerr) return false;
      if(this.fKey && (this.isYes(r['CUSTOMER_IS_KEY_ACCOUNT_YN'])?'Yes':'No')!==this.fKey) return false;
      if(q && !this.cols().some(c=>String(r[c.key]??'').toLowerCase().includes(q))) return false;
      return true;
    });
  }

  applySort(){ this.sort=this.sortSel; this.dir='asc'; this.load(); }
  sortBy(k:string){ if(this.sort===k) this.dir=this.dir==='asc'?'desc':'asc'; else {this.sort=k;this.dir='asc';} this.sortSel=k; this.load(); }
  reset(){ this.q='';this.fTerr='';this.fKey='';this.sortSel='CUSTOMER_NAME';this.sort='';this.dir='asc'; this.load(); }

  isYes(v:any){ return String(v).toLowerCase()==='yes'||v==='Y'||v===true; }
  fmtDate(v:any){ if(!v) return '—'; const d=new Date(v); return isNaN(d.getTime())?String(v):d.toLocaleDateString('en-US',{day:'2-digit',month:'short',year:'numeric'}); }
}
