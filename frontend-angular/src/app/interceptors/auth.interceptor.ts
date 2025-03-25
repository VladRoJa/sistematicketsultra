// src/app/interceptors/auth.interceptor.ts
import { HttpInterceptorFn, HttpRequest, HttpHandlerFn, HttpEvent } from '@angular/common/http';
import { Observable } from 'rxjs';

/**
 * authInterceptorFn:
 *  - Usa localStorage para obtener el token
 *  - Añade la cabecera Authorization si existe
 *  - Devuelve la llamada al siguiente interceptor o request final
 */
export const authInterceptorFn: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn // Eliminamos el <unknown>
): Observable<HttpEvent<unknown>> => {
  const token = localStorage.getItem('token');
  if (token) {
    const authReq = req.clone({
      setHeaders: { Authorization: `Bearer ${token}` }
    });
    return next(authReq);
  }
  return next(req);
};
