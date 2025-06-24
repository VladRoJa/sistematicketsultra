# ❓ Preguntas frecuentes (FAQ) – Sistema de Tickets UltraGym

---

## 1. Hice un cambio en el código, pero no lo veo en la web. ¿Qué hago?

- **¿Guardaste el archivo?**  
- **¿Reiniciaste el servidor?**  
  - Backend: Detén y vuelve a iniciar con `flask run`
  - Frontend: Si ya estaba corriendo con `ng serve`, usualmente recarga solo, pero a veces hay que detenerlo y volver a correr `ng serve --open`
- **¿Limpiaste la caché del navegador?**  
  - Prueba Ctrl+Shift+R para forzar recarga

---

## 2. ¿Dónde veo los errores?

- **Frontend:**  
  - Abre la consola de tu navegador (F12 o Ctrl+Shift+I)
- **Backend:**  
  - En la terminal donde corre Flask. Los errores se imprimen ahí.
- **Base de datos:**  
  - Si hay problemas de conexión, también se ven en la consola del backend

---

## 3. ¿Cómo agrego un nuevo usuario?

- Por ahora, los usuarios se agregan directamente en la base de datos o mediante endpoints del backend (consulta a quien administra el sistema para el método actual).
- Si tienes acceso, puedes hacerlo insertando en la tabla `usuarios` (PostgreSQL).

---

## 4. ¿Por qué mis cambios de validaciones no se aplican?

- Recuerda que tanto el **frontend** como el **backend** pueden tener reglas de validación.
- Si cambiaste solo en Angular, el backend puede seguir rechazando datos incorrectos (o viceversa).
- Revisa ambos lados si tu cambio no surte efecto.

---

## 5. ¿Cómo sé si el sistema está usando la base de datos correcta?

- Verifica el archivo `.env` en la raíz del backend. Ahí está la URL de la base de datos que está usando Flask.
- Puedes imprimir la cadena de conexión en `config.py` para verificar.

---

## 6. ¿Cómo exporto tickets a Excel?

- Usa la función de exportar que aparece en la pantalla de ver tickets (`pantalla-ver-tickets`). Si tienes problemas, consulta los logs del backend.

---

## 7. ¿Puedo cambiar los nombres de las columnas (por ejemplo, “Sucursal” por “Área”)?

- Sí. Busca y reemplaza el texto en los componentes de Angular (y archivos de traducción si los hay).
- Si hay validaciones o lógica en backend que dependan del nombre, ajústalas también.

---

## 8. ¿Qué hago si “rompí” el sistema o sale un error grave?

- No te preocupes.  
  - Asegúrate de estar trabajando en una rama, así puedes volver a `main`.
  - Pregunta antes de borrar nada.
  - Si hay muchos errores, deshaz el último cambio o vuelve a clonar el repo.

---