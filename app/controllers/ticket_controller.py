# app/controllers/ticket_controller.py
from flask import jsonify, session, request
from app.models.ticket_model import create_ticket, get_tickets, update_ticket_status

class TicketController:
    def create_ticket(self, data):
        
        print(f"📌 Sesión antes de procesar ticket: {dict(session)}")
        descripcion = data.get('descripcion')
        username = data.get('username')
        id_sucursal = session.get('id_sucursal')
        
        print("📌 Sesión en Flask antes de responder:", {dict(session)})
        
        ticket = create_ticket( descripcion, username, id_sucursal)
        
        print("📌 Sesión en Flask después:", {dict(session)})
        
        return jsonify({
            'mensaje': 'Ticket creado exitosamente',
            'id': ticket['id'],
            'estado': ticket['estado'],
            'fecha_creacion': ticket['fecha_creacion']
        }), 201

        
        
    def get_tickets(self, estado):
        id_sucursal = session.get('id_sucursal')

        # 🔹 Recibir parámetros de paginación desde la URL
        page = request.args.get('page', default=1, type=int)
        per_page = request.args.get('per_page', default=15, type=int)
        offset = (page - 1) * per_page  # 🔥 Calcular desde dónde empezar la consulta

        # 🔹 Obtener los tickets con paginación
        tickets, total_tickets = get_tickets(estado, id_sucursal, per_page, offset)

        return jsonify({
            'tickets': tickets,
            'total_tickets': total_tickets,  # 🔥 Número total de tickets (para calcular páginas)
            'page': page,
            'per_page': per_page
        }), 200


    def update_ticket_status(self, id, data):
        nuevo_estado = data.get('estado')
        ticket = update_ticket_status(id, nuevo_estado)
        if ticket:
            return jsonify({
                'mensaje': 'Estado del ticket actualizado exitosamente',
                'ticket': ticket
            }), 200
        else:
            return jsonify({'mensaje': 'Ticket no encontrado'}), 404

# Crea una instancia de la clase
ticket_controller = TicketController()