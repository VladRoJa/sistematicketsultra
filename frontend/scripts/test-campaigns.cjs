// Compile only these local test inputs; run against the installed Angular packages.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const sourceDir = path.join(root, 'src/app/marketing-reactivation');
const outputDir = path.join(root, 'out-tsc/campaign-tests');
fs.mkdirSync(outputDir, { recursive: true });
const compilerOptions = {
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.ES2022,
  experimentalDecorators: true,
};

const sourceNames = [
  'marketing-reactivation.component.node-test',
  'marketing-reactivation-explorer-result.node-test',
  'marketing-audience-explorer-dialog.component.node-test',
  'marketing-reactivation.component',
  'marketing-audience-explorer-dialog.component',
  'marketing-reactivation.service',
  'marketing-reactivation.models',
  'marketing-audience-explorer.models',
  'marketing-campaign-source-status.models',
];

for (const name of sourceNames) {
  let source = fs.readFileSync(path.join(sourceDir, `${name}.ts`), 'utf8');
  source = source.replace(
    /from '(\.\/[^']+)'/g,
    (_match, localPath) => `from '${localPath}.mjs'`,
  );
  source = source.replace(
    "from 'src/environments/environment'",
    "from './environment.mjs'",
  );
  fs.writeFileSync(
    path.join(outputDir, `${name}.mjs`),
    ts.transpileModule(source, { compilerOptions }).outputText,
  );
}

const environment = fs.readFileSync(
  path.join(root, 'src/environments/environment.ts'),
  'utf8',
);
fs.writeFileSync(
  path.join(outputDir, 'environment.mjs'),
  ts.transpileModule(environment, { compilerOptions }).outputText,
);

const tests = [
  'marketing-reactivation.component.node-test.mjs',
  'marketing-reactivation-explorer-result.node-test.mjs',
  'marketing-audience-explorer-dialog.component.node-test.mjs',
].map(name => path.join(outputDir, name));
const result = spawnSync(process.execPath, ['--test', ...tests], {
  stdio: 'inherit',
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
