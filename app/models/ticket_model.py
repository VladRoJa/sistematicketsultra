# app/models/ticket_model.py
from flask import json, jsonify
from .database import get_db_connection
from datetime import datetime

class Ticket:
    def __init__(self, id, titulo, descripcion, username, estado, fecha_creacion, sucursal_id, fecha_finalizado=None):
        self.id = id
        self.titulo = titulo
        self.descripcion = descripcion
        self.username = username
        self.estado = estado
        self.fecha_creacion = fecha_creacion
        self.sucursal_id = sucursal_id
        self.fecha_finalizado = fecha_finalizado
        
    def to_dict(self):
        return {
            'id': self.id,
            'titulo': self.titulo,
            'descripcion': self.descripcion,
            'username': self.username,
            'estado': self.estado,
            'fecha_creacion': self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S'),
            'sucursal_id': self.sucursal_id,
            'fecha_finalizado': self.fecha_finalizado.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_finalizado else None
        }

    @staticmethod
    def get_tickets(estado="todos", sucursal_id=None, limit=None, sort=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        sql = "SELECT id, titulo, descripcion, username, estado, fecha_creacion, sucursal_id, fecha_finalizado FROM tickets"
        val = []

        if estado != 'todos':
            sql += " WHERE estado = %s"
            val.append(estado)

        if sucursal_id and sucursal_id != 1000:
            sql += " AND sucursal_id = %s" if estado != 'todos' else " WHERE sucursal_id = %s"
            val.append(sucursal_id)

        if sort:
            sql += " ORDER BY fecha_creacion DESC"

        if limit:
            sql += f" LIMIT {limit}"

        try:
            print(f"📌 Ejecutando SQL: {sql} con valores: {val}")  
            cursor.execute(sql, tuple(val))  
            tickets_data = cursor.fetchall()

            if not tickets_data:
                print("🔹 No se encontraron tickets en la base de datos.")
                return []  

            cursor.close()
            conn.close()
            return tickets_data  

        except Exception as e:
            print(f"❌ Error en la consulta SQL: {e}")
            cursor.close()
            conn.close()
            return None
        
    @staticmethod
    def get_by_id(id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, titulo, descripcion, username, estado, fecha_creacion, sucursal_id, fecha_finalizado FROM tickets WHERE id = %s", (id,))
        data = cursor.fetchone()
        conn.close()
        if data:
            return Ticket(**data)  
        return None

    @staticmethod
    def create_ticket(titulo, descripcion, username):
        conn = get_db_connection()
        cursor = conn.cursor()

        estado = 'abierto'
        fecha_creacion = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        sql = "INSERT INTO tickets (titulo, descripcion, username, estado, fecha_creacion) VALUES (%s, %s, %s, %s, %s)"
        val = (titulo, descripcion, username, estado, fecha_creacion)

        try:
            cursor.execute(sql, val)
            conn.commit()
            ticket_id = cursor.lastrowid
            cursor.close()
            conn.close()
            return Ticket.get_by_id(ticket_id)  # Retornar el ticket creado
        except Exception as e:
            print(f"❌ Error al insertar ticket en BD: {e}")
            cursor.close()
            conn.close()
            return None
    
    @staticmethod
    def get_tickets_by_sucursal(sucursal_id):
        conn = get_db_connection()  # Obtener conexión a la base de datos
        cursor = conn.cursor(dictionary=True)
               
        try:
            query = "SELECT * FROM tickets WHERE sucursal_id = %s"
            cursor.execute(query, (sucursal_id,))
            tickets = cursor.fetchall()
            return tickets
        except Exception as e:
            print(f"❌ Error en get_tickets_by_sucursal: {e}")
            return None

@staticmethod
def update_ticket_status(id, nuevo_estado, fecha_finalizado=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if nuevo_estado == 'finalizado':
        sql = "UPDATE tickets SET estado = %s, fecha_finalizado = %s WHERE id = %s"
        val = (nuevo_estado, fecha_finalizado, id)
    else:
        sql = "UPDATE tickets SET estado = %s WHERE id = %s"
        val = (nuevo_estado, id)

    cursor.execute(sql, val)
    conn.commit()

    if cursor.rowcount > 0:
        updated_ticket = Ticket.get_by_id(id)  # Obtener el ticket actualizado
        return updated_ticket

    cursor.close()
    conn.close()
    return None

