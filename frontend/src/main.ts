//frontend-angular\src\main.ts

import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter, withHashLocation } from '@angular/router';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';
import { AppComponent } from './app/app.component';
import { routes } from './app/app.routes';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { TokenInterceptor } from './app/interceptors/auth.interceptor';
import { MatDialogModule } from '@angular/material/dialog';
import { importProvidersFrom } from '@angular/core';
import { JwtHelperService, JWT_OPTIONS } from '@auth0/angular-jwt';
import { JwtInterceptor } from './app/interceptors/jwt.interceptor';

bootstrapApplication(AppComponent, {
  providers: [
    provideAnimations(),
    provideRouter(routes, withHashLocation()), 
    importProvidersFrom(MatDialogModule),
    provideHttpClient(withInterceptorsFromDi()),
    {
      provide: HTTP_INTERCEPTORS,
      useClass: TokenInterceptor,
      multi: true
    },
    {
      provide: HTTP_INTERCEPTORS,
      useClass: JwtInterceptor,
      multi: true
    },
    { provide: JWT_OPTIONS, useValue: JWT_OPTIONS },
    JwtHelperService
  ]
}).catch(err => console.error(err));
