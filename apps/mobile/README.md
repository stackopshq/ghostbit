# GhostBit pour mobile

Un pastebin chiffré de bout en bout, sur iPhone et Android. Le contenu est chiffré sur
l'appareil, la clé vit dans le **fragment** de l'URL — que les navigateurs n'envoient
jamais — et le serveur ne manipule que du chiffré.

---

## L'architecture, et pourquoi elle est asymétrique

```
                    ghost_crypto::partage          (le cœur, dans ghostsuite/suite)
                      AES-256-GCM, nonce 12 o
                              │
              ┌───────────────┴───────────────┐
              │                               │
      flutter_rust_bridge                  UniFFI
              │                               │
        rust/src/api/coeur.rs          GhostbitCrypto.xcframework
              │                               │
         l'application                 la feuille de partage iOS
        (Flutter / Dart)                     (Swift)
```

Les deux générateurs de liaisons sont **frères** : chacun se pose directement sur
`ghost-crypto`. Empiler l'un sur l'autre aurait ajouté une frontière sans rien apporter.

**Le gros de l'application est en Flutter** — créer, historique, révocation, lecture.
**Les feuilles de partage divergent selon la plateforme**, et l'écart a un motif :

| Plateforme | Feuille de partage | Pourquoi |
|---|---|---|
| iOS | extension Swift séparée (`ios/Partage/`) | une Share Extension est un **processus séparé** au budget mémoire serré ; un moteur Flutter n'y tient pas en pratique |
| Android | l'activité Flutter elle-même | `ACTION_SEND` peut la viser directement — pas de contrainte mémoire, donc pas de raison d'écrire un second client |

**L'asymétrie est dans l'interface, jamais dans la cryptographie.** Swift appelle
`sealSend`, Dart appelle `sceller` ; les deux atteignent le même `ghost_crypto::partage`.

## La règle qui prime sur tout

**Aucune cryptographie en Dart, ni en Swift, ni en Kotlin.** Si le cœur ne sait pas faire
quelque chose, cela se signale — cela ne se réimplémente pas côté client. Deux manques sont
connus et documentés plus bas.

---

## Le format de ghostbit, qui n'est pas celui de la suite

```
https://paste.example.com/aB3kZx9m#CLE_B64URL~JETON_DE_SUPPRESSION
└──────────── envoyé au serveur ──┘└─────── jamais envoyé ────────┘
```

Deux encodages coexistent **dans la même URL**, et les confondre est le piège :

| Champ | Encodage | Pourquoi |
|---|---|---|
| `content`, `nonce` (corps de la requête) | base64 **standard** | le validateur du serveur décode strictement (`b64decode(…, validate=True)`) et répond 422 sur un `-` ou un `_` |
| la clé (fragment) | base64**url** sans remplissage | c'est ce que produit `exportKey` + `_b64url` dans `static/e2e.js` |

Le fragment est composé et analysé **une seule fois**, dans `rust/src/api/coeur.rs`. Les
clients transportent la chaîne, ils ne la fabriquent pas — un format recopié de chaque côté
d'une frontière diverge sans que rien ne le signale.

---

## Les témoins

**Un témoin qui vérifie qu'un côté se relit lui-même est vert dans le monde cassé.** Les
témoins ci-dessous sont donc croisés, et ils passent par la vraie API du navigateur.

```bash
# 1. Le témoin qui compte : le vrai static/e2e.js sur node:crypto.webcrypto,
#    contre le vrai serveur. Nécessite une instance locale.
STORAGE_BACKEND=sqlite RATE_LIMIT_CREATE=10000/minute RATE_LIMIT_VIEW=10000/minute \
  python -m uvicorn app.main:app --port 8931 &
cargo build --manifest-path rust/Cargo.toml --bin temoin
node temoins/croise.mjs

# 2. La barrière rapide, sans réseau : le croisement contre `aes-gcm` pris directement.
cargo test --manifest-path rust/Cargo.toml

# 3. Les témoins Dart, dont le gzip croisé — il appelle Node pendant le test.
flutter test

# 4. Le format de fragment côté Swift, sans Xcode ni simulateur.
outils/temoin-swift.sh

# 5. Le pont de trousseau entre l'extension et l'application.
outils/verifier-pont-trousseau.sh
```

### Ce que chaque témoin mesure, et ce qu'il ne mesure pas

`temoins/croise.mjs` est le seul à voir **tout** le chemin : il charge `static/e2e.js`
depuis le disque, l'exécute sur `node:crypto.webcrypto`, extrait de `static/paste.js` les
quatre lignes qui découpent le fragment et les exécute, et fait passer chaque paste par le
vrai relais. Rien n'y est réimplémenté.

Les autres sont plus étroits par construction. `cargo test` ne voit ni le validateur base64
du serveur ni le découpage du fragment par `paste.js` ; `outils/temoin-swift.sh` ne voit que
l'encodage.

### Le cas est choisi, pas représentatif

Sur 32 octets tirés au hasard, environ **une clé sur quatre** ne contient ni `+` ni `/` en
base64 standard : un témoin qui prendrait une clé aléatoire serait vert trois fois sur
quatre dans un monde où l'encodage du fragment est faux. Les témoins emploient donc une clé
choisie pour contenir les deux, plus un `=` de remplissage.

Le point a été **mesuré** : en remplaçant `URL_SAFE_NO_PAD` par `STANDARD` dans `sceller`,
les deux aller-retours du témoin croisé restent **verts** — les deux décodeurs, le nôtre et
celui d'`e2e.js`, sont tolérants. Seule l'assertion explicite sur la forme voit la
différence. C'est le corollaire du jour appliqué : choisir le cas où les branches divergent.

---

## Ce que le cœur ne sait pas encore faire

Deux fonctions manquent à `ghost_crypto`, et elles ne sont **pas** écrites côté client.

### 1. Les pastes protégés par mot de passe

Ghostbit dérive la clé d'un mot de passe par **PBKDF2-SHA256, 600 000 itérations**, ou par
**Argon2id à `m=19456, t=2, p=1`**, avec un sel aléatoire de 16 octets porté par le paste.

- PBKDF2 **n'existe nulle part** dans `ghost-crypto` ;
- le seul Argon2id du cœur (`kdf::derive_master_key`) tire son sel de l'e-mail de façon
  déterministe, et son garde-fou `ensure_strong()` **refuserait** les paramètres de
  ghostbit — 19 456 Kio est sous le plancher de 65 536, et 2 passes sous celui de 3. Ces
  planchers sont justes pour un mot de passe maître de coffre ; ils ne s'appliquent pas à
  un paste éphémère, et les abaisser pour ghostbit affaiblirait ghostpass.

L'application **détecte** `has_password` et le dit clairement, plutôt que d'échouer en
prétendant que la clé est mauvaise. Il faudrait au cœur un module
`partage::kdf::{pbkdf2_sha256, argon2id}` prenant ses paramètres à l'appel.

### 2. L'édition d'un paste par son propriétaire

`PUT /api/v1/pastes/{id}` demande de rechiffrer sous une clé **déjà connue** — celle du
fragment, qui ne peut pas changer sans casser les liens déjà partagés. `partage::sceller`
ne sait sceller que sous une clé qu'il tire lui-même. Il manque un
`partage::sceller_avec(cle, clair)`. L'édition est donc absente, et son absence est un choix.

### 3. Une façade `ghostbit` au binding UniFFI

`sealSend` rend la clé en base64 **standard** ; le fragment de ghostbit la veut en
base64url sans remplissage. La conversion est donc dans `ios/Partage/Fragment.swift` —
isolée dans un seul fichier et éprouvée par `outils/temoin-swift.sh`, mais c'est une
seconde description du format, à côté de celle du cœur. Une façade `ghostbit` dans
`ghost-crypto-ffi` qui rendrait le fragment déjà composé la ferait disparaître.

---

## Ce qui reste à faire

**La cible Xcode de l'extension de partage n'est pas câblée.** Les sources
(`ios/Partage/`), l'`Info.plist`, les droits et l'XCFramework existent et sont éprouvés,
mais aucune cible `Partage` n'a été ajoutée à `Runner.xcodeproj`. C'est une manipulation
qui se fait dans Xcode et que je n'ai pas pu vérifier ici ; la décrire comme faite aurait
été pire que de la laisser nommée.

À faire dans Xcode : nouvelle cible *Share Extension* nommée `Partage`, y ajouter les
quatre fichiers Swift, remplacer son `Info.plist` par celui fourni, lui attacher
`Partage.entitlements`, lier `GhostbitCrypto.xcframework`, et cocher le groupe
`group.dev.ghostbit` sur les deux cibles.

---

## Construire

```bash
flutter pub get
outils/construire-xcframework.sh        # iOS seulement, macOS + Xcode requis
outils/engendrer_langages.py            # après un changement de app/languages.json
flutter run
```

L'XCFramework ne sert **pas** à l'application, qui passe par `flutter_rust_bridge` : il
sert à la feuille de partage iOS.

## Les icônes

Rendues par les outils de la charte, jamais par un `rsvg-convert` naïf :

```bash
cd ../../../suite
python3 tools/brand/icone-ios.py assets/ghostbit/logo.svg \
  ../ghostbit/apps/mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/
python3 tools/brand/icone-adaptative-android.py assets/ghostbit/logo.svg \
  ../ghostbit/apps/mobile/android/app/src/main/res/
```

**Aucun `--fond` n'est passé, et c'est délibéré** : le défaut de l'outil *est* la décision.
Il valait `#0B0F17` jusqu'au 2026-08-31 en fin de journée, où il est passé à `#FFFFFF` pour
que l'icône Android se lise comme la sœur de l'icône iOS, que `icone-ios.py` aplatit sur
blanc. Passer une couleur ici — même celle du `--color-base` de la charte, qui paraît le
choix évident — écrase silencieusement ce genre de décision. C'est arrivé pendant ce
portage, et seul un `git status` sur le dépôt de la suite l'a rattrapé.

Les SVG de charte sont cadrés pour un **favicon** : la silhouette touche les bords. Les
outils mesurent la silhouette rendue puis recadrent — 80 % de la hauteur sur iOS, 80 % de
la **zone sûre de 72 dp** sur Android, soit 53 % de la toile de 108 dp. Appliquer 80 % à la
toile entière ferait rogner la silhouette chez certains utilisateurs seulement, selon leur
lanceur.

## L'apparence

`suite/docs/charte-mobile.md`. L'écran d'entrée se copie structure par structure :
enseigne sur plaque avec son halo, nom, sous-titre, carte de verre bornée à 420.

Deux points relevés en portant l'écran, et qui n'étaient pas dans la charte :

- **le rayon des champs est 8** (`--radius-sm`), pas 12. Le portage Flutter de ghostcal
  emploie 12 : il n'a pas suivi la décision du 2026-08-31 ;
- **le bouton d'accent de ghostbit est un aplat plein avec halo**, alors que celui de
  ghostcal est une teinte à 14 % sans halo. Ce n'est pas un écart : `emit_theme.py` dérive
  cette forme de la luminance de l'accent, et l'encre du bouton de ghostbit est **noire**
  (`--color-accent-ink: #000000`) là où celle de ghostcal est blanche. Recopier le bouton
  d'un produit frère donnerait du texte illisible.

L'exception iOS — boutons rectangulaires plutôt qu'en pilule — s'applique aussi sur
Android, et la charte §7 le porte déjà avec son motif revérifié : le champ de recherche de
Material n'est pas une pilule non plus.

**Le flou d'arrière-plan de la carte de verre, en revanche, ne suit pas l'écart Android de
la charte §7.** Cet écart est propre à Compose, dont `Modifier.blur` floute le composant
lui-même. `BackdropFilter` de Flutter floute bien ce qui est derrière, sur les deux
plateformes, parce que c'est le moteur de Flutter qui compose et non celui du système.
