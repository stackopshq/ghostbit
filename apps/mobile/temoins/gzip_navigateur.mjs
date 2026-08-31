/**
 * Produit, avec le vrai `static/e2e.js`, un gzip tel que le navigateur en fabrique.
 *
 * Appelé **pendant** `flutter test` plutôt que figé dans un fichier de vecteurs : un
 * vecteur recopié un jour ne dit plus rien du code d'aujourd'hui, et c'est exactement le
 * mode de défaillance qu'on cherche à éviter — l'artefact qui a divergé de son générateur.
 *
 *   node temoins/gzip_navigateur.mjs <texte>   → le gzip, en base64, sur la sortie standard
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const ICI = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(ICI, '..', '..', '..', 'static', 'e2e.js'), 'utf8');

const contexte = vm.createContext({
  crypto: globalThis.crypto,
  btoa,
  atob,
  TextEncoder,
  TextDecoder,
  Blob,
  Response,
  CompressionStream,
  DecompressionStream,
  console,
  window: {},
});
const E2E = vm.runInContext(`${source}\n;E2E;`, contexte);

const texte = process.argv[2];
if (texte === undefined) {
  console.error('usage : node temoins/gzip_navigateur.mjs <texte>');
  process.exit(2);
}

// `gzipString` passe par `CompressionStream('gzip')`, l'API du navigateur — pas par zlib.
process.stdout.write(Buffer.from(await E2E.gzipString(texte)).toString('base64'));
