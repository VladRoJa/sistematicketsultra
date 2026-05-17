/* ==========================================================================
   Suite Ultra Core v0.1 — Auditoría previa a migraciones
   ========================================================================== */

-- ==========================================================================
-- 1. Usuarios con departamento inválido
-- ==========================================================================

SELECT
  u.id,
  u.username,
  u.rol,
  u.department_id
FROM users u
LEFT JOIN departamentos d ON d.id = u.department_id
WHERE d.id IS NULL;


-- ==========================================================================
-- 2. Departamentos duplicados por nombre exacto
-- ==========================================================================

SELECT
  nombre,
  COUNT(*) AS total
FROM departamentos
GROUP BY nombre
HAVING COUNT(*) > 1;


-- ==========================================================================
-- 3. Departamentos duplicados por nombre normalizado básico
-- ==========================================================================

SELECT
  LOWER(TRIM(nombre)) AS nombre_normalizado,
  COUNT(*) AS total
FROM departamentos
GROUP BY LOWER(TRIM(nombre))
HAVING COUNT(*) > 1;


-- ==========================================================================
-- 4. Inventario por sucursal duplicado
-- ==========================================================================

SELECT
  inventario_id,
  sucursal_id,
  COUNT(*) AS total
FROM inventario_sucursal
GROUP BY inventario_id, sucursal_id
HAVING COUNT(*) > 1;


-- ==========================================================================
-- 5. Inventario por sucursal con inventario inexistente
-- ==========================================================================

SELECT
  ins.id,
  ins.inventario_id,
  ins.sucursal_id
FROM inventario_sucursal ins
LEFT JOIN inventario_general ig ON ig.id = ins.inventario_id
WHERE ig.id IS NULL;


-- ==========================================================================
-- 6. Inventario por sucursal con sucursal inexistente
-- ==========================================================================

SELECT
  ins.id,
  ins.inventario_id,
  ins.sucursal_id
FROM inventario_sucursal ins
LEFT JOIN sucursales s ON s.sucursal_id = ins.sucursal_id
WHERE s.sucursal_id IS NULL;


-- ==========================================================================
-- 7. PM bitácoras con sucursal inexistente
-- ==========================================================================

SELECT
  p.id,
  p.inventario_id,
  p.sucursal_id,
  p.fecha,
  p.resultado,
  p.tipo_mantenimiento
FROM pm_bitacoras p
LEFT JOIN sucursales s ON s.sucursal_id = p.sucursal_id
WHERE s.sucursal_id IS NULL;


-- ==========================================================================
-- 8. PM bitácoras con inventario inexistente
-- ==========================================================================

SELECT
  p.id,
  p.inventario_id,
  p.sucursal_id,
  p.fecha,
  p.resultado,
  p.tipo_mantenimiento
FROM pm_bitacoras p
LEFT JOIN inventario_general ig ON ig.id = p.inventario_id
WHERE ig.id IS NULL;


-- ==========================================================================
-- 9. PM bitácoras donde inventario no pertenece a la sucursal
-- ==========================================================================

SELECT
  p.id,
  p.inventario_id,
  p.sucursal_id,
  p.fecha,
  p.resultado,
  p.tipo_mantenimiento
FROM pm_bitacoras p
LEFT JOIN inventario_sucursal ins
  ON ins.inventario_id = p.inventario_id
 AND ins.sucursal_id = p.sucursal_id
WHERE ins.id IS NULL;


-- ==========================================================================
-- 10. PM bitácoras con resultado inválido
-- ==========================================================================

SELECT
  id,
  resultado
FROM pm_bitacoras
WHERE resultado NOT IN ('OK', 'FALLA', 'OBS');


-- ==========================================================================
-- 11. PM bitácoras con tipo de mantenimiento inválido
-- ==========================================================================

SELECT
  id,
  tipo_mantenimiento
FROM pm_bitacoras
WHERE tipo_mantenimiento NOT IN ('PREVENTIVO', 'CORRECTIVO', 'ESTETICO', 'MEJORA');


-- ==========================================================================
-- 12. PM preventivo duplicado por activo/sucursal/fecha
-- ==========================================================================

SELECT
  inventario_id,
  sucursal_id,
  fecha,
  tipo_mantenimiento,
  COUNT(*) AS total
FROM pm_bitacoras
WHERE tipo_mantenimiento = 'PREVENTIVO'
GROUP BY inventario_id, sucursal_id, fecha, tipo_mantenimiento
HAVING COUNT(*) > 1;


-- ==========================================================================
-- 13. PM validaciones con bitácora inexistente
-- ==========================================================================

SELECT
  v.id,
  v.bitacora_pm_id,
  v.decision,
  v.validado_por_user_id
FROM pm_validaciones v
LEFT JOIN pm_bitacoras p ON p.id = v.bitacora_pm_id
WHERE p.id IS NULL;


-- ==========================================================================
-- 14. PM validaciones con usuario validador inexistente
-- ==========================================================================

SELECT
  v.id,
  v.bitacora_pm_id,
  v.decision,
  v.validado_por_user_id
FROM pm_validaciones v
LEFT JOIN users u ON u.id = v.validado_por_user_id
WHERE u.id IS NULL;


-- ==========================================================================
-- 15. PM validaciones rechazadas sin motivo
-- ==========================================================================

SELECT
  id,
  bitacora_pm_id,
  decision,
  motivo
FROM pm_validaciones
WHERE decision = 'RECHAZADO'
  AND (motivo IS NULL OR TRIM(motivo) = '');


-- ==========================================================================
-- 16. PM autovalidaciones
-- ==========================================================================

SELECT
  v.id AS validacion_id,
  v.bitacora_pm_id,
  p.created_by_user_id,
  v.validado_por_user_id,
  v.decision
FROM pm_validaciones v
JOIN pm_bitacoras p ON p.id = v.bitacora_pm_id
WHERE p.created_by_user_id = v.validado_por_user_id;


-- ==========================================================================
-- 17. PM configuraciones con inventario inexistente
-- ==========================================================================

SELECT
  c.id,
  c.inventario_id,
  c.sucursal_id
FROM pm_preventivo_config c
LEFT JOIN inventario_general ig ON ig.id = c.inventario_id
WHERE ig.id IS NULL;


-- ==========================================================================
-- 18. PM configuraciones con sucursal inexistente
-- ==========================================================================

SELECT
  c.id,
  c.inventario_id,
  c.sucursal_id
FROM pm_preventivo_config c
LEFT JOIN sucursales s ON s.sucursal_id = c.sucursal_id
WHERE s.sucursal_id IS NULL;


-- ==========================================================================
-- 19. PM configuraciones donde inventario no pertenece a la sucursal
-- ==========================================================================

SELECT
  c.id,
  c.inventario_id,
  c.sucursal_id
FROM pm_preventivo_config c
LEFT JOIN inventario_sucursal ins
  ON ins.inventario_id = c.inventario_id
 AND ins.sucursal_id = c.sucursal_id
WHERE ins.id IS NULL;


-- ==========================================================================
-- 20. PM configuraciones duplicadas
-- ==========================================================================

SELECT
  inventario_id,
  sucursal_id,
  COUNT(*) AS total
FROM pm_preventivo_config
GROUP BY inventario_id, sucursal_id
HAVING COUNT(*) > 1;