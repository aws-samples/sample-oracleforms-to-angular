import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

// App shell: provides a minimal global nav and hosts the router outlet.
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <nav class="global-nav">
      <span class="brand">Modernized Oracle App &mdash; Sample</span>
      <a routerLink="/accounts" routerLinkActive="active">Accounts</a>
      <a routerLink="/reports/accounts" routerLinkActive="active">Reports</a>
    </nav>
    <router-outlet></router-outlet>
  `,
  styles: [`
    .global-nav {
      display: flex;
      align-items: center;
      gap: 20px;
      background: #0f1729;
      color: #fff;
      padding: 0 24px;
      height: 48px;
      font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    }
    .brand {
      font-weight: 600;
      font-size: 14px;
      margin-right: 16px;
      color: #fff;
    }
    a {
      color: #adb8c8;
      text-decoration: none;
      font-size: 14px;
      padding: 4px 10px;
      border-radius: 4px;
    }
    a:hover { color: #fff; }
    a.active { color: #fff; background: #1e3250; }
  `],
})
export class RootComponent {}
