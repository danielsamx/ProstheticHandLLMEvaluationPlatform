import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { authInterceptor } from '@core/services/auth.interceptor';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter, withComponentInputBinding, withInMemoryScrolling } from '@angular/router';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Signals drive every view in this app, so zone.js change detection is
    // unnecessary overhead - and the 3D loop benefits from staying out of it.
    provideZonelessChangeDetection(),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideAnimationsAsync(),
    provideRouter(
      routes,
      withComponentInputBinding(),
      // Returning to the dashboard should not lose your place in a long table.
      withInMemoryScrolling({ scrollPositionRestoration: 'enabled' }),
    ),
  ],
};
