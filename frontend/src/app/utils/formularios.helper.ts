import { FormGroup } from '@angular/forms';
import { EventEmitter } from '@angular/core';

export function limpiarCamposDependientes(form: FormGroup, campos: string[]): void {
  for (const campo of campos) {
    if (form.get(campo)) {
      form.get(campo)!.reset();
    }
  }
}

export const DEPARTAMENTO_IDS = {
  mantenimiento: 1,
  finanzas: 2,
  marketing: 3,
  gerencia: 4,
  rh: 5,
  compras: 6,
  sistemas: 7
};

export function emitirPayloadFormulario(
  parentForm: FormGroup,
  departamento_id: number,
  emisor: EventEmitter<any>
): void {
  if (!parentForm || !parentForm.valid) return;

  parentForm.get('departamento_id')?.setValue(departamento_id);

  emisor.emit({
    departamento_id,
    categoria: parentForm.get('categoria')?.value,
    subcategoria: parentForm.get('subcategoria')?.value,
    detalle: parentForm.get('detalle')?.value,
    descripcion: parentForm.get('descripcion')?.value
  });
}