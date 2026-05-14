// frontend-angular\src\app\utils\alertas.ts

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
  
  export async function solicitarMotivoRechazoCierre(
  ticketId: number,
  descripcion?: string
): Promise<string | null> {
  const result = await Swal.fire<string>({
    icon: 'warning',
    title: 'Rechazar cierre',
    text: descripcion
      ? `Ticket #${ticketId}: ${descripcion}`
      : `Ticket #${ticketId}`,
    input: 'textarea',
    inputLabel: 'Motivo del rechazo',
    inputPlaceholder: 'Ej. El ticket no está realmente resuelto; falta evidencia de solución.',
    inputAttributes: {
      'aria-label': 'Motivo del rechazo'
    },
    showCancelButton: true,
    confirmButtonText: 'Rechazar cierre',
    cancelButtonText: 'Cancelar',
    confirmButtonColor: '#d33',
    cancelButtonColor: '#6c757d',
    inputValidator: (value) => {
      if (!value || !value.trim()) {
        return 'El motivo de rechazo es obligatorio.';
      }

      if (value.trim().length < 3) {
        return 'El motivo debe tener al menos 3 caracteres.';
      }

      return null;
    }
  });

  if (!result.isConfirmed) {
    return null;
  }

  return (result.value || '').trim();
}