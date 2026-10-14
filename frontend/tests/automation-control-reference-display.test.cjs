const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const file = path.resolve(__dirname, '../src/app/automation-control/automation-control-timeline-display.ts');
const source = fs.readFileSync(file, 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const loaded = { exports: {} };
new Function('module', 'exports', js)(loaded, loaded.exports);
const { classifyReferenceHour, currentTijuanaClock, classifyObservationRuns } = loaded.exports;

const clock = { date: '2026-10-13', time: '11:13' };
assert.equal(classifyReferenceHour('2026-10-13', '12:00', ['12:20'], clock), 'FUTURE_REFERENCE');
assert.equal(classifyReferenceHour('2026-10-13', '08:00', ['08:20'], clock), 'PAST_REFERENCE_UNVERIFIED');
assert.equal(classifyReferenceHour('2026-10-13', '08:00', [], clock), 'NO_OBSERVATION');
assert.equal(classifyReferenceHour('2026-10-12', '12:00', ['12:20'], clock), 'PAST_REFERENCE_UNVERIFIED');
assert.equal(classifyReferenceHour('2026-10-14', '08:00', ['08:20'], clock), 'FUTURE_REFERENCE');
assert.equal(classifyReferenceHour('2026-10-13', '11:00', ['11:45'], clock), 'FUTURE_REFERENCE');
assert.equal(classifyReferenceHour('2026-10-13', '11:00', ['11:10', '11:45'], clock), 'PAST_REFERENCE_UNVERIFIED');
assert.equal(currentTijuanaClock(new Date('2026-10-13T18:13:00Z')).date, '2026-10-13');
assert.equal(currentTijuanaClock(new Date('2026-10-13T18:13:00Z')).time, '11:13');
assert.equal(classifyObservationRuns([{status_raw:'RUNNING'}]), 'running');
assert.equal(classifyObservationRuns([{status_raw:'PARTIAL'}]), 'partial');
assert.equal(classifyObservationRuns([{status_raw:'FAILED'}]), 'error');
assert.equal(classifyObservationRuns([{status_raw:'TIMED_OUT'}]), 'error');
assert.equal(classifyObservationRuns([{status_raw:'replaced'}]), 'replaced');
assert.equal(classifyObservationRuns([{status_raw:'COMPLETED'}, {status_raw:'FAILED'}]), 'completed');
assert.equal(classifyObservationRuns([{status_raw:'ERROR'}, {status_raw:'SUCCESS'}]), 'error');
assert.equal(classifyObservationRuns([{status_raw:'  success  '}]), 'completed');
assert.equal(classifyObservationRuns([{status_raw:'QUEUED'}]), 'unknown');
assert.equal(classifyObservationRuns([]), 'unknown');
assert.equal(classifyObservationRuns([{status_raw:'SUCCEEDED'}]), 'completed');
assert.equal(classifyObservationRuns([{status_raw:'FAILED'}, {status_raw:'COMPLETED'}]), 'error');
console.log('Automation reference and observation display: 20 assertions PASS');

// M1-UX: the two dataset cards must use the existing, authorized freshness
// responses. Do not spin up duplicate requests or synthesize a green SLA.
const automationTs = fs.readFileSync(path.resolve(__dirname,
  '../src/app/automation-control/automation-control.component.ts'), 'utf8');
const automationHtml = fs.readFileSync(path.resolve(__dirname,
  '../src/app/automation-control/automation-control.component.html'), 'utf8');
const indicatorTs = fs.readFileSync(path.resolve(__dirname,
  '../src/app/shared/data-freshness-indicator/data-freshness-indicator.component.ts'), 'utf8');

// Latest scheduler outcome uses actual attributed runs, not data freshness.
assert.match(automationTs, /this\.api\.runs\(job\.key,0,1\)/);
assert.match(automationTs, /mergeMap\(job=>/);
assert.match(automationTs, /latestRunStatus\(job:Job\)/);
assert.match(automationTs, /latestRunIsFailure\(job:Job\)/);
assert.match(automationHtml, /Última ejecución/);
assert.match(automationHtml, /\(click\)="openLatestFailure\(job\)"/);
assert.match(automationHtml, /latestRunStatus\(job\)/);
assert.match(automationTs, /DataFreshnessIndicatorComponent/);
assert.match(automationTs, /isFreshnessDataset\(key:string\)/);
assert.match(automationHtml, /<app-data-freshness-indicator/);
assert.match(automationHtml, /\[suppliedState\]="datasetEvidence\[dataset\.key\] \?\? null"/);
assert.match(automationHtml, /\[statusOnly\]="true"/);
assert.doesNotMatch(automationHtml, /Frescura sin SLA certificado/);
assert.match(indicatorTs, /if \(this\.suppliedState !== undefined\)/);
assert.match(indicatorTs, /this\.state = this\.suppliedState/);
assert.match(indicatorTs, /this\.state \? 'Sin certificar' : 'Sin verificar'/);
assert.match(automationTs, /funnel:this\.freshnessApi\.get\('marketing\.sales_funnel','GLOBAL'\)/);
assert.match(automationTs, /track:this\.freshnessApi\.get\('track\.daily','GLOBAL'\)/);
console.log('Automation dataset SLA cards: 11 assertions PASS');
