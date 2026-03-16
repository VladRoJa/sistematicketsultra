// frontend/src/app/pm/helpers/calendario-pm.helper.ts

export type SemanaCalendarioPmOption = {
  anio: number;
  mes: number;
  semana_anio: number;

  fecha_inicio_iso: string;
  fecha_fin_iso: string;

  fecha_inicio_label: string; // dd/mm
  fecha_fin_label: string;    // dd/mm

  label: string; // Semana 24 — 14/06 al 20/06
};

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

function formatearIso(fecha: Date): string {
  const yyyy = fecha.getFullYear();
  const mm = pad2(fecha.getMonth() + 1);
  const dd = pad2(fecha.getDate());
  return `${yyyy}-${mm}-${dd}`;
}

function formatearLabelDdMm(fecha: Date): string {
  const dd = pad2(fecha.getDate());
  const mm = pad2(fecha.getMonth() + 1);
  return `${dd}/${mm}`;
}

function sumarDias(fecha: Date, dias: number): Date {
  const copia = new Date(fecha);
  copia.setDate(copia.getDate() + dias);
  return copia;
}

function inicioAnioDomingo(anio: number): Date {
  const primeroEnero = new Date(anio, 0, 1);
  const diaSemana = primeroEnero.getDay(); // 0=domingo
  return sumarDias(primeroEnero, -diaSemana);
}

function calcularSemanaAnioDomingoASabado(fecha: Date): number {
  const inicio = inicioAnioDomingo(fecha.getFullYear());

  const fechaUtc = Date.UTC(
    fecha.getFullYear(),
    fecha.getMonth(),
    fecha.getDate()
  );

  const inicioUtc = Date.UTC(
    inicio.getFullYear(),
    inicio.getMonth(),
    inicio.getDate()
  );

  const diffDias = Math.floor((fechaUtc - inicioUtc) / 86400000);
  return Math.floor(diffDias / 7) + 1;
}

export function generarSemanasDelMes(
  anio: number,
  mes: number // 1-12
): SemanaCalendarioPmOption[] {
  if (mes < 1 || mes > 12) {
    return [];
  }

  const mesIndex = mes - 1;
  const primerDiaMes = new Date(anio, mesIndex, 1);
  const ultimoDiaMes = new Date(anio, mesIndex + 1, 0);

  const primerDiaSemana = primerDiaMes.getDay(); // 0=domingo
  const offsetPrimerDomingo = primerDiaSemana === 0 ? 0 : 7 - primerDiaSemana;
  let domingoActual = sumarDias(primerDiaMes, offsetPrimerDomingo);

  const semanas: SemanaCalendarioPmOption[] = [];

  while (domingoActual.getMonth() === mesIndex && domingoActual <= ultimoDiaMes) {
    const sabadoActual = sumarDias(domingoActual, 6);
    const semanaAnio = calcularSemanaAnioDomingoASabado(domingoActual);

    semanas.push({
      anio,
      mes,
      semana_anio: semanaAnio,
      fecha_inicio_iso: formatearIso(domingoActual),
      fecha_fin_iso: formatearIso(sabadoActual),
      fecha_inicio_label: formatearLabelDdMm(domingoActual),
      fecha_fin_label: formatearLabelDdMm(sabadoActual),
      label: `Semana ${semanaAnio} — ${formatearLabelDdMm(domingoActual)} al ${formatearLabelDdMm(sabadoActual)}`,
    });

    domingoActual = sumarDias(domingoActual, 7);
  }

  return semanas;
}