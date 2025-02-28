# app/models/ticket_model.py
from flask import json, jsonify
from .database import get_db_connection
from datetime import datetime
import pytz
import locale

locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')

class Ticket:
    def __init__(self, id, titulo, descripcion, username, estado, fecha_creacion, id_sucursal, fecha_finalizado=None):
        self.id = id
        self.titulo = titulo
        self.descripcion = descripcion
        self.username = username
        self.estado = estado
        self.fecha_creacion = fecha_creacion
        self.id_sucursal = id_sucursal
        self.fecha_finalizado = fecha_finalizado
        
    def to_dict(self):
        
        tz = pytz.timezone('America/Tijuana')

        fecha_creacion_local = self.fecha_creacion.replace(tzinfo=pytz.utc).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S') if self.fecha_creacion else "N/A"
        fecha_finalizado_local = self.fecha_finalizado.replace(tzinfo=pytz.utc).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S') if self.fecha_finalizado else "N/A"


        return {
            'id': self.id,
            'titulo': self.titulo,
            'descripcion': self.descripcion,
            'username': self.username,
            'estado': self.estado,
            'fecha_creacion': fecha_creacion_local,
            'id_sucursal': self.id_sucursal,
            'fecha_finalizado': fecha_finalizado_local
        }

    @staticmethod
    def get_tickets(estado="todos", id_sucursal=None, limit=None, sort=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        sql = "SELECT id, titulo, descripcion, username, estado, fecha_creacion, id_sucursal, fecha_finalizado FROM tickets"
        val = []

        if estado != 'todos':
            sql += " WHERE estado = %s"
            val.append(estado)

        if id_sucursal and id_sucursal != 1000:
            sql += " AND id_sucursal = %s" if estado != 'todos' else " WHERE id_sucursal = %s"
            val.append(id_sucursal)

        if sort:
            sql += " ORDER BY fecha_creacion DESC"

        if limit:
            sql += f" LIMIT {limit}"

        try:
            print(f"📌 Ejecutando SQL: {sql} con valores: {val}")  
            cursor.execute(sql, tuple(val))  
            tickets_data = cursor.fetchall()

             # Convertir fechas a la zona horaria de Mexicali antes de enviarlas
            tz = pytz.timezone('America/Tijuana')
            for ticket in tickets_data:
                if ticket['fecha_creacion']:
                    ticket['fecha_creacion'] = ticket['fecha_creacion'].astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')
                if ticket['fecha_finalizado']:
                    ticket['fecha_finalizado'] = ticket['fecha_finalizado'].astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')

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
        cursor.execute("SELECT id, titulo, descripcion, username, estado, fecha_creacion, id_sucursal, fecha_finalizado FROM tickets WHERE id = %s", (id,))
        data = cursor.fetchone()
        conn.close()
        if data:
            return Ticket(**data)  
        return None

    @staticmethod
    def create_ticket(titulo, descripcion, username, id_sucursal):
        conn = get_db_connection()
        cursor = conn.cursor()

        estado = 'abierto'
        tz = pytz.timezone('America/Tijuana') 
        fecha_creacion = datetime.now(pytz.utc).astimezone(tz)

        sql = "INSERT INTO tickets (titulo, descripcion, username, estado, fecha_creacion, id_sucursal) VALUES (%s, %s, %s, %s, %s, %s)"
        val = (titulo, descripcion, username, estado, fecha_creacion.strftime('%Y-%m-%d %H:%M:%S'), id_sucursal)

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
    def get_tickets_by_sucursal(id_sucursal):
        conn = get_db_connection()  # Obtener conexión a la base de datos
        cursor = conn.cursor(dictionary=True)
               
        try:
            query = "SELECT * FROM tickets WHERE id_sucursal = %s"
            cursor.execute(query, (id_sucursal,))
            tickets = cursor.fetchall()
            return tickets
        except Exception as e:
            print(f"❌ Error en get_tickets_by_sucursal: {e}")
            return None

@staticmethod
def update_ticket_status(id, nuevo_estado, fecha_finalizado=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    tz = pytz.timezone('America/Tijuana')

    if nuevo_estado == 'finalizado':
        fecha_finalizado_tz = datetime.now(pytz.utc).astimezone(tz)
        sql = "UPDATE tickets SET estado = %s, fecha_finalizado = %s WHERE id = %s"
        val = (nuevo_estado, fecha_finalizado_tz.strftime('%Y-%m-%d %H:%M:%S'), id)
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

