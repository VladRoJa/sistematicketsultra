# 🛠️ Guía de cambios frecuentes en el Sistema de Tickets UltraGym

Aquí encontrarás instrucciones sencillas para realizar los cambios más comunes en el sistema.  
Si tienes dudas sobre algún paso, pregunta o revisa los otros documentos en la carpeta `docs/`.

---

## 1. Agregar un nuevo campo a los tickets

### a) **En el backend (Flask):**
1. Ve a `app/models/ticket_model.py`
2. Agrega el nuevo campo a la clase `Ticket`
3. Si necesitas, ajusta la migración o el script para la base de datos
4. Ve a `app/routes/ticket_routes.py` y permite que la API reciba/envíe el nuevo campo

### b) **En el frontend (Angular):**
1. Ve a `frontend-angular/src/app/components/pantalla-crear-ticket/`
2. Modifica el formulario para incluir el nuevo campo
3. Si el campo debe verse en otras pantallas, repite el paso en esos componentes
4. Actualiza cualquier helper que maneje el ticket (por ejemplo: validaciones en `/utils/`)

### c) **Probar**
1. Levanta backend y frontend
2. Crea un ticket de prueba
3. Revisa en la base de datos que el nuevo campo se guardó correctamente

---

## 2. Cambiar textos o nombres de columnas/entidades

1. Busca el texto a cambiar en los componentes de Angular (por ejemplo, en `/src/app/components/` o `/src/assets/i18n/` si usas archivos de traducción)
2. Cambia el nombre en las plantillas HTML y archivos TypeScript donde aparezca
3. Si el backend devuelve el nombre en las respuestas, revisa que sea coherente en `ticket_routes.py`
4. Prueba en la interfaz que el nuevo nombre aparece correctamente

> **Ejemplo:** Cambiar "Sucursal" por "Propiedad"  
> Busca todas las apariciones de "Sucursal" en el frontend y reemplaza por "Propiedad".

---

## 3. Crear un nuevo reporte

1. Define qué datos y filtros necesitas
2. Crea una nueva ruta en `app/routes/reportes_routes.py` (puedes copiar de un reporte existente)
3. Haz la consulta a la base de datos y devuelve los datos necesarios
4. En el frontend, crea un nuevo componente en `frontend-angular/src/app/components/reportes/`
5. Consume el endpoint desde Angular y muestra la información en tablas o gráficos

---

## 4. Modificar filtros en la pantalla de tickets

1. Ve a `frontend-angular/src/app/components/pantalla-ver-tickets/`
2. Modifica la lógica de los filtros en el TypeScript correspondiente
3. Ajusta los helpers en `/utils/` si es necesario
4. Verifica que los filtros funcionen bien y no rompan la paginación ni la exportación

---

## 5. Cambiar validaciones en formularios

1. Ve al componente correspondiente (por ejemplo, `pantalla-crear-ticket`)
2. Modifica las reglas de validación en el archivo TypeScript
3. Si hay validaciones importantes, refuérzalas también en el backend
4. Prueba que el formulario no deje pasar datos incorrectos

---

## 6. Probar tus cambios antes de subir

- Siempre **levanta backend y frontend** después de cualquier cambio
- Haz pruebas creando/modificando tickets y usando la función que editaste
- Revisa la consola del navegador (frontend) y la terminal (backend) para ver si hay errores

---