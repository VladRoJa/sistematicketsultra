# Issue #856 · Etapa E — Gate de seguridad y despliegue controlado

**Estado**: checklist preparado, **NO ejecutado en producción**.
Este documento no autoriza ninguna comunicación iVentas. El primer canario,
incluida la campaña #16, requiere autorización nueva y explícita del operador,
con número de campaña, child y destinatarios aprobados.

## 1. Invariantes obligatorias (GO / NO-GO)

1. CI: nuevo `Campaign V2 Stage E Safety Gates` PASS, CI existente de
   campañas/PG/Angular PASS para el commit que se vaya a promover.
2. **Ambos switches OFF** antes, durante y después del despliegue:
   `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=false`,
   `CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=false`.
   No basta apagar uno. Un 423 para el POST `/dispatch/execute` es sano.
3. No realizar pruebas POST con un child real. Para comprobar el bloqueo,
   usar mocks en CI; en producción solo GET autorizados para inspección.
4. PostgreSQL con respaldo probado y migraciones bajo Alembic; evitar
   edición manual de archivos o SQL correctivo en servidor.
5. Verificar portafolios candidatos B1 y relaciones B2/B3: todo Business ID,
   WABA y cuota declarada sin evidencia API permanece **no verificada por Meta**.
   No sembrar mapeos de los 26 canales ni deducirlos de cuentas publicitarias.
6. Nunca marcar `IN_FLIGHT`, `SUBMITTING`, `PROVIDER_ERROR`,
   `RECONCILIATION_REQUIRED` o `HELD` como reintentables automáticamente.
   La consola **no** reconcilia ni libera retenciones.
7. `APPROVED` / `RESERVED` / `READY` / `AUTHORIZED` no demuestran
   que se haya enviado. Solo datos persistidos de un child `SUBMITTED`
   pueden indicar aceptación; nunca afirmar entrega al destinatario.

## 2. Auditoría previa al despliegue (solo lectura)

Desde la **máquina del servidor**, únicamente después de que se confirme
qué commit exacto será promovido:

```bash
cd ~/sistematicketsultra
git status --short
git rev-parse HEAD
docker compose ps
docker compose exec -T backend python -m flask db current
docker compose exec -T backend python -m flask db heads
docker compose exec -T backend python - <<'PY'
from app import create_app
app = create_app()
with app.app_context():
    print("PROVIDER_SEND_ENABLED =", app.config.get("CAMPAIGN_V2_PROVIDER_SEND_ENABLED"))
    print("GOVERNED_DISPATCH_ENABLED =", app.config.get("CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED"))
PY
```

**NO-GO** si hay cambios locales, head inesperado, migraciones divergentes,
al menos un switch encendido, o servicio de web/scheduler sin salud.
Nunca imprimir variables de secretos/tokens.

## 3. Procedimiento de promoción (requiere aprobación de despliegue aparte)

El flujo no se ejecuta como parte del PR E. Al autorizarlo:

1. Confirmar un restore point y ventana operativa; guardar commit previo y
   copia de PostgreSQL fuera de la carpeta de trabajo del repositorio.
2. Respaldo lógico PostgreSQL sin imprimir credenciales (ejemplo sujeto a
   variables reales del servicio db):

   ```bash
   docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /ruta-segura/backup_pre_issue856.dump
   ```

   Verificar que el archivo exista, no sea cero y sea restaurable mediante
   mecanismo **aislado**; nunca restaurar sobre producción como prueba.
3. Repo local → commit → CI → merge → servidor `git pull --ff-only`.
   **No** editar código en servidor ni saltar GitHub.
4. Migrar con Alembic cuando corresponda: comprobar la cadena completa;
   B1 `b856port1014` y B2 `c856map1014` son acumulativas, pero la
   versión `head` real puede incluir cambios posteriores de otros módulos.
   Rechazar dos heads inesperados. Ejecutar upgrade solo tras el respaldo
   y revisar `flask db current` al terminar.
5. Reconstruir servicios aprobados con
   `docker compose up -d --build backend frontend`. No reiniciar
   schedulers innecesariamente.
6. Verificar backend con
   `curl -i --max-time 5 http://127.0.0.1:5000/`.
   Un 404 rápido puede ser respuesta sana del servidor Flask.
   Comprobar `docker compose ps`, trabajadores y logs sin tokens.
7. Navegación de humo por **GET/UI sin operaciones de escritura**:
   centro A, portafolios B1, evidencia B2/B3, modal QA C y consola D.
   Revisar 401/403 según permisos, errores 500 y todas las etiquetas
   `NO VERIFICADO`/estimación MXN. No congelar QA ni crear reservas.
8. Verificar de nuevo ambos switches OFF con lectura de configuración real
   y registrar hora America/Tijuana, commit, heads y operadores.

**Nota de orden:** si el nuevo backend usa modelos que requieren B1/B2,
coordinar una ventana breve y migración antes de exponer el servicio nuevo;
no asumir que reconstruir siempre primero es seguro. Decidir orden a partir
del estado real y salud observada en el paso 2.

## 4. Detener y recuperar

- **STOP** ante diferencias esquema-ORM, migración inválida, 5xx sostenidos,
  errores de permisos, cuota no verificable o cualquier sospecha de envío.
- Mantener switches OFF. Preservar el estado de la DB y capturar evidencia
  técnica (sin teléfonos completos, variables, tokens ni claves).
- Revertir código mediante **nuevo commit/PR de reversión y despliegue Git**,
  nunca parchear manualmente contenedores. No ejecutar `flask db downgrade`
  como rollback automático: puede destruir registros de auditoría.
- Restaurar DB solo si el procedimiento de recuperación fue aprobado y
  ensayado fuera de producción, valorando datos acumulados después del backup.
- Si un child está `SUBMITTING`/ambiguo, no volver a llamar POST; seguir
  conciliación explícita con evidencia de iVentas.

## 5. Gate separado para primer envío canario

**Fuera del alcance actual.** Antes de habilitar flags deben existir:
verificación documental de canal/WABA, plantilla compatible, blacklist,
cohorte congelada validada, costo MXN, cuota interna, identidades y permisos
backend, aprobación/cupo y autorización vigentes. Después, autorización
expresa y específica para **ese** child. Los flags no se encienden como prueba
de interfaz; el orden de ejecución es manual y no hay reintentos implícitos.
