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
for (const name of ['marketing-reactivation.component.node-test', 'marketing-reactivation.component', 'marketing-reactivation.service']) {
  let source = fs.readFileSync(path.join(sourceDir, `${name}.ts`), 'utf8');
  source = source.replace(/from '\.\/(marketing-reactivation\.(?:component|service))'/g, "from './$1.mjs'");
  source = source.replace("from 'src/environments/environment'", "from './environment.mjs'");
  fs.writeFileSync(path.join(outputDir, `${name}.mjs`), ts.transpileModule(source, { compilerOptions }).outputText);
}
const environment = fs.readFileSync(path.join(root, 'src/environments/environment.ts'), 'utf8');
fs.writeFileSync(path.join(outputDir, 'environment.mjs'), ts.transpileModule(environment, { compilerOptions }).outputText);
const result = spawnSync(process.execPath, ['--test', path.join(outputDir, 'marketing-reactivation.component.node-test.mjs')], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
