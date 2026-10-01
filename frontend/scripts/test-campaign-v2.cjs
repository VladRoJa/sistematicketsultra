const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const sourceDir = path.join(root, 'src/app/marketing-campaign-v2');
const outputDir = path.join(root, 'out-tsc/campaign-v2-tests');
fs.mkdirSync(outputDir, { recursive: true });

const compilerOptions = {
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.ES2022,
  esModuleInterop: true,
};

const sourceNames = [
  'marketing-campaign-v2.models',
  'marketing-campaign-v2.logic',
  'marketing-campaign-v2-menu',
  'marketing-campaign-v2.logic.node-test',
];

for (const name of sourceNames) {
  let source = fs.readFileSync(path.join(sourceDir, `${name}.ts`), 'utf8');
  source = source.replace(
    /from '(\.\/[^']+)'/g,
    (_match, localPath) => `from '${localPath}.mjs'`,
  );
  fs.writeFileSync(
    path.join(outputDir, `${name}.mjs`),
    ts.transpileModule(source, { compilerOptions }).outputText,
  );
}

const testFile = path.join(outputDir, 'marketing-campaign-v2.logic.node-test.mjs');
const result = spawnSync(process.execPath, ['--test', testFile], {
  cwd: root,
  stdio: 'inherit',
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
