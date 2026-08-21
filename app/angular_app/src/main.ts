import { provideZoneChangeDetection } from "@angular/core";
import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { RootComponent } from './app/root.component';
import { routes } from './app/app.routes';

bootstrapApplication(RootComponent, {
  providers: [provideZoneChangeDetection(),provideHttpClient(withXhr()), provideRouter(routes)],
}).catch((err) => console.error(err));
