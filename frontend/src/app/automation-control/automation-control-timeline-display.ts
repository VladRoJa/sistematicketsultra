/** Solo presentación de horarios de referencia; NO evalúa cumplimiento ni SLA. */
export type ReferenceState = 'FUTURE_REFERENCE' | 'PAST_REFERENCE_UNVERIFIED' | 'NO_OBSERVATION';

export interface TijuanaClock {
  date: string;
  time: string;
}

export function currentTijuanaClock(now: Date): TijuanaClock {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Tijuana',
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).formatToParts(now);
  const part = (type: string): string => parts.find(item => item.type === type)?.value ?? '';
  return {
    date: [part('year'), part('month'), part('day')].join('-'),
    time: [part('hour'), part('minute')].join(':'),
  };
}

export function classifyReferenceHour(
  selectedDate: string,
  hour: string,
  referenceSlots: readonly string[],
  clock: TijuanaClock,
): ReferenceState {
  const slots = referenceSlots.filter(slot => /^\d{2}:\d{2}$/.test(slot) && slot.slice(0, 2) === hour.slice(0, 2));
  if (!slots.length) { return 'NO_OBSERVATION'; }
  if (selectedDate > clock.date) { return 'FUTURE_REFERENCE'; }
  if (selectedDate === clock.date && slots.every(slot => slot > clock.time)) {
    return 'FUTURE_REFERENCE';
  }
  return 'PAST_REFERENCE_UNVERIFIED';
}

/** Primer elemento = última ejecución observada, ordenada por inicio desc en la API. */
export type ObservationState = 'completed' | 'replaced' | 'running' | 'partial' | 'error' | 'unknown';

export function classifyObservationRuns(runs: readonly { status_raw: string }[]): ObservationState {
  const status = (runs[0]?.status_raw ?? '').trim().toLowerCase();
  if (status === 'running') { return 'running'; }
  if (status === 'partial') { return 'partial'; }
  if (status === 'failed' || status === 'error') { return 'error'; }
  if (['completed', 'success', 'succeeded'].includes(status)) { return 'completed'; }
  if (status === 'replaced') { return 'replaced'; }
  return 'unknown';
}
