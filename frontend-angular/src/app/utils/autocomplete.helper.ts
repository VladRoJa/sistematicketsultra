// src/app/utils/autocomplete.helper.ts

import { AbstractControl } from '@angular/forms';

/**
 * Enlaza un mat-autocomplete para forzar el objeto seleccionado
 * con mouse o teclado, aunque el input muestre texto.
 * 
 * Llama este método en (click) y en (optionSelected) de tu mat-option
 */
export function seleccionarObjetoAutocomplete<T>(
  control: AbstractControl | null | undefined, 
  objeto: T, 
  extraFn?: (obj: T) => void
) {
  if (!control) return;
  control.setValue(objeto, { emitEvent: false });
  // Puedes ejecutar lógica extra (ej: setear otro campo relacionado)
  if (extraFn) extraFn(objeto);
}

export function forzarObjetoEnFormArray(
  grupo: AbstractControl,
  inv: any,
  event: MouseEvent
) {
  event.preventDefault();
  grupo.get('inventarioControl')?.setValue(inv, { emitEvent: false });
  grupo.get('inventario_id')?.setValue(inv.id, { emitEvent: false });
  grupo.get('unidad_medida')?.setValue(inv.unidad_medida || '', { emitEvent: false });
}
