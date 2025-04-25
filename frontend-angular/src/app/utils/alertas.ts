// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\utils\alertas.ts

import Swal from 'sweetalert2';

export function mostrarAlertaToast(
    mensaje: string = '✅ Acción realizada correctamente.',
    tipo: 'success' | 'error' | 'info' | 'warning' = 'success'
  ): void {
    Swal.fire({
      toast: true,
      position: 'bottom-end',
      icon: tipo,
      title: mensaje,
      showConfirmButton: false,
      timer: 2500
    });
  }


  export function mostrarAlertaErrorDesdeStatus(status: number): void {
    let mensaje: string;
  
    switch (status) {
      case 400:
        mensaje = '⚠️ Faltan datos obligatorios.';
        break;
      case 401:
        mensaje = '🔒 No autorizado, inicia sesión.';
        break;
      default:
        mensaje = '❌ Error interno en el servidor.';
    }
  
    Swal.fire({
      toast: true,
      position: 'top-end',
      icon: 'error',
      title: mensaje,
      showConfirmButton: false,
      timer: 2500
    });
  }

  export function mostrarAlertaStockInsuficiente(nombreProducto: string): void {
    Swal.fire({
      icon: 'warning',
      title: 'Stock insuficiente',
      html: `No hay suficiente stock disponible para <b>${nombreProducto}</b>.`,
      confirmButtonText: 'Entendido',
      confirmButtonColor: '#3085d6'
    });
  }
  
  