export type SystemDailyCheckGateScreen =
  | 'branch'
  | 'intro'
  | 'form';

export type SystemDailyCheckGateAnswer =
  | 'YES'
  | 'NO'
  | 'NA';

export type SystemDailyCheckGateAffectedScope =
  | 'ONE'
  | 'MULTIPLE';

export interface SystemDailyCheckGateQuestionLike {
  question_key: string;
  category_key: string;
  requires_affected_scope: boolean;
}

export interface SystemDailyCheckGateAnswerStateLike {
  answer: SystemDailyCheckGateAnswer | null;
  affectedScope: SystemDailyCheckGateAffectedScope | null;
  reportedToSupport: boolean | null;
  description: string;
}

export interface SystemDailyCheckGateStatusLike {
  completed: boolean;
  should_prompt: boolean;
  mandatory: boolean;
  can_postpone: boolean;
}

export interface SystemDailyCheckMvpUserLike {
  username?: unknown;
  rol?: unknown;
  role?: unknown;
}

export interface SystemDailyCheckGatePresentation {
  visible: boolean;
  screen: SystemDailyCheckGateScreen;
  scheduleRetry: boolean;
}

export interface SystemDailyCheckGateQuestionGroup<
  T extends SystemDailyCheckGateQuestionLike,
> {
  key: string;
  label: string;
  questions: T[];
}

export const SYSTEM_DAILY_CHECK_CATEGORY_ORDER = [
  'COMPUTING',
  'CONNECTIVITY_SYSTEMS',
  'ACCESS_CONTROL',
  'AUXILIARY_SYSTEMS',
] as const;

export const SYSTEM_DAILY_CHECK_CATEGORY_LABELS: Record<
  string,
  string
> = {
  COMPUTING: 'Equipo de cómputo',
  CONNECTIVITY_SYSTEMS: 'Conectividad y sistemas',
  ACCESS_CONTROL: 'Control de acceso',
  AUXILIARY_SYSTEMS: 'Sistemas auxiliares',
};

export function isSystemDailyCheckMvpCandidate(
  user: SystemDailyCheckMvpUserLike | null | undefined,
): boolean {
  const role = String(
    user?.rol ?? user?.role ?? '',
  ).trim().toUpperCase();
  const username = String(
    user?.username ?? '',
  ).trim().toUpperCase();

  return role === 'SISTEMAS' || username === 'ADMICORP';
}

export function buildSystemDailyCheckQuestionGroups<
  T extends SystemDailyCheckGateQuestionLike,
>(
  questions: readonly T[],
): SystemDailyCheckGateQuestionGroup<T>[] {
  return SYSTEM_DAILY_CHECK_CATEGORY_ORDER
    .map((key) => ({
      key,
      label: SYSTEM_DAILY_CHECK_CATEGORY_LABELS[key] || key,
      questions: questions.filter(
        (question) => question.category_key === key,
      ),
    }))
    .filter((group) => group.questions.length > 0);
}

export function isSystemDailyCheckQuestionComplete(
  question: SystemDailyCheckGateQuestionLike,
  state: SystemDailyCheckGateAnswerStateLike,
): boolean {
  if (!state.answer) {
    return false;
  }

  if (state.answer !== 'NO') {
    return true;
  }

  if (
    question.requires_affected_scope
    && !state.affectedScope
  ) {
    return false;
  }

  if (state.reportedToSupport === null) {
    return false;
  }

  return !!state.description.trim();
}

export function canSystemDailyCheckPostpone(
  status: SystemDailyCheckGateStatusLike | null,
  busy: boolean,
): boolean {
  if (!status || busy) {
    return false;
  }

  return (
    status.can_postpone
    && !status.mandatory
    && !status.completed
  );
}

export function resolveSystemDailyCheckGatePresentation(
  status: SystemDailyCheckGateStatusLike,
  currentScreen: SystemDailyCheckGateScreen,
): SystemDailyCheckGatePresentation {
  if (status.completed) {
    return {
      visible: false,
      screen: currentScreen,
      scheduleRetry: false,
    };
  }

  if (!status.should_prompt) {
    return {
      visible: false,
      screen: currentScreen,
      scheduleRetry: true,
    };
  }

  if (status.mandatory) {
    return {
      visible: true,
      screen: 'form',
      scheduleRetry: false,
    };
  }

  return {
    visible: true,
    screen: currentScreen === 'form' ? 'form' : 'intro',
    scheduleRetry: false,
  };
}
