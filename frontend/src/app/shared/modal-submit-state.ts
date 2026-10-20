/**
 * Validación reusable de habilitación para botones de confirmación en modales.
 * La UI controla disabled; los handlers siguen verificando antes de emitir.
 */
export interface ModalSubmitRequirements {
  requiredText?: Array<string | null | undefined>;
  requiredSelections?: unknown[];
  blocked?: boolean;
}

export function isModalSubmitDisabled({
  requiredText = [],
  requiredSelections = [],
  blocked = false,
}: ModalSubmitRequirements): boolean {
  return blocked ||
    requiredText.some((text) => !text?.trim()) ||
    requiredSelections.some(
      (value) => value === null || value === undefined || value === '',
    );
}
