import {
  buildSystemDailyCheckQuestionGroups,
  canSystemDailyCheckPostpone,
  isSystemDailyCheckQuestionComplete,
  resolveSystemDailyCheckGatePresentation,
} from '../src/app/system-daily-check/system-daily-check-gate-state';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const questions = [
  {
    question_key: 'COMPUTERS_WORKING',
    category_key: 'COMPUTING',
    requires_affected_scope: true,
  },
  {
    question_key: 'INTERNET_WORKING',
    category_key: 'CONNECTIVITY_SYSTEMS',
    requires_affected_scope: true,
  },
  {
    question_key: 'GASCA_WORKING',
    category_key: 'CONNECTIVITY_SYSTEMS',
    requires_affected_scope: false,
  },
  {
    question_key: 'TURNSTILES_WORKING',
    category_key: 'ACCESS_CONTROL',
    requires_affected_scope: true,
  },
  {
    question_key: 'CAMERAS_WORKING',
    category_key: 'AUXILIARY_SYSTEMS',
    requires_affected_scope: true,
  },
];

const groups = buildSystemDailyCheckQuestionGroups(questions);
assert(groups.length === 4, 'Debe conservar las cuatro agrupaciones.');
assert(
  groups.map((group) => group.key).join('|')
    === 'COMPUTING|CONNECTIVITY_SYSTEMS|ACCESS_CONTROL|AUXILIARY_SYSTEMS',
  'Las agrupaciones deben conservar el orden operativo.',
);
assert(
  groups[1].questions.length === 2,
  'Conectividad debe conservar preguntas independientes.',
);

assert(
  !isSystemDailyCheckQuestionComplete(
    questions[0],
    {
      answer: null,
      affectedScope: null,
      reportedToSupport: null,
      description: '',
    },
  ),
  'Una pregunta sin selección no puede estar completa.',
);

assert(
  isSystemDailyCheckQuestionComplete(
    questions[0],
    {
      answer: 'YES',
      affectedScope: null,
      reportedToSupport: null,
      description: '',
    },
  ),
  'YES no debe exigir detalle de incidencia.',
);

assert(
  !isSystemDailyCheckQuestionComplete(
    questions[0],
    {
      answer: 'NO',
      affectedScope: null,
      reportedToSupport: false,
      description: 'No enciende.',
    },
  ),
  'NO contable debe exigir ONE/MULTIPLE.',
);

assert(
  isSystemDailyCheckQuestionComplete(
    questions[0],
    {
      answer: 'NO',
      affectedScope: 'ONE',
      reportedToSupport: false,
      description: 'No enciende.',
    },
  ),
  'NO con detalle completo debe ser válido.',
);

assert(
  isSystemDailyCheckQuestionComplete(
    questions[2],
    {
      answer: 'NO',
      affectedScope: null,
      reportedToSupport: true,
      description: 'Gasca no abre.',
    },
  ),
  'Preguntas no contables no deben exigir affected_scope.',
);

assert(
  canSystemDailyCheckPostpone(
    {
      completed: false,
      should_prompt: true,
      mandatory: false,
      can_postpone: true,
    },
    false,
  ),
  'Primera/segunda presentación elegible debe permitir aplazar.',
);

assert(
  !canSystemDailyCheckPostpone(
    {
      completed: false,
      should_prompt: true,
      mandatory: true,
      can_postpone: false,
    },
    false,
  ),
  'Mandatory nunca debe permitir aplazar.',
);

assert(
  !canSystemDailyCheckPostpone(
    {
      completed: false,
      should_prompt: true,
      mandatory: false,
      can_postpone: true,
    },
    true,
  ),
  'No debe aceptar doble acción mientras existe request en curso.',
);

const waiting = resolveSystemDailyCheckGatePresentation(
  {
    completed: false,
    should_prompt: false,
    mandatory: false,
    can_postpone: false,
  },
  'intro',
);
assert(!waiting.visible, 'Durante los cinco minutos el gate debe ocultarse.');
assert(waiting.scheduleRetry, 'Debe programar reconsulta backend.');

const mandatory = resolveSystemDailyCheckGatePresentation(
  {
    completed: false,
    should_prompt: true,
    mandatory: true,
    can_postpone: false,
  },
  'intro',
);
assert(mandatory.visible, 'Mandatory debe mostrar el gate.');
assert(mandatory.screen === 'form', 'Mandatory debe abrir captura directa.');
assert(!mandatory.scheduleRetry, 'Mandatory no espera otro ciclo.');

const complete = resolveSystemDailyCheckGatePresentation(
  {
    completed: true,
    should_prompt: false,
    mandatory: false,
    can_postpone: false,
  },
  'form',
);
assert(!complete.visible, 'Submit completado debe liberar Suite.');
assert(!complete.scheduleRetry, 'Completado no debe seguir consultando.');

const preserveForm = resolveSystemDailyCheckGatePresentation(
  {
    completed: false,
    should_prompt: true,
    mandatory: false,
    can_postpone: true,
  },
  'form',
);
assert(
  preserveForm.screen === 'form',
  'Una reconsulta no debe borrar progreso si el usuario ya empezó.',
);
