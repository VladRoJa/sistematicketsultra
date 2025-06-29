# 🎟️ Sistema de Tickets UltraGym

Bienvenido/a al **Sistema de Tickets UltraGym**.  
Este proyecto permite la gestión de tickets/incidencias para empresas con múltiples sucursales, pero está diseñado para ser adaptable a diferentes tipos de negocio (gimnasios, inmobiliarias, etc.).

---

## 🚀 ¿Qué es este sistema?
Un sistema de tickets multiusuario para registrar, dar seguimiento y resolver incidencias, con módulos para administración, reportes y gestión por áreas/departamentos.

- **Backend:** Python (Flask, SQLAlchemy)
- **Frontend:** Angular + Angular Material + TailwindCSS
- **Base de datos:** PostgreSQL

---

## 🖥️ Instalación rápida (modo local)

1. **Clona este repositorio**  
   `git clone https://github.com/VladRoJa/sistematicketsultra.git`
2. **Instala las dependencias**
   - Backend:  
     ```bash
     cd sistematicketsultra
     python -m venv .venv
     source .venv/bin/activate   # O .venv\Scripts\activate en Windows
     pip install -r requirements.txt
     ```
   - Frontend:  
     ```bash
     cd frontend-angular
     npm install
     ```
3. **Configura variables de entorno**  
   - Copia y renombra el archivo  
     `config-examples/.env.example`  
     a  
     `.env` en la raíz del backend.  
   - Edita los valores según tu entorno local (DB, JWT_SECRET, etc.)
4. **Levanta los servidores**  
   - Backend:  
     ```bash
     flask run
     ```
   - Frontend:  
     ```bash
     ng serve --open
     ```

---

## 🗂️ Estructura de carpetas

- `/app/`  
  Código del backend (Flask).
- `/frontend-angular/`  
  Aplicación Angular (frontend).
- `/config-examples/`  
  Ejemplos de archivos de configuración.
- `/scripts/`  
  Scripts útiles (migraciones, limpieza, utilidades).
- `/docs/`  
  Documentación extendida (arquitectura, guías, FAQ, etc).

---

## 🧭 ¿Por dónde empiezo?

- [Guía de primeros cambios](docs/GUIA_CAMBIOS.md)  
- [Preguntas frecuentes y problemas conocidos](docs/FAQ.md)
- [Arquitectura y flujo general del sistema](docs/ARQUITECTURA.md)
- [Guía para contribuir](CONTRIBUTING.md)

---

## 👨‍💻 Cambios frecuentes

- Agregar campos a formularios y modelos
- Ajustar nombres de columnas/entidades para otros rubros
- Crear nuevos reportes

Ver: [docs/GUIA_CAMBIOS.md](docs/GUIA_CAMBIOS.md)

---

## 🏗️ ¿Cómo funciona internamente?
Consulta el archivo  
[docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)  
para entender el flujo de datos, las entidades principales y la comunicación entre frontend y backend.

---

## 🤝 Contribuir y mejorar

¡Tu ayuda es bienvenida!  
Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para ver cómo colaborar, proponer cambios o arreglar bugs.

---

## 📬 Contacto y dudas

Para cualquier duda o para reportar problemas:  
[Tu correo o WhatsApp]  
(agrega tu preferido aquí)

---

