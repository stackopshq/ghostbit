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

## La cible Xcode de l'extension, et pourquoi pas xcodegen

`outils/cabler-extension-ios.sh` ajoute la cible `Partage` à `ios/Runner.xcodeproj`. Le
script est **idempotent** : il défait puis refait, si bien qu'il vaut à la fois
installation et documentation exécutable. Une cible ajoutée à la main dans Xcode ne se
relit pas, ne se diffe pas, et ne se refait pas.

`apps/ios/` de ghostpass décrit tout son projet en `project.yml` et ne versionne pas son
`.xcodeproj` — c'est plus propre, et ce serait le bon choix pour un projet iOS natif.
**Il ne se transpose pas ici**, et la raison est mesurable : le `Runner.xcodeproj` de
Flutter porte deux phases de script (`xcode_backend.sh build` et `embed_and_thin`), une
chaîne de `xcconfig`, et il se compile depuis un `.xcworkspace` que `pod install`
entretient. Passer sous xcodegen voudrait dire redéclarer tout cela **puis** relancer
`pod install` après chaque génération : le projet généré ne serait jamais celui qu'on
compile.

La bibliothèque employée, `xcodeproj`, est celle de CocoaPods — déjà elle qui écrit dans ce
fichier à chaque `pod install`. Deux écrivains, une seule grammaire.

**Le risque qu'un outil Flutter réécrive le projet a été mesuré, pas supposé :**

| Après | Cibles présentes |
|---|---|
| câblage | `Partage, Runner, RunnerTests` |
| `pod install` | `Partage, Runner, RunnerTests` |
| `flutter clean` + `flutter pub get` | `Partage, Runner, RunnerTests` |

Et la phase « Embed App Extensions » reste **avant** « Thin Binary » — copier l'extension
après la signature la laisserait non signée dans un paquet déjà scellé.

### Ce que la compilation prouve

```
Runner.app/
├── Frameworks/rust_lib_ghostbit.framework   ← le cœur, par flutter_rust_bridge
└── PlugIns/Partage.appex                    ← le cœur, par UniFFI (139 symboles)
```

Les deux générateurs frères, au-dessus du même `ghost-crypto`, dans le même paquet.
Vérifié par `nm` sur le binaire produit, pas déduit du fichier de projet.

### Ce que la compilation ne prouve pas

Elle ne prouve pas que la feuille de partage existe pour l'utilisateur, et il a fallu
deux échecs pour l'apprendre.

**Le premier tenait à la signature.** `flutter create` avait posé
`DEVELOPMENT_TEAM = 6BBGV83S5C` — une équipe **personnelle**, qui ne peut pas
provisionner de groupe d'applications, et dont la signature réussit sans un mot. On
obtient une application qui s'installe, se lance, et dont la feuille de partage ne trouve
jamais l'adresse du serveur : `UserDefaults(suiteName:)` rend `nil`. Le symptôme est à
mille lieues de la cause. `cabler-extension-ios.rb` **impose** désormais l'équipe payante
sur les deux cibles, et `appareil-ios.sh` la réimpose en ligne de commande.

**Le second tenait à une variable non définie.** `Partage/Info.plist` porte
`$(FLUTTER_BUILD_NUMBER)`, qui vient de `Flutter/Generated.xcconfig` — et que seule la
cible Runner incluait. Non définie, elle ne laisse pas une valeur par défaut : elle
s'efface. Compilation et signature passent ; c'est l'appareil qui refuse :

    Appex bundle … does not have a CFBundleVersion key with a non-zero length string
    value in its Info.plist (MIInstallerErrorDomain error 33)

`ios/Partage/Partage.xcconfig` n'inclut que `Generated.xcconfig`, pour que la version
vienne de `pubspec.yaml` une seule fois et pour les deux cibles.

### Et ce que l'ouverture de la feuille prouve

```bash
outils/temoin-feuille-de-partage.sh      # sur un simulateur démarré
```

`TemoinPartage` ouvre la **vraie** feuille du système depuis une application d'un bouton
(`ios/HoteDePartage/`), y choisit GhostBit, et vérifie que la zone de rédaction contient
un jeton qui n'existe nulle part ailleurs sur l'appareil. La capture est jointe au
résultat d'essai.

Passer par Safari ou Notes aurait marché, au prix d'une dépendance à la disposition
interne d'applications d'Apple qui change à chaque version majeure : le témoin aurait
rougi pour des raisons étrangères à GhostBit.

Ce que l'ouvrir a révélé, et que trois relectures n'avaient pas montré : **la feuille
affichait « Ghostbit »**. Elle montre le nom de l'application contenante, jamais celui de
l'extension — le `CFBundleDisplayName` de `Partage/Info.plist` n'a aucun effet là.

Trois choses restent hors de portée d'un script, et sont nommées plutôt que contournées :

- **Le geste de l'utilisateur sur un appareil réel.** Le témoin tourne sur simulateur. Sur
  un iPhone, ouvrir la feuille demande une main, et un journal ne la remplace pas :
  `NSLog` depuis une extension iOS n'est visible ni par `devicectl --console` ni par
  `idevicesyslog`. Prévoir un affichage à l'écran, jamais un journal.
- **Le réglage de l'adresse.** L'extension lit ce que l'application a écrit dans le
  groupe ; sans une première ouverture de GhostBit, elle lève `adresseAbsente`.
- **La publication elle-même.** Le témoin s'arrête à « le texte est arrivé ». Ce qui suit
  — chiffrer, poster, rendre un lien — passe par le réseau et par une instance, et n'a pas
  encore été mesuré de bout en bout depuis la feuille.

---

## Android

`outils/verifier-rust-android.sh` compile le cœur pour les trois ABI que Flutter livre
(`arm64-v8a`, `armeabi-v7a`, `x86_64`), au niveau d'API 24 — le `minSdk` de Flutter — et
compare la **surface exportée** de chaque `.so` à celle de la bibliothèque hôte.

La comparaison remplace une liste de symboles écrite à la main, et ce n'est pas de la
coquetterie : la première version de ce contrôle cherchait `frbgen_ghostbit` et échouait
sur les trois architectures **alors que les trois bibliothèques étaient bonnes**.
`flutter_rust_bridge` 2.x n'exporte pas un symbole par fonction ; il expose un répartiteur,
`frb_pde_ffi_dispatcher_primary`, et achemine les appels par un discriminant. Le contrôle
accusait la compilation d'un défaut qui était le sien.

Ce contrôle sait rougir, et cela a été mesuré plutôt que supposé : en lui donnant une
autre bibliothèque hôte, il sort 1 et nomme la différence.

### L'APK

```bash
ANDROID_HOME=$HOME/Library/Android/sdk JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
  flutter build apk
```

**Le JDK 21, pas plus récent** : `jlink`, qu'appelle l'AGP, casse sous le JDK 26.

`flutter build apk` produit `app-release.apk`, 54,5 Mo, avec `librust_lib_ghostbit.so`
dans `arm64-v8a`, `armeabi-v7a` et `x86_64`. Il a d'abord échoué trois fois, et les trois
échecs se cachaient l'un l'autre :

1. `:app` compilait contre `android-36` quand `flutter_secure_storage` 11 exige 37. Le
   greffon Gradle de Flutter aligne les **sous-projets de greffon** sur le compileSdk de
   l'application, et non l'inverse : l'application ne monte pas toute seule.
2. `compileSdk = 37` seul échange ce message contre
   `Failed to find target with hash string 'android-37'`, qui ressemble à un SDK mal
   installé et n'en est pas un. Google ne publie plus de `platforms;android-37`, seulement
   `android-37.0` et suivantes ; `compileSdkMinor` nomme la mineure.
3. cargokit lit ce même `compileSdkVersion` et l'analyse en entier :
   `substring(8) as int` sur « android-37.0 » lève `For input string: "37.0"`.

Les trois correctifs portent leur explication à l'endroit où ils sont
(`android/app/build.gradle.kts`, `android/build.gradle.kts`,
`rust_builder/cargokit/gradle/plugin.gradle`), parce que chacun a l'air arbitraire seul.

**Ce qui n'est pas éprouvé côté Android** : rien n'a tourné sur un téléphone. Le Redmi
n'était pas branché — `adb devices` ne montrait qu'un émulateur — et un APK qui se
construit n'est pas un APK qui se lance. Le partage par `ACTION_SEND` en particulier n'a
jamais été déclenché.

## Les liens universels : ouvrir un paste dans l'application

Un lien de paste doit ouvrir **l'application quand elle est installée, et le site
sinon**. C'est la demande, et jusqu'ici elle n'était satisfaite dans aucun des deux
cas : le lien ouvrait toujours le navigateur.

Le défaut avait survécu pour une raison qui mérite d'être écrite, parce qu'elle se
reproduira ailleurs : **il ne produit rien qui ressemble à une panne**. Un lien
universel mal configuré n'échoue pas, il retombe — sur le navigateur, qui affiche le
paste correctement. Aucune erreur, aucune trace, rien à regarder. Personne ne pouvait
le voir sans aller le chercher.

### Les deux moitiés, dont aucune ne suffit

| Moitié | Où | Sans elle |
|---|---|---|
| Le **site** déclare quelles applications il autorise | `/.well-known/apple-app-site-association` et `/.well-known/assetlinks.json`, servis par `app/main.py` | le système ne trouve rien à vérifier, et ouvre le navigateur |
| L'**application** déclare quels domaines elle réclame | `ios/Runner/Runner.entitlements`, `android/app/src/main/AndroidManifest.xml` | le système ne demande rien, et ouvre le navigateur |

Les deux symptômes sont identiques, et identiques à celui d'un lien qui marche. La
seule façon de savoir où l'on en est est de le demander explicitement :

```bash
# Le fichier est-il servi, en application/json, sans redirection ?
curl -sSD- https://ghostbit.dev/.well-known/apple-app-site-association | head -20
curl -sSD- https://ghostbit.dev/.well-known/assetlinks.json | head -20

# Android : l'état réel de la vérification, hôte par hôte. `verified` ou rien.
adb shell pm get-app-links dev.ghostbit.ghostbit
```

Un **code 200 ne prouve rien** : sur certains hôtes, une page de redirection est servie
pour n'importe quel chemin. Il faut lire le corps.

### Trois pièges rencontrés, dont deux muets

1. **`/apple-app-site-association` à la racine rendait 422, pas 404.** Cela ressemble à
   une route d'API qui intercepte ; ce n'en est pas une. Le chemin tombait sur
   l'attrape-tout `/{paste_id}`, dont le motif `^[A-Za-z0-9_-]{1,20}$` refuse les 26
   caractères du nom. Le serveur sert désormais le document aux deux emplacements.

2. **Sous `UIScene`, `application(_:continueUserActivity:…)` n'est jamais appelé.**
   C'est pourtant ce que montre presque toute la documentation. L'activité va à la
   scène, et à elle seule — d'où `SceneDelegate.swift`. Avec le délégué d'application,
   tout est correct et le lien ouvre l'application… sur son écran d'accueil.

3. **Le routage de liens profonds de Flutter est actif par défaut depuis 3.24**, et
   pousse le lien comme route initiale. Ce `MaterialApp` a un `home:` et pas de table
   de routes : la route ne correspond à rien, et l'application s'ouvre sans le paste.
   Il est coupé des deux côtés (`FlutterDeepLinkingEnabled`, `flutter_deeplinking_enabled`)
   et les liens passent par le canal `dev.ghostbit/partage`, celui que le partage
   emprunte déjà.

### L'empreinte de signature, qui n'est pas dans ce dépôt

`assetlinks.json` a besoin du SHA-256 du certificat qui signe l'APK. **Il n'y a pas de
valeur par défaut, et il ne doit pas y en avoir** : l'empreinte dépend de la clé, et une
empreinte fausse produit un fichier syntaxiquement parfait qu'Android rejette sans
prévenir. Tant que `ANDROID_CERT_FINGERPRINTS` n'est pas réglée, la route rend **503 en
nommant la variable** — un échec qu'un humain peut trouver, au lieu d'un fichier qui a
l'air juste.

Aujourd'hui, `android/app/build.gradle.kts` signe encore la release avec la clé de
**débogage** (`signingConfig = signingConfigs.getByName("debug")`, un `TODO` de
`flutter create`). Cette clé est locale à la machine qui construit : publier son
empreinte associerait le domaine à des APK que personne d'autre ne peut produire, et
l'association casserait au premier vrai build. Il faut donc une clé de release avant de
pouvoir remplir cette variable.

### Ce qui est éprouvé, et ce qui ne l'est pas

Éprouvé :

- les deux fichiers sont servis en `application/json`, sans redirection, avec l'App ID
  complet et l'empreinte — vérifié par `curl` contre le serveur lancé, et par
  `tests/test_app_association.py`, dont chaque assertion a été éprouvée par mutation ;
- une empreinte mal formée — tronquée, un seul caractère non hexadécimal, les
  deux-points manquants — fait échouer le **démarrage** du serveur ;
- le manifeste Android fusionné porte bien `autoVerify="true"` et les deux hôtes
  (lu dans `build/app/intermediates/merged_manifest/…`) ;
- `MainActivity.kt` compile, l'application iOS compile, `flutter analyze` est propre et
  les témoins Dart passent ;
- un lien venu d'un hôte que l'appareil n'a pas configuré est **nommé** au lieu d'être
  annoncé comme un paste disparu (`test/lien_entrant_test.dart`).

**Pas éprouvé, et il faut le dire :** rien n'a tourné sur un appareil. Aucun lien
universel n'a été touché du doigt, ni sur iPhone ni sur Android. La vérification réelle
ne peut avoir lieu qu'après le déploiement des fichiers sur les hôtes, puisque c'est le
système qui va les lire à l'installation. Il reste aussi, côté iOS, à activer la
capacité **Associated Domains** sur l'App ID chez Apple et à régénérer le profil de
provisionnement : sans cela, la signature échoue — bruyamment, pour une fois.

## Construire

```bash
flutter pub get
outils/construire-xcframework.sh        # iOS seulement, macOS + Xcode requis
outils/cabler-extension-ios.sh          # idem : ajoute la cible Partage au projet
outils/engendrer_langages.py            # après un changement de app/languages.json
flutter run
```

L'ordre compte : `cabler-extension-ios.sh` refuse de tourner si l'XCFramework et les
liaisons Swift n'existent pas encore, plutôt que de câbler une cible qui ne compilerait pas.

Pour poser sur un iPhone branché, extension comprise :

```bash
outils/appareil-ios.sh                  # construit, vérifie, installe
outils/temoin-feuille-de-partage.sh     # ouvre la feuille sur un simulateur et regarde
```

`appareil-ios.sh` refuse de choisir entre deux appareils, impose l'équipe payante, et
**regarde dans le paquet** que `Partage.appex` est sous `PlugIns/` avant de poser : une
extension posée à côté de l'application n'existe pas pour iOS, et l'installation réussit
sans un mot d'explication.

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
