/**
 * Le témoin croisé : un paste créé par l'application s'ouvre-t-il dans le visualiseur web,
 * et réciproquement ?
 *
 * ─── Pourquoi ce fichier existe, et pourquoi il est écrit comme ça ───
 *
 * Un témoin qui vérifie qu'un côté se relit lui-même est **vert dans le monde cassé**.
 * C'est ce qui a coûté plusieurs jours : les deux côtés chiffraient correctement, chacun
 * dans son format, et toutes les suites de tests passaient. Le seul témoin qui mesure
 * quelque chose est croisé.
 *
 * Deux règles en découlent, et elles gouvernent tout ce fichier :
 *
 * 1. **Aucune réimplémentation d'aucun côté.** Le côté navigateur, c'est le vrai
 *    `static/e2e.js` du produit, chargé depuis le disque et exécuté sur le vrai
 *    `node:crypto.webcrypto`. Le côté application, c'est le vrai cœur Rust, appelé par un
 *    binaire qui passe par la même façade que Dart. Réécrire l'un des deux en JavaScript
 *    pour les comparer reviendrait à comparer deux copies, ce qui est précisément le
 *    défaut d'origine.
 *
 * 2. **Le vrai serveur est dans la boucle.** Ce n'est pas du zèle : le validateur de
 *    `POST /api/v1/pastes` décode en base64 **strict** (`validate=True`) et exige un nonce
 *    de douze octets exactement. Ces deux règles-là ne se voient d'aucun des deux côtés
 *    cryptographiques, et c'est un refus du relais — « expected 12 bytes after decode,
 *    got 24 » — qui avait rendu la création de partage impossible depuis mobile.
 *
 * ─── Le choix des cas ───
 *
 * Un témoin dont les deux branches de la mutation produisent la même sortie est vert des
 * deux côtés. La clé n'est donc pas tirée au hasard : sur 32 octets aléatoires, environ
 * une clé sur quatre ne contient ni `+` ni `/` en base64 standard, et le témoin ne verrait
 * pas la différence entre base64 et base64url trois fois sur quatre. Les cas ci-dessous
 * choisissent l'octet qui fait diverger, pas l'octet représentatif.
 *
 * Usage : node temoins/croise.mjs [http://127.0.0.1:8931]
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const ICI = dirname(fileURLToPath(import.meta.url));
const RACINE = join(ICI, '..', '..', '..'); // apps/mobile/temoins → dépôt ghostbit
const TEMOIN = join(ICI, '..', 'rust', 'target', 'debug', 'temoin');
const SERVEUR = process.argv[2] ?? 'http://127.0.0.1:8931';

// ─── Le côté navigateur : le vrai e2e.js, sur la vraie WebCrypto ──────────────

/**
 * Charge `static/e2e.js` tel qu'il est servi aux visiteurs.
 *
 * Les globales fournies sont celles d'une page : `crypto` est `node:crypto.webcrypto`,
 * c'est-à-dire la même implémentation de la Web Crypto API que celle qu'appelle un
 * navigateur, et non une bibliothèque tierce qui prétendrait s'y conformer.
 */
function chargerE2E() {
  const source = readFileSync(join(RACINE, 'static', 'e2e.js'), 'utf8');
  const contexte = vm.createContext({
    crypto: globalThis.crypto, // node:crypto.webcrypto
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
  return vm.runInContext(`${source}\n;E2E;`, contexte);
}

/**
 * Extrait de `static/paste.js` les quatre lignes qui découpent le fragment, et les exécute.
 *
 * Recopier ces lignes ici en ferait une cinquième copie du format, à côté de celles de
 * Rust, de Dart et de Swift — exactement ce que ce témoin existe pour interdire. On lit
 * donc le vrai fichier.
 *
 * Si les lignes ne s'y trouvent plus, c'est un **échec** et non un test à sauter : cela
 * veut dire que le visualiseur a changé de format et que plus rien ne le mesure.
 */
function analyseurDuVisualiseur() {
  const source = readFileSync(join(RACINE, 'static', 'paste.js'), 'utf8');
  const lignes = source
    .split('\n')
    .filter((l) => /^\s*const\s+(fragment|tildeIdx|keyPart|deleteToken)\s*=/.test(l));
  if (lignes.length !== 4) {
    throw new Error(
      `paste.js ne contient plus les 4 lignes qui découpent le fragment (${lignes.length} trouvée·s). ` +
        `Le témoin ne mesure plus le format du visualiseur : corriger le témoin, pas le contourner.`,
    );
  }
  return (hash) => {
    const contexte = vm.createContext({ window: { location: { hash } } });
    return vm.runInContext(`${lignes.join('\n')}\n;({keyPart, deleteToken});`, contexte);
  };
}

// ─── Le côté application : le vrai cœur Rust, par la façade que Dart appelle ──

function coeur(...args) {
  return execFileSync(TEMOIN, args, { encoding: 'buffer' });
}
const coeurTexte = (...args) => coeur(...args).toString('utf8').trim();
const coeurJSON = (...args) => JSON.parse(coeurTexte(...args));

// ─── Le vrai serveur ─────────────────────────────────────────────────────────

async function creerPaste(corps) {
  const r = await fetch(`${SERVEUR}/api/v1/pastes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corps),
  });
  if (!r.ok) {
    throw new Error(`le relais a refusé la création (${r.status}) : ${await r.text()}`);
  }
  return r.json();
}

const lirePaste = async (id) => {
  const r = await fetch(`${SERVEUR}/api/v1/pastes/${id}`);
  if (!r.ok) throw new Error(`lecture impossible (${r.status})`);
  return r.json();
};

// ─── Le harnais ──────────────────────────────────────────────────────────────

const cas = [];
const temoin = (nom, fn) => cas.push([nom, fn]);
const doitValoir = (obtenu, attendu, quoi) => {
  if (obtenu !== attendu) {
    throw new Error(`${quoi}\n  attendu : ${JSON.stringify(attendu)}\n  obtenu  : ${JSON.stringify(obtenu)}`);
  }
};

const E2E = chargerE2E();
const decouperCommeLeVisualiseur = analyseurDuVisualiseur();
const b64 = (u8) => Buffer.from(u8).toString('base64');

/** Une clé de 32 octets dont le base64 standard contient **`+` et `/`**, et dont le
 *  base64url diffère donc caractère par caractère. C'est le cas où la mutation
 *  « émettre du base64 standard dans le fragment » se voit ; une clé au hasard ne le
 *  montrerait qu'une fois sur quatre. */
const CLE_QUI_DIVERGE = Uint8Array.from({ length: 32 }, (_, i) => [0xfb, 0xff, 0x3e, 0x3f][i % 4]);

// ─── 1. Ce que l'application scelle, le navigateur l'ouvre ───────────────────

temoin("le visualiseur web ouvre un paste créé par l'application", async () => {
  const clair = 'export API_TOKEN=ne-doit-jamais-toucher-le-disque-du-serveur';
  const e = coeurJSON('sceller', clair);

  // Le vrai relais, avec son validateur base64 strict et son nonce de douze octets.
  const cree = await creerPaste({ content: e.chiffre, nonce: e.nonce, language: 'bash' });
  const fragment = coeurTexte('fragment', e.cle, cree.delete_token);

  // À partir d'ici, plus une ligne de notre code : le visualiseur découpe le fragment,
  // et e2e.js déchiffre ce que le serveur a rendu.
  const { keyPart } = decouperCommeLeVisualiseur(`#${fragment}`);
  const donnees = await lirePaste(cree.id);
  const cle = await E2E.importKey(keyPart);
  const lu = await E2E.decrypt(donnees.content, donnees.nonce, cle);

  doitValoir(lu, clair, "le navigateur n'a pas retrouvé le contenu du paste");
});

// ─── 2. Ce que le navigateur scelle, l'application l'ouvre ───────────────────

temoin("l'application ouvre un paste créé dans le navigateur", async () => {
  const clair = 'def bonjour():\n    print("créé sur le web, lu sur mobile")\n';
  const cle = await E2E.generateKey();
  const { ciphertext, nonce } = await E2E.encrypt(clair, cle);

  const cree = await creerPaste({ content: ciphertext, nonce, language: 'python' });
  // Le fragment tel que `index.js` le compose, à la ligne près.
  const fragment = `${await E2E.exportKey(cle)}~${cree.delete_token}`;

  const { cle: cleLue, jeton } = coeurJSON('analyser', fragment);
  const donnees = await lirePaste(cree.id);
  const lu = coeur('ouvrir', cleLue, donnees.nonce, donnees.content).toString('utf8');

  doitValoir(lu, clair, "l'application n'a pas retrouvé le contenu du paste");
  doitValoir(jeton, cree.delete_token, 'le jeton de suppression ne survit pas au fragment');
});

// ─── 3. L'encodage du fragment, sur le cas qui diverge ───────────────────────

temoin('la clé du fragment est en base64url, et le navigateur la relit', async () => {
  const clair = 'la clé de ce paste contient des caractères qui distinguent les deux base64';
  // Une clé choisie, importée dans la vraie WebCrypto : c'est bien e2e.js qui chiffre.
  const cle = await globalThis.crypto.subtle.importKey(
    'raw',
    CLE_QUI_DIVERGE,
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt'],
  );
  const exportee = await E2E.exportKey(cle);

  // La mutation qu'on veut voir échouer : émettre `+` et `/` là où le format dit `-` et `_`.
  const standard = b64(CLE_QUI_DIVERGE);
  if (standard === exportee) {
    throw new Error(
      'la clé choisie ne distingue pas base64 de base64url : le témoin ne mesurerait rien',
    );
  }
  if (!/[+/=]/.test(standard)) throw new Error('la clé choisie ne contient ni + ni / ni =');

  // Ce que notre côté écrit dans le fragment doit être *exactement* ce que le web écrit.
  const nôtre = coeurJSON('sceller', 'x');
  if (/[+/=]/.test(nôtre.cle)) {
    throw new Error(`la clé du fragment n'est pas en base64url sans remplissage : ${nôtre.cle}`);
  }

  // Et l'aller-retour complet sur cette clé-là.
  const { ciphertext, nonce } = await E2E.encrypt(clair, cle);
  const cree = await creerPaste({ content: ciphertext, nonce });
  const { cle: cleLue } = coeurJSON('analyser', `${exportee}~${cree.delete_token}`);
  const donnees = await lirePaste(cree.id);
  doitValoir(
    coeur('ouvrir', cleLue, donnees.nonce, donnees.content).toString('utf8'),
    clair,
    "une clé qui distingue les deux base64 n'a pas fait l'aller-retour",
  );
});

// ─── 4. Ce que le relais exige, et qui ne se voit d'aucun côté crypto ────────

temoin('le chiffre et le nonce partent en base64 standard, que le relais décode strictement', async () => {
  const e = coeurJSON('sceller', 'x');
  // Le validateur du serveur est `base64.b64decode(v, validate=True)` : un seul `-` ou
  // `_` le fait échouer en 422. Le fragment et le corps de la requête n'ont donc pas le
  // même encodage, dans la même URL — c'est le piège de ce format.
  for (const [nom, valeur] of [['chiffre', e.chiffre], ['nonce', e.nonce]]) {
    if (/[-_]/.test(valeur)) {
      throw new Error(`le champ ${nom} est en base64url ; le relais le refusera : ${valeur}`);
    }
  }
  doitValoir(Buffer.from(e.nonce, 'base64').length, 12, 'le nonce ne fait pas douze octets');

  // Et la preuve par le relais lui-même, plutôt que par notre lecture de son code.
  await creerPaste({ content: e.chiffre, nonce: e.nonce });
});

// ─── 5. Un paste compressé, tel que le web en produit ───────────────────────

temoin('un paste gzippé par le navigateur se déchiffre côté application', async () => {
  const clair = 'a'.repeat(4096) + '\nrépétitif, donc effectivement compressé\n';
  const cle = await E2E.generateKey();
  const gzippe = await E2E.gzipString(clair);
  const { ciphertext, nonce } = await E2E.encrypt(gzippe, cle);

  const cree = await creerPaste({ content: ciphertext, nonce, compressed: true });
  const donnees = await lirePaste(cree.id);
  if (!donnees.compressed) throw new Error("le serveur n'a pas conservé le drapeau compressed");

  // Le cœur rend des **octets**, pas une chaîne : à ce stade ce n'est pas encore du texte.
  const octets = coeur('ouvrir', await E2E.exportKey(cle), donnees.nonce, donnees.content);
  const { gunzipSync } = await import('node:zlib');
  doitValoir(gunzipSync(octets).toString('utf8'), clair, 'le gzip du navigateur ne se relit pas');
});

// ─── 6. Les refus doivent être des refus ────────────────────────────────────

temoin('une mauvaise clé échoue franchement, sans demi-succès', async () => {
  const cle = await E2E.generateKey();
  const { ciphertext, nonce } = await E2E.encrypt('secret', cle);
  const fausse = b64(Uint8Array.from({ length: 32 }, () => 0));
  let aEchoue = false;
  try {
    coeur('ouvrir', fausse, nonce, ciphertext);
  } catch {
    aEchoue = true;
  }
  if (!aEchoue) throw new Error("une clé fausse a ouvert le paste : l'étiquette GCM ne sert à rien");
});

// ─── Exécution ───────────────────────────────────────────────────────────────

let echecs = 0;
for (const [nom, fn] of cas) {
  try {
    await fn();
    console.log(`  ok   ${nom}`);
  } catch (e) {
    echecs++;
    console.log(`  ÉCHEC ${nom}\n       ${String(e.message).split('\n').join('\n       ')}`);
  }
}
console.log(`\n${cas.length - echecs}/${cas.length} témoins passent.`);
process.exit(echecs === 0 ? 0 : 1);
