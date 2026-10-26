'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..', 'src/app');
const campaignDir = path.join(root, 'marketing-campaign-v2');
const read = file => fs.readFileSync(path.join(campaignDir, file), 'utf8');
const modal = read('marketing-campaign-v2-governed-console-dialog.component.ts');
const modalHtml = read('marketing-campaign-v2-governed-console-dialog.component.html');
const dock = read('background-dispatch-dock.component.ts');
const dockHtml = read('background-dispatch-dock.component.html');
const service = read('marketing-campaign-v2.service.ts');

test('el envío manual no se confunde con registro background', () => {
  assert.match(modal, /async executePendingSequentially\(\)/);
  assert.match(modal, /startBackground\(\)/);
  assert.match(modal, /this\.api\.startBackgroundJob\(/);
  assert.match(modal, /backgroundBlocksManual/);
  assert.match(modal, /get canExecute\(\)/);
  assert.match(modal, /get canBulkSend\(\)/);
});

test('minimizar solo después de recibir trabajo confirmado', () => {
  assert.match(modal, /if \(this\.backgroundJob && !this\.busy\)/);
  assert.match(modalHtml, /\*ngIf="backgroundJob"/);
  assert.match(modalHtml, /\(click\)="minimize\(\)"/);
  assert.match(modalHtml, /\(click\)="close\(\)"/);
});

test('Escape y backdrop no destruyen el envío legacy', () => {
  const detail = read('marketing-campaign-v2-campaign-detail-dialog.component.ts');
  assert.match(detail, /openGovernedConsole\(\): void[\s\S]{0,500}disableClose: true/);
  assert.match(dock, /disableClose: true/);
});

test('el indicador global solo consulta, nunca envía ni detiene', () => {
  assert.match(dock, /listMyBackgroundJobs\(\)/);
  assert.doesNotMatch(dock, /startBackgroundJob\(|stopBackgroundJob\(|executeGovernedChild\(|IVentasBroadcastProvider/);
  assert.match(dockHtml, /Ver detalles/);
  assert.doesNotMatch(dockHtml, /contraseña|teléfono|destinatarios|operator_password/);
});

test('estado durable desde backend, sin secretos en navegador', () => {
  assert.doesNotMatch(dock, /localStorage|sessionStorage|setItem/);
  assert.match(dock, /currentIdentity\(\) !== this\.initialIdentity/);
  assert.match(dock, /this\.jobs = \[\]/);
  assert.match(dock, /\[401, 403, 404\]/);
  assert.match(dock, /this\.stale = true/);
});

test('acciones de detener requieren confirmación independiente', () => {
  assert.match(modal, /requestBackgroundStop\(\): void/);
  assert.match(modal, /confirmBackgroundStop\(\): void/);
  assert.match(modal, /stopConfirmationOpen/);
  assert.match(modalHtml, /Confirmar detención/);
  assert.doesNotMatch(modal, /close\(\): void \{[^}]*stopBackgroundJob/);
});

test('sin segundo POST automático al vencer la petición de inicio', () => {
  const body = modal.slice(modal.indexOf('  startBackground(): void {'), modal.indexOf('  requestBackgroundStop(): void {'));
  assert.match(body, /startBackgroundJob\(/);
  assert.match(body, /this\.loadBackgroundJobs\(\)/);
  assert.equal((body.match(/startBackgroundJob\(/g) || []).length, 1);
  assert.doesNotMatch(body, /retry\(|setTimeout\(|interval\(/);
});

test('contrato HTTP de cuatro rutas nuevo y monitor legado intacto', () => {
  assert.match(service, /startBackgroundJob\(/);
  assert.match(service, /getBackgroundJob\(/);
  assert.match(service, /listMyBackgroundJobs\(/);
  assert.match(service, /stopBackgroundJob\(/);
  assert.match(service, /executeGovernedChild\(/);
  assert.match(service, /getGovernedMonitor\(/);
});

test('el dock vive en el layout y es recuperable tras navegar', () => {
  const ts = fs.readFileSync(path.join(root, 'layout/layout.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'layout/layout.component.html'), 'utf8');
  assert.match(ts, /BackgroundDispatchDockComponent/);
  assert.match(html, /app-campaign-v2-background-dock/);
  assert.match(html, /router-outlet/);
  assert.match(dock, /jobId: job\.job_id/);
  assert.match(modal, /job\.job_id === this\.data\.jobId/);
});

test('progreso tipado es aceptación, no entrega', () => {
  const model = read('background-dispatch.model.ts');
  assert.match(model, /delivery_confirmed: false/);
  assert.match(model, /accepted_by_provider/);
  assert.match(model, /Math\.min\(100/);
  assert.match(dockHtml, /Aceptado no equivale a entregado/);
  assert.match(modalHtml, /No significa entregado/);
});

test('clave de idempotencia por WebCrypto, sin Math.random', () => {
  const model = read('background-dispatch.model.ts');
  assert.match(model, /crypto\.getRandomValues\(bytes\)/);
  assert.match(model, /new Uint8Array\(32\)/);
  assert.doesNotMatch(model, /Math\.random/);
});

test('las plantillas son archivos propios y no inline', () => {
  assert.match(dock, /templateUrl: '.\/background-dispatch-dock.component.html'/);
  assert.match(dock, /styleUrls: \['.\/background-dispatch-dock.component.css'\]/);
});


test('backend comunica disponibilidad de nuevo despacho sin ocultar trabajos ya registrados', () => {
  const routes = fs.readFileSync(path.resolve(__dirname,
    '../../backend/app/routes/marketing_campaign_v2_routes.py'), 'utf8');
  const mine = routes.slice(routes.indexOf('def campaign_v2_background_mine_endpoint():'),
    routes.indexOf('def campaign_v2_background_stop_endpoint('));
  const model = read('background-dispatch.model.ts');
  assert.match(mine, /"background_dispatch_available": _background_dispatch_enabled\(\)/);
  assert.match(mine, /"jobs": list_background_jobs/);
  assert.match(model, /background_dispatch_available: boolean/);
  assert.match(modal, /this\.backgroundAvailable = response\.background_dispatch_available === true/);
  assert.doesNotMatch(modal, /this\.backgroundAvailable = true;/);
});
