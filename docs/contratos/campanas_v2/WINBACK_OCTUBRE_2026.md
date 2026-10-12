# Winback octubre 2026 ? cohortes y gate de env?o

Fuente: EXPIRED_MEMBERS. Periodo inclusivo 2020-01-01 a 2026-09-30.

## Cohortes: cuatro campa?as, tres plantillas

1. BCN: adeudo >= 3000, excluyendo Villalta, Metepec, Insurgentes y Serran?a. Plan Fidelidad 699 pesos/mes, compromiso de seis meses, vigencia hasta 2026-10-31.
2. General: adeudo_min = 0 y adeudo_max = 0.
3. Atenci?n personalizada: adeudo_min = 0.01 y adeudo_max = 2999.99, todas las sucursales.
4. Atenci?n personalizada: adeudo_min = 3000, solo las cuatro sucursales excluidas de BCN.

Las sucursales se seleccionan desde el cat?logo Track autorizado; revisar sus etiquetas can?nicas. Los saldos desconocidos no equivalen a cero. Una sucursal sin identidad un?voca no es elegible en una audiencia filtrada.

## Gate antes de env?o

- Confirmar en iVentas que las tres plantillas est?n aprobadas; variable de sucursal correctamente mapeada.
- Revisar fecha de corte can?nico de la cartera y el estado actual de cada exsocio, adem?s de blacklist, tel?fonos inv?lidos, familias sin clasificaci?n y deduplicaci?n intra-campa?a.
- Revisar previews por separado y que BCN excluya las cuatro sucursales. Congelar usando fingerprint, exportar Excel de cada campa?a por sucursal/segmento.
- BLOQUEO antes de submit: comparar por tel?fono normalizado los cuatro paquetes exportados y resolver cualquier cruce. La deduplicaci?n actual es intra-campa?a, no global entre campa?as. Si hay cruces, no enviar.
- Verificar consentimiento comercial vigente y mecanismos de baja; probar con n?meros internos, variables, tarifas, preflight y restricciones de cada canal.
- No ejecutar env?os, migraciones ni despliegues hasta autorizaci?n del propietario.

## Pruebas

Backend: test_marketing_campaign_v2_audience_service.py, test_marketing_campaign_v2_routes.py, test_marketing_campaign_v2_creation_service.py.
Frontend: tsc -p tsconfig.app.json --noEmit y ng build.

Filtros de adeudo y selecci?n de sucursales forman parte del preview y del freeze; no alteran DB y no requieren migraci?n Alembic.
