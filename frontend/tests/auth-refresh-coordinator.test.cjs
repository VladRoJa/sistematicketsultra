'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const source = fs.readFileSync(
  path.join(__dirname, '../src/app/core/auth/refresh-coordinator.ts'),
  'utf8'
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;

const runtime = { exports: {} };
new Function('module', 'exports', compiled)(runtime, runtime.exports);
const { RefreshCoordinator } = runtime.exports;

function lock() {
  let previous = Promise.resolve();
  return async (work) => {
    const ready = previous;
    let unlock;
    previous = new Promise(resolve => { unlock = resolve; });
    await ready;
    try {
      return await work();
    } finally {
      unlock();
    }
  };
}

test('five simultaneous calls in same tab exchange once', async () => {
  let token = 'old';
  let exchanges = 0;
  const coordinator = new RefreshCoordinator(
    () => token, () => true,
    async () => { exchanges++; await Promise.resolve(); token = 'new'; return token; },
    lock()
  );
  const result = await Promise.all(
    Array.from({ length: 5 }, () => coordinator.renew('old'))
  );
  assert.deepEqual(result, Array(5).fill('new'));
  assert.equal(exchanges, 1);
});

test('two tabs sharing Web Lock do not replay rotated cookie', async () => {
  let token = 'old';
  let exchanges = 0;
  const sharedLock = lock();
  const makeTab = () => new RefreshCoordinator(
    () => token,
    t => t === 'new',
    async () => { exchanges++; await Promise.resolve(); token = 'new'; return token; },
    sharedLock
  );

  const first = makeTab();
  const second = makeTab();
  const result = await Promise.all([first.renew('old'), second.renew('old')]);
  assert.deepEqual(result, ['new', 'new']);
  assert.equal(exchanges, 1);
});

test('absent token or logged out state cannot trigger rotation', async () => {
  let exchanges = 0;
  let current = 'old';
  const coordinator = new RefreshCoordinator(
    () => current, () => true,
    async () => { exchanges++; return 'new'; }, lock()
  );
  assert.equal(await coordinator.renew(null), null);
  current = null;
  assert.equal(await coordinator.renew('old'), null);
  assert.equal(exchanges, 0);
});

test('after rejection coordinator clears singleflight and may try again', async () => {
  let attempts = 0;
  const coordinator = new RefreshCoordinator(
    () => 'old', () => true,
    async () => {
      attempts++;
      if (attempts === 1) throw new Error('temporary server error');
      return 'new';
    }, lock()
  );
  await assert.rejects(() => coordinator.renew('old'), /temporary/);
  assert.equal(await coordinator.renew('old'), 'new');
  assert.equal(attempts, 2);
});

test('without exclusive lock implementation rotation fails closed', async () => {
  let count = 0;
  const coordinator = new RefreshCoordinator(
    () => 'old', () => true,
    async () => { count++; return 'new'; },
    async () => null
  );
  assert.equal(await coordinator.renew('old'), null);
  assert.equal(count, 0);
});
