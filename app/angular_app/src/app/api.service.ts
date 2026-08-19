import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../environments/environment';

// Generic API service — thin wrapper over the .NET Web API that round-trips to Oracle.
// The accounts and report-grid components inject HttpClient directly; this service
// is provided as an extension point for shared API calls.
@Injectable({ providedIn: 'root' })
export class ApiService {
  readonly base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}
}
