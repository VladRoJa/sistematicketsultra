# app/routes/asistencia_routes.py

from flask import Blueprint, request, jsonify
from app.models.asistencia_model import RegistroAsistencia
from app.models.user_model import UserORM
from app.models.horario_general import HorarioGeneral
from app.models.bloque_horario import BloqueHorario
from app.models.empleado_horario_asignado import EmpleadoHorarioAsignado
from app.extensions import db
from datetime import datetime, date, time
from app.utils.semana_actual import get_semana_actual
from flask_jwt_extended import jwt_required

asistencia_bp = Blueprint('asistencia', __name__, url_prefix='/api/asistencia')

@asistencia_bp.route('/registrar', methods=['POST'])
@jwt_required()
def registrar_asistencia():
    data = request.get_json()
    usuario_id = data.get("usuario_id")
    sucursal_id = data.get("sucursal_id")

    now = datetime.now()
    hoy = now.date()
    hora_actual = now.time()
    dia_semana = hoy.weekday()  # 0=Lunes

    semana_actual = get_semana_actual(hoy)
    asignacion = EmpleadoHorarioAsignado.query.filter_by(usuario_id=usuario_id, activo=True).first()
    if not asignacion:
        return jsonify({"ok": False, "mensaje": "Empleado sin horario asignado."}), 400

    horario = HorarioGeneral.query.get(asignacion.horario_general_id)
    if not horario or horario.ciclo != semana_actual:
        return jsonify({"ok": False, "mensaje": "No hay horario para esta semana."}), 400

    bloques = BloqueHorario.query.filter_by(horario_general_id=horario.id, dia_semana=dia_semana).order_by(BloqueHorario.hora_inicio).all()
    if not bloques:
        return jsonify({"ok": False, "mensaje": "No hay bloques asignados para hoy."}), 400

    # Checadas registradas hoy
    registros_hoy = RegistroAsistencia.query.filter_by(usuario_id=usuario_id, sucursal_id=sucursal_id)\
        .filter(RegistroAsistencia.timestamp >= datetime.combine(hoy, time.min))\
        .filter(RegistroAsistencia.timestamp <= datetime.combine(hoy, time.max))\
        .all()
    checadas_hechas = [r.tipo_marcado for r in registros_hoy]

    # Arma las checadas esperadas (según bloques)
    checadas_esperadas = []
    for i, bloque in enumerate(bloques):
        if bloque.es_descanso:
            continue
        pref = 'm' if len(bloques) > 1 and i == 0 else 't' if len(bloques) > 1 else ''
        checadas_esperadas.append(f"entrada_{pref}".rstrip('_'))
        checadas_esperadas.append(f"salida_{pref}".rstrip('_'))

    # Identifica faltantes
    faltantes = [ch for ch in checadas_esperadas if ch not in checadas_hechas]

    # Lógica para determinar el tipo de checada que toca según hora
    tipo_marcado = None
    mensaje = ""
    proxima_checada = None

    for i, bloque in enumerate(bloques):
        if bloque.es_descanso:
            mensaje = "Hoy es tu día de descanso."
            tipo_marcado = "descanso"
            break

        pref = 'm' if len(bloques) > 1 and i == 0 else 't' if len(bloques) > 1 else ''

        # Entrada
        if hora_actual < bloque.hora_inicio:
            tipo_marcado = f"entrada_{pref}".rstrip('_')
            mensaje = f"Puntual, tu entrada es a las {bloque.hora_inicio.strftime('%H:%M')}"
            proxima_checada = {
                "tipo": tipo_marcado,
                "hora": bloque.hora_inicio.strftime('%H:%M')
            }
            break
        elif bloque.hora_inicio <= hora_actual < bloque.hora_fin:
            tipo_marcado = f"entrada_{pref}".rstrip('_') if f"entrada_{pref}".rstrip('_') in faltantes else f"salida_{pref}".rstrip('_')
            # Ya entró, le toca salida
            if tipo_marcado.startswith('entrada'):
                mensaje = "Retardo (checada de entrada, fuera de horario exacto)"
            else:
                mensaje = "Marca tu salida antes de que termine el bloque"
            proxima_checada = {
                "tipo": tipo_marcado,
                "hora": bloque.hora_fin.strftime('%H:%M')
            }
            break
        elif hora_actual >= bloque.hora_fin:
            tipo_marcado = f"salida_{pref}".rstrip('_')
            mensaje = "Checada fuera de horario (ya terminó el bloque)"
            # Busca la siguiente checada pendiente
            continue

    # Si ya hizo todas las checadas
    if not faltantes:
        return jsonify({
            "ok": True,
            "mensaje": "Ya completaste todas las checadas del día.",
            "tipo_marcado": tipo_marcado,
            "hora": now.strftime("%H:%M"),
            "proxima_checada": None,
            "faltantes": []
        }), 200

    # Registra si hay una checada válida
    if tipo_marcado and tipo_marcado in faltantes and tipo_marcado != "descanso":
        nueva = RegistroAsistencia(
            usuario_id=usuario_id,
            sucursal_id=sucursal_id,
            tipo_marcado=tipo_marcado,
            timestamp=now
        )
        db.session.add(nueva)
        db.session.commit()
        checadas_hechas.append(tipo_marcado)
        faltantes = [ch for ch in checadas_esperadas if ch not in checadas_hechas]

    return jsonify({
        "ok": True,
        "mensaje": mensaje or "Registro realizado.",
        "tipo_marcado": tipo_marcado,
        "hora": now.strftime("%H:%M"),
        "proxima_checada": proxima_checada,
        "faltantes": faltantes
    })

