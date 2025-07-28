# C:\Users\Vladimir\Documents\Sistema tickets\app\controllers\ticket_controller.py

# -------------------------------------------------------------------------------
# CONTROLADOR DE TICKETS CON JWT
# -------------------------------------------------------------------------------

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.extensions import db
from app.models.inventario import InventarioGeneral

class TicketController:

    # ---------------------------------------------------------------------------
    # CREAR TICKET
    # ---------------------------------------------------------------------------
    def create_ticket(self, data):
        try:
            current_user_id = get_jwt_identity()
            user = UserORM.get_by_id(current_user_id)

            if not user:
                return jsonify({'mensaje': 'Usuario no encontrado'}), 404

            descripcion = data.get('descripcion')
            categoria = data.get('categoria')
            if not (descripcion and categoria):
                return jsonify({'mensaje': 'Datos incompletos'}), 400

            # Nuevo: Valida que el aparato/artículo exista en InventarioGeneral
            aparato_id = data.get('aparato_id')
            if aparato_id:
                inv = InventarioGeneral.query.get(aparato_id)
                if not inv:
                    return jsonify({'mensaje': 'El aparato/artículo referenciado no existe en inventario'}), 400

            nuevo_ticket = Ticket.create_ticket(
                descripcion=descripcion,
                username=user.username,
                sucursal_id=user.sucursal_id,
                departamento_id=data.get('departamento_id', 1),
                criticidad=data.get('criticidad', 1),
                categoria=categoria,
                subcategoria=data.get('subcategoria'),
                detalle=data.get('detalle'),
                aparato_id=aparato_id,
                problema_detectado=data.get('problema_detectado'),
                necesita_refaccion=data.get('necesita_refaccion', False),
                descripcion_refaccion=data.get('descripcion_refaccion')
            )

            return jsonify({
                'mensaje': 'Ticket creado exitosamente',
                'ticket': nuevo_ticket.to_dict()
            }), 201

        except Exception as e:
            print(f"❌ Error en create_ticket: {e}")
            db.session.rollback()
            return jsonify({'mensaje': 'Error interno al crear ticket'}), 500

    # ---------------------------------------------------------------------------
    # OBTENER TICKETS (PAGINADOS)
    # ---------------------------------------------------------------------------
    def get_tickets(self, estado):
        try:
            current_user_id = get_jwt_identity()
            user = UserORM.get_by_id(current_user_id)

            if not user:
                return jsonify({'mensaje': 'Usuario no encontrado'}), 404

            page = request.args.get('page', default=1, type=int)
            per_page = request.args.get('per_page', default=15, type=int)
            offset = (page - 1) * per_page

            query = Ticket.query.filter(Ticket.sucursal_id == user.sucursal_id)
            if estado:
                query = query.filter(Ticket.estado == estado)

            total_tickets = query.count()
            tickets = query.order_by(Ticket.fecha_creacion.desc()).limit(per_page).offset(offset).all()
            tickets_data = [ticket.to_dict() for ticket in tickets]

            return jsonify({
                'tickets': tickets_data,
                'total_tickets': total_tickets,
                'page': page,
                'per_page': per_page
            }), 200

        except Exception as e:
            print(f"❌ Error en get_tickets: {e}")
            return jsonify({'mensaje': 'Error interno al obtener tickets'}), 500

    # ---------------------------------------------------------------------------
    # ACTUALIZAR ESTADO DEL TICKET
    # ---------------------------------------------------------------------------
    def update_ticket_status(self, id, data):
        try:
            nuevo_estado = data.get('estado')

            if not nuevo_estado:
                return jsonify({'mensaje': 'Estado no proporcionado'}), 400

            ticket = Ticket.query.get(id)
            if not ticket:
                return jsonify({'mensaje': 'Ticket no encontrado'}), 404

            ticket.estado = nuevo_estado

            if nuevo_estado == 'finalizado':
                ticket.fecha_finalizado = db.func.now()

            db.session.commit()

            return jsonify({
                'mensaje': 'Estado del ticket actualizado exitosamente',
                'ticket': ticket.to_dict()
            }), 200

        except Exception as e:
            print(f"❌ Error en update_ticket_status: {e}")
            db.session.rollback()
            return jsonify({'mensaje': 'Error interno al actualizar ticket'}), 500

# -------------------------------------------------------------------------------
# INSTANCIA DEL CONTROLADOR
# -------------------------------------------------------------------------------
ticket_controller = TicketController()

