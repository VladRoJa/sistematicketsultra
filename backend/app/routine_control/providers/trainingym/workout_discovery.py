from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


_WORKOUT_PATH = "/reports/workout"
_SPACE = re.compile(r"\s+")
_EMAIL = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b", re.IGNORECASE)
_LONG_IDENTIFIER = re.compile(r"\b\d{5,}\b")
_SENSITIVE = re.compile(
    r"\b(?:accessToken|authorization|bearer|cookie|password|secret|token)\b",
    re.IGNORECASE,
)
_POWERBI_HOST = re.compile(r"(?:^|\.)powerbi\.com$", re.IGNORECASE)
_MORE_OPTIONS = {"more options", "más opciones"}
_EXPORT_DATA = {"export data", "exportar datos"}
_DOCUMENT_STABLE_SCRIPT = """
() => (
  document.readyState === "interactive"
  || document.readyState === "complete"
) && Boolean(document.body)
"""
_WORKOUT_EVIDENCE_SCRIPT = """
() => {
  const text = (document.body?.innerText || "").replace(/\\s+/g, " ");
  return text.includes("Rutinas y pesajes")
    || text.includes("RUTINAS / PESAJES POR TÉCNICO")
    || Boolean(document.querySelector(
      "iframe,[class*='powerbi' i],[data-powerbi],[powerbi-client],"
      + "[aria-label*='Power BI' i],[aria-label*='report' i],"
      + "[class*='report' i]"
    ));
}
"""
_FRAME_EVIDENCE_SCRIPT = """
() => {
  const text = (document.body?.innerText || "").replace(/\\s+/g, " ");
  return {
    contains_powerbi: Boolean(document.querySelector(
      "iframe[src*='powerbi' i],[class*='powerbi' i],[data-powerbi],"
      + "[powerbi-client],[aria-label*='Power BI' i]"
    )),
    contains_report_controls: Boolean(document.querySelector(
      "input[type='date'],[role='combobox'],select,[aria-label*='fecha' i],"
      + "[aria-label*='date' i],[aria-label*='centro' i]"
    )),
    contains_workout_text: text.includes("Rutinas y pesajes")
      || text.includes("RUTINAS / PESAJES POR TÉCNICO")
      || text.includes("Total Pesajes y Rutinas por Técnico")
  };
}
"""
_FILTER_CONTROLS_SCRIPT = """
() => {
  /* workout_filters */
  const excluded = "table,tbody,[role='grid'],[role='row'],[role='rowgroup'],"
    + ".grid,[class*='grid' i]";
  const candidates = document.querySelectorAll(
    "input[type='date'],input[placeholder],[role='combobox'],select,"
    + "[aria-label*='fecha' i],[aria-label*='date' i],"
    + "[aria-label*='centro' i],label"
  );
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none"
      && rect.width > 0 && rect.height > 0;
  };
  return Array.from(candidates)
    .filter((element) => !element.closest(excluded) && visible(element))
    .slice(0, 80)
    .map((element) => {
      const inputType = element.getAttribute("type") || "";
      return {
        kind: inputType === "date" ? "date" : (
          element.getAttribute("role") === "combobox"
            || element.tagName === "SELECT" ? "selector" : "label"
        ),
        text: element.innerText || element.textContent || "",
        placeholder: element.getAttribute("placeholder") || "",
        role: element.getAttribute("role") || "",
        aria_label: element.getAttribute("aria-label") || "",
        input_type: inputType,
        value: inputType === "date" ? (element.value || "") : ""
      };
    });
}
"""
_EXPORT_CANDIDATES_SCRIPT = """
() => {
  /* workout_export_candidates */
  const excluded = "table,tbody,[role='grid'],[role='row'],[role='rowgroup'],"
    + ".grid,[class*='grid' i]";
  const terms = [
    "más opciones", "more options", "exportar datos", "export data",
    "export", "descargar", "download"
  ];
  const candidates = document.querySelectorAll(
    "button,[role='button'],[role='menuitem'],[aria-label],[title]"
  );
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none"
      && rect.width > 0 && rect.height > 0;
  };
  return Array.from(candidates)
    .filter((element) => {
      if (element.closest(excluded) || !visible(element)) {
        return false;
      }
      const haystack = [
        element.innerText,
        element.textContent,
        element.getAttribute("aria-label"),
        element.getAttribute("title")
      ].join(" ").toLocaleLowerCase();
      return terms.some((term) => haystack.includes(term));
    })
    .slice(0, 80)
    .map((element) => {
      const visual = element.closest("[aria-label],[title]");
      return {
        text: element.innerText || element.textContent || "",
        aria_label: element.getAttribute("aria-label") || "",
        title: element.getAttribute("title") || "",
        role: element.getAttribute("role")
          || (element.tagName === "BUTTON" ? "button" : ""),
        visual: visual && visual !== element
          ? (visual.getAttribute("aria-label") || visual.getAttribute("title") || "")
          : ""
      };
    });
}
"""
_MENU_ITEMS_SCRIPT = """
() => {
  /* workout_menu_items */
  const excluded = "table,tbody,[role='grid'],[role='row'],[role='rowgroup']";
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none"
      && rect.width > 0 && rect.height > 0;
  };
  return Array.from(document.querySelectorAll(
    "[role='menu'] [role='menuitem'],"
    + "[role='menu'] [role='menuitemcheckbox'],"
    + "[role='listbox'] [role='option']"
  ))
    .filter((element) => !element.closest(excluded) && visible(element))
    .slice(0, 50)
    .map((element) => (
      element.innerText || element.textContent
      || element.getAttribute("aria-label") || ""
    ));
}
"""


class TrainingymWorkoutDiscoveryError(RuntimeError):
    provider_retryable = False

    def __init__(self, error_code: str, error_message: str) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.attempts = 1


@dataclass(frozen=True, slots=True)
class WorkoutFrameSummary:
    index: int
    name: str
    hostname: str
    path: str
    is_main_frame: bool
    contains_powerbi: bool
    contains_report_controls: bool
    contains_workout_text: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "contains_powerbi": self.contains_powerbi,
            "contains_report_controls": self.contains_report_controls,
            "contains_workout_text": self.contains_workout_text,
            "hostname": self.hostname,
            "index": self.index,
            "is_main_frame": self.is_main_frame,
            "name": self.name,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class WorkoutFilterControl:
    frame_index: int
    kind: str
    text: str
    placeholder: str
    role: str
    aria_label: str
    input_type: str
    value: str

    def to_dict(self) -> dict[str, object]:
        return {
            "aria_label": self.aria_label,
            "frame_index": self.frame_index,
            "input_type": self.input_type,
            "kind": self.kind,
            "placeholder": self.placeholder,
            "role": self.role,
            "text": self.text,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class WorkoutExportControl:
    frame_index: int
    selector: str
    text: str
    aria_label: str
    title: str
    menu_items: tuple[str, ...]
    export_data_visible: bool
    visual: str

    def to_dict(self) -> dict[str, object]:
        return {
            "aria_label": self.aria_label,
            "export_data_visible": self.export_data_visible,
            "frame_index": self.frame_index,
            "menu_items": list(self.menu_items),
            "selector": self.selector,
            "text": self.text,
            "title": self.title,
            "visual": self.visual,
        }


@dataclass(frozen=True, slots=True)
class WorkoutDiscoveryObservation:
    workout_path: str
    workout_reached: bool
    report_mode: str
    frame_summaries: tuple[WorkoutFrameSummary, ...]
    filter_controls: tuple[WorkoutFilterControl, ...]
    export_controls: tuple[WorkoutExportControl, ...]
    export_contract_verified: bool
    workout_error_code: str | None


def _is_execution_context_destroyed(exc: BaseException) -> bool:
    return "execution context was destroyed" in str(exc).casefold()


def _safe_text(value: object) -> str:
    text = _SPACE.sub(" ", str(value or "")).strip()
    if (
        not text
        or len(text) > 120
        or _EMAIL.search(text)
        or _LONG_IDENTIFIER.search(text)
        or _SENSITIVE.search(text)
    ):
        return ""
    return text


def _safe_url_parts(value: object) -> tuple[str, str]:
    parsed = urlsplit(str(value or ""))
    return (parsed.hostname or "")[:120], (parsed.path or "/")[:300]


def _normalize(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip().casefold()


def _inspect_frame(frame, index: int, main_frame) -> WorkoutFrameSummary:
    hostname, path = _safe_url_parts(frame.url)
    evidence: dict[str, object] = {}
    for attempt in range(2):
        try:
            evidence = dict(frame.evaluate(_FRAME_EVIDENCE_SCRIPT) or {})
            break
        except Exception as exc:
            if _is_execution_context_destroyed(exc) and attempt == 0:
                continue
            break
    return WorkoutFrameSummary(
        index=index,
        name=_safe_text(getattr(frame, "name", "")),
        hostname=hostname,
        path=path,
        is_main_frame=frame is main_frame,
        contains_powerbi=bool(
            _POWERBI_HOST.search(hostname)
            or evidence.get("contains_powerbi")
        ),
        contains_report_controls=bool(
            evidence.get("contains_report_controls")
        ),
        contains_workout_text=bool(evidence.get("contains_workout_text")),
    )


def _report_mode(frames: tuple[WorkoutFrameSummary, ...]) -> str:
    if any(
        frame.contains_powerbi and not frame.is_main_frame
        for frame in frames
    ):
        return "powerbi_iframe"
    if any(
        frame.contains_powerbi and frame.is_main_frame
        for frame in frames
    ):
        return "powerbi_same_dom"
    if any(
        frame.contains_report_controls or frame.contains_workout_text
        for frame in frames
    ):
        return "native_dom"
    return "unknown"


def _read_filter_controls(
    frames,
    frame_indexes: dict[int, int],
) -> tuple[WorkoutFilterControl, ...]:
    controls: list[WorkoutFilterControl] = []
    for frame in frames:
        if len(controls) >= 50:
            break
        try:
            candidates = frame.evaluate(_FILTER_CONTROLS_SCRIPT) or ()
        except Exception:
            continue
        for raw in candidates:
            if len(controls) >= 50 or not isinstance(raw, dict):
                break
            control = WorkoutFilterControl(
                frame_index=frame_indexes[id(frame)],
                kind=_safe_text(raw.get("kind")) or "unknown",
                text=_safe_text(raw.get("text")),
                placeholder=_safe_text(raw.get("placeholder")),
                role=_safe_text(raw.get("role")),
                aria_label=_safe_text(raw.get("aria_label")),
                input_type=_safe_text(raw.get("input_type")),
                value=(
                    _safe_text(raw.get("value"))
                    if raw.get("input_type") == "date"
                    else ""
                ),
            )
            if any(
                (
                    control.text,
                    control.placeholder,
                    control.aria_label,
                    control.role,
                )
            ):
                controls.append(control)
    return tuple(controls)


def _candidate_name(raw: dict[str, object]) -> str:
    return (
        _safe_text(raw.get("aria_label"))
        or _safe_text(raw.get("text"))
        or _safe_text(raw.get("title"))
    )


def _selector_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _semantic_menu_locator(frame, raw: dict[str, object]):
    name = _candidate_name(raw)
    role = _normalize(raw.get("role"))
    if not name:
        return None, ""
    if role == "button":
        return (
            frame.get_by_role("button", name=name, exact=True),
            f'role=button[name="{_selector_value(name)}"]',
        )
    title = _safe_text(raw.get("title"))
    if title:
        return (
            frame.get_by_title(title, exact=True),
            f'title="{_selector_value(title)}"',
        )
    return None, ""


def _read_export_controls(
    page,
    frames,
    frame_indexes: dict[int, int],
) -> tuple[WorkoutExportControl, ...]:
    controls: list[WorkoutExportControl] = []
    for frame in frames:
        if len(controls) >= 50:
            break
        try:
            candidates = frame.evaluate(_EXPORT_CANDIDATES_SCRIPT) or ()
        except Exception:
            continue
        for raw in candidates:
            if len(controls) >= 50 or not isinstance(raw, dict):
                break
            name = _candidate_name(raw)
            normalized = _normalize(name)
            locator, selector = _semantic_menu_locator(frame, raw)
            menu_items: tuple[str, ...] = ()
            if (
                normalized in _MORE_OPTIONS
                and locator is not None
                and locator.count() == 1
                and locator.is_visible()
            ):
                locator.click()
                try:
                    menu_items = tuple(
                        value
                        for value in (
                            _safe_text(item)
                            for item in (
                                frame.evaluate(_MENU_ITEMS_SCRIPT) or ()
                            )
                        )
                        if value
                    )[:50]
                finally:
                    page.keyboard.press("Escape")
            export_visible = (
                normalized in _EXPORT_DATA
                or any(_normalize(item) in _EXPORT_DATA for item in menu_items)
            )
            if not selector:
                role = _safe_text(raw.get("role"))
                selector = (
                    f'role={role}[name="{_selector_value(name)}"]'
                    if role and name
                    else ""
                )
            controls.append(
                WorkoutExportControl(
                    frame_index=frame_indexes[id(frame)],
                    selector=_safe_text(selector),
                    text=_safe_text(raw.get("text")),
                    aria_label=_safe_text(raw.get("aria_label")),
                    title=_safe_text(raw.get("title")),
                    menu_items=menu_items,
                    export_data_visible=export_visible,
                    visual=_safe_text(raw.get("visual")),
                )
            )
    return tuple(controls)


def discover_workout(page, workout_url: str) -> WorkoutDiscoveryObservation:
    try:
        page.goto(workout_url, wait_until="domcontentloaded")
    except Exception as exc:
        if not _is_execution_context_destroyed(exc):
            raise TrainingymWorkoutDiscoveryError(
                "TRAININGYM_WORKOUT_NAVIGATION_FAILED",
                "No fue posible abrir el reporte Workout configurado.",
            ) from exc

    last_error: BaseException | None = None
    stabilized = False
    for attempt in range(2):
        try:
            page.wait_for_url("**/reports/workout*")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_function(_DOCUMENT_STABLE_SCRIPT)
            page.locator("body").wait_for(state="visible")
            if _safe_url_parts(page.url)[1] != _WORKOUT_PATH:
                raise TrainingymWorkoutDiscoveryError(
                    "TRAININGYM_WORKOUT_NAVIGATION_FAILED",
                    "Trainingym no alcanzó el path Workout esperado.",
                )
            stabilized = True
            break
        except TrainingymWorkoutDiscoveryError:
            raise
        except Exception as exc:
            last_error = exc
            if _is_execution_context_destroyed(exc) and attempt == 0:
                continue
            break
    if not stabilized:
        raise TrainingymWorkoutDiscoveryError(
            "TRAININGYM_WORKOUT_NAVIGATION_FAILED",
            "La navegación Workout no se estabilizó dentro del timeout.",
        ) from last_error

    try:
        page.wait_for_function(_WORKOUT_EVIDENCE_SCRIPT)
    except PlaywrightTimeoutError as exc:
        raise TrainingymWorkoutDiscoveryError(
            "TRAININGYM_WORKOUT_CONTRACT_FAILED",
            "La pantalla Workout no mostró evidencia del reporte comprobado.",
        ) from exc
    except Exception as exc:
        raise TrainingymWorkoutDiscoveryError(
            "TRAININGYM_WORKOUT_DISCOVERY_FAILED",
            "No fue posible validar el documento Workout.",
        ) from exc

    frames = tuple(page.frames[:20])
    frame_indexes = {id(frame): index for index, frame in enumerate(frames)}
    try:
        summaries = tuple(
            _inspect_frame(frame, frame_indexes[id(frame)], page.main_frame)
            for frame in frames
        )
        filters = _read_filter_controls(frames, frame_indexes)
        exports = _read_export_controls(page, frames, frame_indexes)
    except Exception as exc:
        raise TrainingymWorkoutDiscoveryError(
            "TRAININGYM_WORKOUT_DISCOVERY_FAILED",
            "No fue posible inspeccionar el contrato sanitizado de Workout.",
        ) from exc

    export_verified = any(
        control.export_data_visible for control in exports
    )
    return WorkoutDiscoveryObservation(
        workout_path=_safe_url_parts(page.url)[1],
        workout_reached=True,
        report_mode=_report_mode(summaries),
        frame_summaries=summaries,
        filter_controls=filters,
        export_controls=exports,
        export_contract_verified=export_verified,
        workout_error_code=(
            None
            if export_verified
            else "TRAININGYM_WORKOUT_EXPORT_CONTRACT_UNVERIFIED"
        ),
    )
