'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../src/app/marketing-campaign-v2');
const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-campaign-detail-dialog.component.html'), 'utf8');
const ts = fs.readFileSync(path.join(root, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'), 'utf8');
const css = fs.readFileSync(path.join(root, 'marketing-campaign-v2-campaign-detail-dialog.component.css'), 'utf8');

function tab(label) {
  const esc = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const found = html.match(new RegExp('<mat-tab label="' + esc + '">([\\s\\S]*?)<\\/mat-tab>'));
  assert.ok(found, 'Pestaña ausente: ' + label);
  return found[1];
}

test('las cinco tareas quedan divididas en pestañas en orden lógico', () => {
  assert.match(ts, /MatTabsModule/);
  assert.match(html, /<mat-tab-group[^>]+campaign-detail-tabs/);
  const labels = [...html.matchAll(/<mat-tab label="([^"]+)">/g)].map(match => match[1]);
  assert.deepEqual(labels, ['Resultados', 'Destinatarios', 'Preparar envío', 'Seguimiento', 'Información']);
  assert.match(tab('Resultados'), /recipient-overview/);
  assert.match(tab('Resultados'), /reporting-section/);
  assert.match(tab('Resultados'), /provider-submit-state/);
  assert.match(tab('Destinatarios'), /recipient-filter-toolbar/);
  assert.match(tab('Destinatarios'), /exportDeliveryPackage\(\)/);
  assert.match(tab('Preparar envío'), /dispatch-preflight-section/);
  assert.match(tab('Preparar envío'), /confirmAndSubmitDispatch\(\)/);
  assert.match(tab('Seguimiento'), /followup-preview-section/);
  assert.match(tab('Seguimiento'), /freezeFollowup\(\)/);
  assert.match(tab('Información'), /definition-grid/);
});

test('mantiene todas las acciones existentes exactamente una vez', () => {
  const actions = [
    'close()', 'openGovernedConsole()', 'savePurpose()', 'loadReporting()',
    'exportReporting()', 'loadCommercialAttribution()', 'exportDeliveryPackage()',
    'exportSendablePackage()', 'openPreparationCenter()', 'reviewDispatch()',
    'confirmAndSubmitDispatch()', 'loadDispatchState()', 'reviewFailedRecovery()',
    'createFailedRecovery()', 'previewFollowup()', 'freezeFollowup()',
    'previousRecipientsPage()', 'nextRecipientsPage()', 'openRecipient(recipient)',
  ];
  for (const action of actions) {
    const count = html.split('(click)="' + action + '"').length - 1;
    assert.equal(count, 1, action + ' debe conservar un solo botón');
  }
  assert.match(html, /\[disabled\]="!canSubmitDispatch"/);
  assert.match(html, /\[disabled\]="followupFreezing \|\| !followupFreezeConfirmed/);
  assert.match(html, /\*ngIf="data.canManageDispatchConfig"/);
});

test('los botones tienen jerarquía visible para acciones de riesgo diferente', () => {
  assert.match(css, /button\.campaign-detail-btn--primary/);
  assert.match(css, /button\.campaign-detail-btn--secondary/);
  assert.match(css, /button\.campaign-detail-btn--danger/);
  assert.match(css, /button\.campaign-detail-btn:focus-visible/);
  const sendButton = html.match(/<button\b[^>]*\(click\)="confirmAndSubmitDispatch\(\)"[^>]*>/);
  assert.ok(sendButton);
  assert.match(sendButton[0], /campaign-detail-btn--danger/);
  assert.match(tab('Preparar envío'), /campaign-detail-btn--primary/);
  assert.match(tab('Seguimiento'), /campaign-detail-btn--primary/);
});

test('la falta de snapshot se explica, sin convertir ausencia de datos en cero', () => {
  assert.match(tab('Resultados'), /Aún no hay una captura de estadísticas/);
  assert.match(tab('Resultados'), /\*ngIf="report\.observation\.snapshot_id !== null"/);
  assert.match(tab('Resultados'), /counts\?\.SENT/);
  assert.match(tab('Resultados'), /counts\?\.DELIVERED/);
  assert.match(tab('Resultados'), /counts\?\.VIEWED/);
  assert.match(tab('Resultados'), /último corte disponible por lote/);
});

test('tablas de detalle se despliegan solamente cuando se requieren', () => {
  assert.ok((html.match(/<details\b/g) || []).length >= 4);
  assert.equal((html.match(/<details\b/g) || []).length, (html.match(/<\/details>/g) || []).length);
  assert.match(tab('Resultados'), /Ver datos técnicos del proveedor y evolución histórica/);
  assert.match(tab('Preparar envío'), /Ver límites y capacidad por sucursal/);
  assert.match(tab('Preparar envío'), /Ver .* lotes y canales del proveedor/);
});
