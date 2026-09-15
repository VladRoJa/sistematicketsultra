import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, '..');
const sourcePath = resolve(
  frontendRoot,
  'src/assets/templates/marketing-sales-funnel-agosto-template.b64',
);
const targetPath = resolve(
  frontendRoot,
  'src/assets/templates/marketing-sales-funnel-agosto-template.xlsx',
);

const raw = await readFile(sourcePath, 'utf8');
const encoded = raw.replace(/^\uFEFF/, '').replace(/\s+/g, '');

if (!encoded || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) {
  throw new Error('La plantilla Marketing Funnel no contiene Base64 válido.');
}

if (encoded.length % 4 !== 0) {
  throw new Error('La plantilla Marketing Funnel tiene Base64 truncado.');
}

const workbook = Buffer.from(encoded, 'base64');

if (
  workbook.length < 22
  || workbook[0] !== 0x50
  || workbook[1] !== 0x4b
  || workbook[2] !== 0x03
  || workbook[3] !== 0x04
) {
  throw new Error('La plantilla Marketing Funnel no inicia como un XLSX/ZIP válido.');
}

const eocdSignature = Buffer.from([0x50, 0x4b, 0x05, 0x06]);
const eocdOffset = workbook.lastIndexOf(eocdSignature);

if (eocdOffset < 0 || eocdOffset + 22 > workbook.length) {
  throw new Error('La plantilla Marketing Funnel está incompleta: falta el cierre ZIP.');
}

const commentLength = workbook.readUInt16LE(eocdOffset + 20);
const expectedLength = eocdOffset + 22 + commentLength;

if (expectedLength !== workbook.length) {
  throw new Error(
    `La plantilla Marketing Funnel tiene bytes inesperados o está truncada (${workbook.length} vs ${expectedLength}).`,
  );
}

await writeFile(targetPath, workbook);
console.log(
  `[marketing-funnel] plantilla XLSX preparada: ${workbook.length} bytes`,
);
