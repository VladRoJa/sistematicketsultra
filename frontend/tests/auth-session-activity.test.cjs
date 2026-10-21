'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const { firstValueFrom, throwError, of } = require('rxjs');

function loadClass(filename, className, mocks) {
  const contents = fs.readFileSync(
    path.join(__dirname, '../src/app/', filename), 'utf8'
  );
  const compiled = ts.transpileModule(contents, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const module = { exports: {} };
  const requireFake = name => {
    if (name === '@angular/core') {
      return { Injectable: () => constructor => constructor };
    }
    if (name === '@angular/common/http') {
      return { HttpErrorResponse: FakeHttpError };
    }
    if (name === 'rxjs' || name === 'rxjs/operators') {
      return require(name);
    }
    if (name.includes('environments/environment')) {
      return { environment: { apiUrl: '/api' } };
    }
    return mocks[name] || {};
  };
  new Function('require', 'module', 'exports', compiled)(
    requireFake, module, module.exports
  );
  return { Class: module.exports[className], source: contents };
}
class FakeHttpError extends Error {
  constructor(status) {
    super('HTTP ' + status);
    this.status = status;
  }
}
function request(url, method = 'GET') {
  return {
    url, method,
    headers: {},
    clone({ setHeaders }) {
      return { ...this, headers: { ...this.headers, ...setHeaders } };
    },
  };
}

test('trusted user interaction advances 45-minute idle clock without mousemove write storm', () => {
  const oldStorage = global.localStorage;
  const oldNow = Date.now;
  let now = 10_000_000;
  const store = new Map();
  global.localStorage = {
    getItem: k => store.has(k) ? store.get(k) : null,
    setItem: (k, v) => store.set(k, v),
    removeItem: k => store.delete(k),
  };
  Date.now = () => now;
  try {
    const { Class } = loadClass(
      'core/auth/auth-activity.service.ts', 'AuthActivityService', {}
    );
    const activity = new Class();
    activity.initializeIfAbsent();
    assert.equal(activity.millisecondsUntilIdle(), 45 * 60_000);
    now += 500;
    activity.recordInteraction();
    assert.equal(Number(store.get(activity.storageKey)), 10_000_000);
    now += 2000;
    activity.recordInteraction();
    assert.equal(activity.millisecondsUntilIdle(), 45 * 60_000);
    activity.lock();
    now += 60_000;
    activity.recordInteraction();
    assert.equal(activity.isRecent(), false);
    activity.unlock();
    activity.recordInteraction();
    assert.equal(activity.isRecent(), true);
    now += 45 * 60_000 + 1;
    assert.equal(activity.millisecondsUntilIdle(), 0);
    activity.initializeIfAbsent();
    assert.equal(activity.millisecondsUntilIdle(), 0, 'reload never resets a stale clock');
    activity.clear();
    assert.equal(store.size, 0);
  } finally {
    Date.now = oldNow;
    global.localStorage = oldStorage;
  }
});

test('401 rejects session but never opens reauthentication modal', async () => {
  const { Class, source } = loadClass(
    'interceptors/auth.interceptor.ts', 'TokenInterceptor', {}
  );
  assert.doesNotMatch(source, /dialog\.open\(/);
  const calls = [];
  const session = {
    getToken: () => 'test-jwt',
    clearSession: () => calls.push('cleared'),
  };
  const activity = {
    isLocked: () => false,
    millisecondsUntilIdle: () => 1000,
    isRecent: () => true,
    clear: () => calls.push('activity-cleared'),
  };
  const router = { url: '/main/ver-tickets', navigate: () => calls.push('login') };
  const refresh = { shouldRenewSoon: () => false };
  const jwt = { isTokenExpired: () => false };
  const interceptor = new Class(session, refresh, activity, jwt, router);
  const next = { handle: () => throwError(() => new FakeHttpError(401)) };
  await assert.rejects(
    () => firstValueFrom(interceptor.intercept(request('/api/tickets/all'), next)),
    error => error.status === 401
  );
  assert.deepEqual(calls, ['cleared', 'activity-cleared', 'login']);
});

test('background 401 does not count as activity and does not open dialog', async () => {
  const { Class } = loadClass('interceptors/auth.interceptor.ts', 'TokenInterceptor', {});
  let clears = 0;
  const interceptor = new Class(
    { getToken: () => 'test-jwt', clearSession: () => clears++ },
    { shouldRenewSoon: () => false },
    { isLocked: () => false, millisecondsUntilIdle: () => 1000, isRecent: () => false },
    { isTokenExpired: () => false },
    { url: '/main', navigate: () => clears++ },
  );
  const next = { handle: () => throwError(() => new FakeHttpError(401)) };
  await assert.rejects(
    () => firstValueFrom(interceptor.intercept(request('/api/tickets/all'), next)),
    e => e.status === 401
  );
  assert.equal(clears, 0);
});

test('foreign host never receives Authorization header', async () => {
  const { Class } = loadClass('interceptors/auth.interceptor.ts', 'TokenInterceptor', {});
  const interceptor = new Class(
    { getToken: () => 'never-send-to-foreign-host' },
    { shouldRenewSoon: () => false },
    { isLocked: () => false },
    { isTokenExpired: () => false },
    { url: '/', navigate: () => {} },
  );
  const next = { handle: req => of(req.headers) };
  const headers = await firstValueFrom(
    interceptor.intercept(request('https://external.example.org/ingest'), next)
  );
  assert.equal(headers.Authorization, undefined);
});

test('login 401 remains in form without session redirect', async () => {
  const { Class } = loadClass('interceptors/auth.interceptor.ts', 'TokenInterceptor', {});
  let redirected = 0;
  const interceptor = new Class(
    { getToken: () => 'jwt', clearSession: () => redirected++ },
    { shouldRenewSoon: () => false },
    { isLocked: () => false, isRecent: () => true },
    { isTokenExpired: () => false },
    { url: '/login', navigate: () => redirected++ },
  );
  await assert.rejects(
    () => firstValueFrom(interceptor.intercept(
      request('/api/auth/login', 'POST'),
      { handle: () => throwError(() => new FakeHttpError(401)) }
    )),
    e => e.status === 401
  );
  assert.equal(redirected, 0);
});
