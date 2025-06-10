import { FormGroup } from '@angular/forms';

export function limpiarCamposDependientes(form: FormGroup, campos: string[]): void {
  for (const campo of campos) {
    if (form.get(campo)) {
      form.get(campo)!.reset();
    }
  }
}