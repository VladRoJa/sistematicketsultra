"""M4: recepción parcial de tapizado, con trazabilidad y sin cambio del ciclo V1."""

from datetime import datetime, timezone
from sqlalchemy.orm.attributes import flag_modified

TIPO_TRABAJO_TAPIZADO = "TAPIZADO"
ESTADOS_EDITABLES = frozenset({"abierto", "en progreso"})


class RecepcionTapizadoError(ValueError):
    pass


def _vinculos(ticket):
    return list(getattr(ticket, "aparatos_asociados", None) or [])


def resumen_recepcion_tapizado(ticket):
    """Conteo derivado de registros, nunca persistir un porcentaje separado."""
    if getattr(ticket, "tipo_trabajo", None) != TIPO_TRABAJO_TAPIZADO:
        return None

    vinculos = _vinculos(ticket)
    total = len(vinculos)
    recibidos = sum(
        1 for vinculo in vinculos
        if getattr(vinculo, "recibido_en_utc", None) is not None
    )
    return {
        "total": total,
        "recibidos": recibidos,
        "pendientes": total - recibidos,
        "porcentaje": round(recibidos * 100 / total) if total else 0,
        "completo": total > 0 and recibidos == total,
        "parcial": 0 < recibidos < total,
    }


def validar_recepcion_completa(ticket):
    """No permitir solicitar cierre mientras haya aparatos no recibidos."""
    avance = resumen_recepcion_tapizado(ticket)
    if avance is not None and not avance["completo"]:
        raise RecepcionTapizadoError(
            f"Tapizado incompleto: {avance['recibidos']} de {avance['total']} "
            "aparatos recibidos. Registra todas las recepciones antes del cierre."
        )


def _usuario_editor(user, ticket, *, es_coordinador=False, es_jefe_regional=False):
    rol = str(getattr(user, "rol", "") or "").strip().upper()
    if rol in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}:
        return True

    # Un gerente puede certificar recepciones de su propia sucursal destino.
    if rol == "GERENTE":
        try:
            return int(user.sucursal_id) == int(
                ticket.sucursal_id_destino or ticket.sucursal_id
            )
        except (ValueError, TypeError):
            return False

    if es_coordinador or es_jefe_regional:
        return True

    # Los técnicos únicamente intervienen en tickets asignados a su usuario,
    # independientemente de que su perfil pueda leer otros equipos.
    if rol in {"SR_MANTENIMIENTO", "AUX_MANTENIMIENTO", "TECNICO", "MANTENIMIENTO"}:
        return bool(
            int(getattr(user, "department_id", 0) or 0) == 1
            and str(getattr(ticket, "asignado_a", "") or "").strip().casefold()
                == str(getattr(user, "username", "") or "").strip().casefold()
            and bool(str(getattr(user, "username", "") or "").strip())
        )

    return False


def puede_editar_recepcion_tapizado(
    user, ticket, *, es_coordinador=False, es_jefe_regional=False
):
    return bool(
        user is not None
        and getattr(ticket, "tipo_trabajo", None) == TIPO_TRABAJO_TAPIZADO
        and str(getattr(ticket, "estado", "") or "").strip().lower()
            in ESTADOS_EDITABLES
        and _usuario_editor(
            user, ticket,
            es_coordinador=es_coordinador,
            es_jefe_regional=es_jefe_regional,
        )
    )


def actualizar_recepcion_tapizado(
    ticket, *, inventario_id, recibido, actor, motivo=None,
    marca_historial=flag_modified, momento=None
):
    """Modifica un vínculo y crea evento de auditoría. El endpoint hace commit.

    En reversión se requiere motivo. No modifica estado global ni inventario.
    """
    if getattr(ticket, "tipo_trabajo", None) != TIPO_TRABAJO_TAPIZADO:
        raise RecepcionTapizadoError("Este ticket no es de tapizado.")

    if str(getattr(ticket, "estado", "") or "").strip().lower() not in ESTADOS_EDITABLES:
        raise RecepcionTapizadoError("Solo puede modificarse tapizado abierto o en progreso.")

    if not isinstance(recibido, bool):
        raise RecepcionTapizadoError("recibido debe ser booleano.")

    if not isinstance(inventario_id, int) or isinstance(inventario_id, bool) or inventario_id <= 0:
        raise RecepcionTapizadoError("Aparato inválido.")

    if motivo is not None and (
        not isinstance(motivo, str) or len(motivo.strip()) > 500
    ):
        raise RecepcionTapizadoError("La observación debe tener hasta 500 caracteres.")

    nota = (motivo or "").strip()
    links = [v for v in _vinculos(ticket) if v.inventario_id == inventario_id]
    if len(links) != 1:
        raise RecepcionTapizadoError("El aparato no pertenece a este ticket.")

    vinculo = links[0]
    anterior = vinculo.recibido_en_utc is not None
    if anterior == recibido:
        raise RecepcionTapizadoError("La recepción de este aparato ya tiene ese estado.")
    if anterior and not recibido and not nota:
        raise RecepcionTapizadoError("Indica el motivo para revertir una recepción.")

    ahora = momento or datetime.now(timezone.utc)
    vinculo.recibido_en_utc = ahora if recibido else None
    vinculo.recibido_por = str(actor).strip() if recibido else None

    equipo = getattr(vinculo, "inventario", None)
    history = list(getattr(ticket, "historial_fechas", None) or [])
    history.append({
        "tipo": "tapizado_recepcion_aparato_v1",
        "origen": "tapizado_m4",
        "fechaCambio": ahora.isoformat(),
        "cambiadoPor": str(actor).strip(),
        "motivo": nota or (
            "Aparato recibido de tapicería." if recibido
            else "Recepción revertida."
        ),
        "inventario_id": inventario_id,
        "codigo_interno": str(getattr(equipo, "codigo_interno", "") or ""),
        "aparato_nombre": str(getattr(equipo, "nombre", "") or ""),
        "recibido_anterior": anterior,
        "recibido_nuevo": recibido,
    })
    history.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or ""),
        reverse=True,
    )
    ticket.historial_fechas = history
    marca_historial(ticket, "historial_fechas")
    return resumen_recepcion_tapizado(ticket)
