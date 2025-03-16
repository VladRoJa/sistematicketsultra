# app/models/ticket_model.py
from flask import json, jsonify
from .database import get_db_connection
from datetime import datetime
import pytz
import locale

locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')

class Ticket:
    def __init__(self, id, descripcion, username, estado, fecha_creacion, id_sucursal, departamento_id, criticidad, categoria, fecha_solucion, historial_fechas, fecha_finalizado=None):
        self.id = id
        self.descripcion = descripcion
        self.username = username
        self.estado = estado
        self.fecha_creacion = fecha_creacion
        self.id_sucursal = id_sucursal
        self.departamento_id = departamento_id
        self.criticidad = criticidad
        self.categoria = categoria
        self.fecha_finalizado = fecha_finalizado
        self.fecha_solucion = fecha_solucion
        self.historial_fechas = historial_fechas
        
    def to_dict(self):
        tz = pytz.timezone('America/Tijuana')
        fecha_creacion_local = self.fecha_creacion.replace(tzinfo=pytz.utc).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S') if self.fecha_creacion else "N/A"
        fecha_finalizado_local = self.fecha_finalizado.replace(tzinfo=pytz.utc).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S') if self.fecha_finalizado else "N/A"

        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'username': self.username,
            'estado': self.estado,
            'fecha_creacion': fecha_creacion_local,
            'id_sucursal': self.id_sucursal,
            'departamento_id': self.departamento_id,
            'criticidad': self.criticidad,
            'categoria': self.categoria,
            'fecha_finalizado': fecha_finalizado_local
        }

    @staticmethod
    def create_ticket(descripcion, username, id_sucursal, departamento_id, criticidad, categoria):
        print(f"🔍 Creando ticket con: Descripcion={descripcion}, Usuario={username}, Sucursal={id_sucursal}, Departamento={departamento_id}, Criticidad={criticidad}, Categoría={categoria}")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
         # 🔴 Asegúrate de que criticidad es un entero
        if not isinstance(criticidad, int):
            print(f"⚠️ Error: Criticidad no es un entero válido: {criticidad}")
            return None
        
        query = "INSERT INTO tickets ( descripcion, username, id_sucursal, estado, departamento_id, criticidad, categoria) VALUES (%s, %s, %s, 'abierto', %s, %s, %s)"
        cursor.execute(query, (descripcion, username, id_sucursal, departamento_id, criticidad, categoria))
        conn.commit()
        ticket_id = cursor.lastrowid
        cursor.close()
        conn.close()

        print(f"✅ Ticket creado con ID: {ticket_id}")
        return ticket_id

    @staticmethod
    def update_ticket_status(id, nuevo_estado, criticidad=None, categoria=None):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            query = "UPDATE tickets SET estado = %s"
            values = [nuevo_estado]

            if criticidad is not None:
                query += ", criticidad = %s"
                values.append(criticidad)

            if categoria is not None:
                query += ", categoria = %s"
                values.append(categoria)

            query += " WHERE id = %s"
            values.append(id)

            cursor.execute(query, tuple(values))
            conn.commit()

            if cursor.rowcount > 0:
                cursor.execute("SELECT * FROM tickets WHERE id = %s", (id,))
                ticket = cursor.fetchone()
                cursor.close()
                conn.close()
                return ticket

            cursor.close()
            conn.close()
            return None

        except Exception as e:
            return None
            
    @staticmethod
    def get_by_id(id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (id,))
        data = cursor.fetchone()
        conn.close()
        if data:
            return Ticket(**data)
        return None
