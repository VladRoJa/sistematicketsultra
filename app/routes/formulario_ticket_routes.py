# app/routes/formulario_ticket_routes.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models.formulario_ticket import FormularioTicket

formulario_ticket_bp = Blueprint('formulario_ticket', __name__)

@formulario_ticket_bp.route('/<int:formulario_id>', methods=['GET'])
@jwt_required()
def obtener_formulario(formulario_id):
    formulario = FormularioTicket.query.get(formulario_id)
    if not formulario:
        return jsonify({"mensaje": "Formulario no encontrado"}), 404

    # Puedes filtrar campos si necesitas solo algunos tipos/campos visibles, etc.
    campos = [
        {
            "id": campo.id,
            "nombre_campo": campo.nombre_campo,
            "etiqueta": campo.etiqueta,
            "tipo": campo.tipo,
            "obligatorio": campo.obligatorio,
            "orden": campo.orden,
            "opciones": campo.opciones,
            "referencia_arbol": campo.referencia_arbol,
            "referencia_inventario": campo.referencia_inventario,
            "solo_si_nivel": campo.solo_si_nivel,
        }
        for campo in sorted(formulario.campos, key=lambda x: x.orden)
    ]
    return jsonify({
        "id": formulario.id,
        "nombre": formulario.nombre,
        "departamento_id": formulario.departamento_id,
        "tipo_reporte": formulario.tipo_reporte,
        "campos": campos
    })


@formulario_ticket_bp.route('/lista', methods=['GET'])
@jwt_required()
def lista_formularios():
    """
    Regresa lista de formularios activos, opcionalmente filtrados por departamento
    ?departamento_id=...
    """
    departamento_id = request.args.get('departamento_id', type=int)
    query = FormularioTicket.query.filter_by(activo=True)
    if departamento_id:
        query = query.filter_by(departamento_id=departamento_id)
    formularios = query.all()
    return jsonify([
        {
            "id": f.id,
            "nombre": f.nombre,
            "departamento_id": f.departamento_id,
            "tipo_reporte": f.tipo_reporte,
        }
        for f in formularios
    ])


# OPCIONAL: endpoint para obtener solo los departamentos con formularios activos
@formulario_ticket_bp.route('/departamentos_disponibles', methods=['GET'])
@jwt_required()
def departamentos_disponibles():
    """
    Devuelve lista única de departamentos que tienen formularios activos,
    útil para mostrar solo opciones válidas en el frontend.
    """
    departamentos = (
        FormularioTicket.query
        .filter_by(activo=True)
        .with_entities(FormularioTicket.departamento_id)
        .distinct()
        .all()
    )
    # Regresa solo los ids, el frontend los puede cruzar con el catálogo
    return jsonify([d[0] for d in departamentos])
