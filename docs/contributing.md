# 🤝 Guía para contribuir al Sistema de Tickets UltraGym

¡Gracias por tu interés en mejorar este proyecto!  
Aquí te explicamos cómo puedes colaborar de manera sencilla y efectiva, aunque nunca hayas contribuido a un repositorio antes.

---

## 🟢 ¿Por dónde empezar?

1. **Lee el [README.md](README.md)** para entender el propósito general del sistema.
2. **Consulta la [Guía de Cambios Frecuentes](docs/GUIA_CAMBIOS.md)** para saber dónde modificar si quieres agregar campos, cambiar nombres o hacer reportes.
3. Si tienes dudas sobre cómo funciona algo, revisa primero [docs/FAQ.md](docs/FAQ.md) y [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

---

## 📝 ¿Cómo propongo un cambio?

- Antes de cambiar algo, crea una nueva rama basada en `main`:
  ```bash
  git checkout main
  git pull
  git checkout -b mi-nueva-rama
Realiza los cambios en los archivos necesarios.

Prueba localmente que todo siga funcionando (tanto backend como frontend).

Haz commits claros con mensajes descriptivos.
Ejemplo:

git commit -am "Agrego campo prioridad a los tickets"

Sube tu rama:

bash
Copiar
Editar
git push origin mi-nueva-rama
Abre un Pull Request en GitHub, explica brevemente tu cambio.

Si tienes dudas, pregunta antes de hacer cambios grandes.

🎯 Convenciones y buenas prácticas
Código limpio:

Usa nombres descriptivos en variables y funciones (en español).

Prefiere comentarios cuando algo no sea obvio.

Evita duplicar lógica, usa helpers cuando sea posible.

Estilo:

Respeta el estilo del código ya existente.

Para Angular y Flask, sigue la organización de carpetas y archivos como ya está en el proyecto.

Fechas:

Maneja fechas siempre en formato UTC en el backend.

Traducciones y nombres:

Si vas a cambiar textos/nombres para otro rubro, comenta qué cambios hiciste y por qué.

No subas datos sensibles:

No incluyas contraseñas, secretos o archivos .env reales.

📚 Archivos clave
Backend:

Modelos de datos: app/models/

Rutas/API: app/routes/

Configuración: .env y config.py

Frontend:

Componentes principales: frontend-angular/src/app/components/

Estilos y temas: frontend-angular/src/styles/

Helpers/utilidades: frontend-angular/src/app/utils/

Ejemplos de configuración:

config-examples/.env.example

🧑‍💻 Tips para aprender tocando el código
Haz cambios pequeños al principio (cambiar textos, modificar campos).

Usa console.log en Angular y print en Flask para ver el flujo de datos.

No temas romper algo, siempre puedes volver a la rama main.

Pregunta cualquier cosa que no entiendas. ¡Aquí aprendemos todos!