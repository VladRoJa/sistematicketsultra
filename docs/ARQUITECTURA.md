# 🏗️ Arquitectura del Sistema de Tickets UltraGym

Este documento explica de manera sencilla cómo está armado el sistema, cómo se comunican sus partes principales y cómo fluye la información desde que se crea un ticket hasta que se consulta o resuelve.

---

## 🔸 Estructura general

- **Frontend:**  
  Aplicación Angular (`frontend-angular/`)  
  Aquí interactúan los usuarios (crean tickets, ven reportes, etc.).

- **Backend:**  
  API REST construida con Flask (`/app`)  
  Aquí están las reglas de negocio, lógica y conexión a la base de datos.

- **Base de datos:**  
  PostgreSQL  
  Guarda la información de tickets, usuarios, historial, etc.

---

## 🔸 Flujo principal: “Crear y gestionar un ticket”

1. **El usuario llena un formulario en Angular**  
   (Por ejemplo, para reportar una incidencia).
2. **El frontend envía la información vía API**  
   (Usando HTTP POST a una ruta del backend, ej: `/api/tickets`).
3. **El backend recibe, valida y guarda el ticket**  
   (En la base de datos, aplicando lógica de negocio).
4. **El backend responde con el resultado**  
   (Por ejemplo, el ID del ticket creado).
5. **El frontend actualiza la interfaz**  
   (Muestra confirmación, actualiza listas, etc.).

---

## 🔸 Entidades principales

- **Ticket:**  
  El registro principal del sistema.  
  Campos básicos: descripción, usuario que reporta, sucursal/departamento, estado, fecha de creación, fecha de solución, historial de cambios.

- **Usuario:**  
  Persona que crea o resuelve tickets.  
  Campos: nombre, correo, rol (admin, técnico, usuario normal).

- **Sucursal/Departamento:**  
  Área o sucursal donde ocurre la incidencia.  
  (En sistemas adaptados, este nombre puede cambiar según el rubro).

- **Historial de cambios:**  
  Registro de todas las modificaciones importantes a cada ticket  
  (quién cambió qué, cuándo y por qué).

---

## 🔸 Estructura de carpetas (resumida)

/app/ # Backend Flask
/models/ # Modelos de datos (Ticket, Usuario, etc.)
/routes/ # Endpoints API
/frontend-angular/ # Frontend Angular
/src/app/components/ # Componentes principales (pantallas, formularios)
/src/app/utils/ # Helpers y utilidades
/config-examples/ # Ejemplo de .env
/docs/ # Documentación adicional

yaml
Copiar
Editar

---

## 🔸 Ejemplo de flujo: creación de ticket

```mermaid
sequenceDiagram
    participant Usuario
    participant Frontend
    participant Backend
    participant BD

    Usuario->>Frontend: Llena formulario de ticket
    Frontend->>Backend: POST /api/tickets (datos)
    Backend->>BD: Inserta nuevo ticket
    BD-->>Backend: Ticket guardado
    Backend-->>Frontend: Respuesta con ID/ticket
    Frontend-->>Usuario: Muestra confirmación
🔸 Cosas importantes a considerar
Validación:
La mayoría de las reglas de negocio (por ejemplo, “no dejar campos vacíos”) se aplican en el backend.

Fechas:
Todas las fechas se almacenan en formato UTC en la base de datos y se formatean en frontend para mostrar según zona horaria.

Adaptabilidad:
El sistema está pensado para que el nombre de las entidades principales pueda cambiar según el giro (ejemplo: “Sucursal” en gimnasio, “Propiedad” en inmobiliaria). Los cambios visuales se hacen en el frontend.

