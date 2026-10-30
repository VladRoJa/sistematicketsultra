const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const rxjs = require('rxjs');

const provider = { rol: 'PROVEEDOR_FUNNEL_ORIGINAL', username: 'external' };
const target = '/marketing-conversion/venta-total-original';
const tokenTypes = {};
let dependencies = {};
function load(file, mocks = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../src/app', file), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, experimentalDecorators: true,
  }}).outputText;
  const module = { exports: {} };
  function fakeRequire(name) {
    if (name in mocks) return mocks[name];
    if (name === '@angular/core') return {
      Component: () => c => c, Injectable: () => c => c, ViewChild: () => () => {},
      inject: type => dependencies[type],
    };
    if (name === 'rxjs' || name === 'rxjs/operators') return require(name);
    if (name.includes('funnel-provider-access')) return policy;
    if (name.includes('environment')) return { environment: { apiUrl: '/api' } };
    return new Proxy({}, { get: (_, key) => tokenTypes[key] ||= key });
  }
  new Function('require', 'module', 'exports', compiled)(fakeRequire, module, module.exports);
  return module.exports;
}
const policy = load('core/auth/funnel-provider-access.ts');

test('all non-Original URLs redirect for provider, including direct and hydrated JWT access', () => {
  dependencies = {
    SessionService: { getUser: () => provider, getToken: () => 'jwt' },
    Router: { parseUrl: url => ({ redirect: url }) },
    JwtHelperService: { decodeToken: () => provider },
  };
  for (const url of ['/main/ver-tickets', '/inventario', '/pm/calendario', '/warehouse',
    '/warehouse/track', '/marketing-conversion/venta-total', '/marketing/campaigns', '/admin', '/test-select']) {
    assert.deepEqual(policy.funnelProviderRouteGuard({}, { url }), { redirect: target });
  }
  assert.equal(policy.funnelProviderRouteGuard({}, { url: target + '?month=2026-10' }), true);
  assert.equal(policy.funnelProviderRouteGuard({}, { url: '/login' }), true);
  dependencies.SessionService.getUser = () => null;
  assert.deepEqual(policy.funnelProviderRouteGuard({}, { url: '/admin' }), { redirect: target });
  dependencies.SessionService.getUser = () => ({ rol: 'MARKETING' });
  assert.equal(policy.funnelProviderRouteGuard({}, { url: '/main/ver-tickets' }), true);
});

test('provider layout creates only Original menu and never starts other module requests', () => {
  const { LayoutComponent } = load('layout/layout.component.ts');
  const unexpected = new Proxy({}, { get: (_, key) => () => { throw Error('Unexpected request: ' + key); } });
  const layout = new LayoutComponent({}, unexpected, {}, {}, { getUser: () => provider },
    { registrarCallback() {} }, { getUser: () => provider }, {}, {}, unexpected, unexpected, unexpected);
  layout.iniciarTimerInactividad = () => {};
  layout.ngOnInit();
  assert.deepEqual(layout.menuItems.map(item => item.path), [target]);
  assert.equal(layout.puedeVerAccionesFlotantesGlobales, false);
  assert.equal(layout.validationSummaryIntervalId, null);
  assert.equal(layout.automationAlertIntervalId, null);
});

test('provider export uses only dashboard rows, never weekly or personal-data endpoints', () => {
  let exported;
  const { MarketingSalesFunnelOriginalComponent: Component } = load(
    'marketing-sales-funnel/marketing-sales-funnel-original.component.ts', {
      './marketing-sales-funnel-table-export': { exportMarketingSalesFunnelBranchTable: args => exported = args },
    });
  const component = Object.create(Component.prototype);
  component.authService = { getUser: () => ({ ...provider, username: 'ADMICORP' }) };
  component.dashboard = { summary: { investment: 10 }, branches: [{ sucursal_id: 7, investment: 10 }] };
  component.branchRows = [{ sucursal_id: 7 }];
  component.scopeOptions = [{ sucursal_id: 7 }];
  component.regionControl = { value: null };
  component.branchControl = { value: 7 };
  component.monthControl = { value: '2026-10' };
  component.dialog = { open() { throw Error('Personal details must not open'); } };
  component.salesFunnelService = { exportWeeklyWorkbook() { throw Error('Weekly must remain ADMICORP-only'); } };
  component.exportBranchTable();
  assert.deepEqual(exported.branches.map(b => b.sucursal_id), [7]);
  assert.equal(component.canViewIndividualDetails, false);
  component.openDetail('sales_total', 7);
});

test('login navigates directly to Original without delayed ticket navigation', () => {
  const { LoginComponent } = load('pantalla-login/pantalla-login.component.ts');
  const navigations = [];
  const login = new LoginComponent({ setSession() {} }, { navigate: url => navigations.push(url) });
  login.handleLoginSuccess({ token: 'jwt', user: provider });
  assert.deepEqual(navigations, [[target]]);
});
