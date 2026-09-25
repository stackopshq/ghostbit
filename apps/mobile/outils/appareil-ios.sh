#!/usr/bin/env bash
# Pose GhostBit sur un iPhone branché, **feuille de partage comprise**.
#
#   outils/appareil-ios.sh
#
# ─── Ce qu'il existe pour empêcher ───
#
# « La cible est câblée » et « la feuille de partage apparaît » sont deux affirmations
# différentes, et la première a déjà été prise pour la seconde dans ce dépôt. Une cible
# peut être dans le projet, compiler, être signée, et ne jamais donner d'extension sur
# l'appareil — il suffit que la phase d'intégration ne l'ait pas copiée. Ce script regarde
# **dans le paquet construit** avant de poser quoi que ce soit.
#
# ─── L'équipe ───
#
# Elle est imposée, jamais découverte. Voir `cabler-extension-ios.rb` : deux certificats
# cohabitent dans ce trousseau, et signer avec l'équipe personnelle produit une application
# qui s'installe, se lance, et dont le groupe d'applications ne marche pas.
set -euo pipefail

EQUIPE="${EQUIPE_GHOSTBIT:-9WHCJ5W7S6}"
PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IOS="$PRODUIT/ios"
APPEX="Partage.appex"

dire() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }

# ── L'appareil ────────────────────────────────────────────────────────────────
#
# Repris de `ghostpass/tools/ios/lib-appareil.sh`, et pour la même raison : sans ce refus,
# le script prend le premier appareil venu **en silence**, et l'on croit poser sur l'iPhone
# qu'on regarde alors qu'on pose sur l'iPad resté dans le tiroir.
candidats="$(xcrun devicectl list devices 2>/dev/null |
  awk '$0 ~ /connected/ && $0 !~ /no DDI/ && $0 !~ /unavailable/ {
         nom = $1; for (i = 2; $i !~ /coredevice\.local/; i++) nom = nom " " $i
         print nom "\t" $(i+1) }')"
if [[ -n "${GHOSTBIT_APPAREIL:-}" ]]; then
  candidats="$(printf '%s\n' "$candidats" | grep -i -- "$GHOSTBIT_APPAREIL" || true)"
fi
nombre="$(printf '%s' "$candidats" | grep -c . || true)"
if [[ "$nombre" -gt 1 ]]; then
  echo "Plusieurs appareils sont branchés — précisez lequel :" >&2
  printf '%s\n' "$candidats" | cut -f1 | sed 's/^/  /' >&2
  echo >&2
  echo "  GHOSTBIT_APPAREIL=\"iPhone 17\" $0" >&2
  exit 1
fi
NOM="$(printf '%s' "$candidats" | cut -f1)"
DEVICE="$(printf '%s' "$candidats" | cut -f2)"
if [[ -z "$DEVICE" ]]; then
  echo "Aucun iPhone utilisable n'est branché." >&2
  echo >&2
  echo "  1. Brancher le téléphone en USB — câble de données, pas d'alimentation." >&2
  echo "  2. Le déverrouiller et répondre « Se fier »." >&2
  echo "  3. Réglages > Confidentialité et sécurité > Mode développeur." >&2
  echo >&2
  xcrun devicectl list devices 2>&1 | sed -n '1,8p' >&2
  exit 1
fi
dire "Appareil : ${NOM:-inconnu} ($DEVICE)"
dire "Équipe   : $EQUIPE (imposée)"

# ── Les prérequis du câblage ──────────────────────────────────────────────────
[[ -d "$IOS/GhostbitCrypto.xcframework" ]] ||
  { echo "XCFramework absent — lancez outils/construire-xcframework.sh" >&2; exit 1; }
"$PRODUIT/outils/cabler-extension-ios.sh" >/dev/null

# ── Construction ──────────────────────────────────────────────────────────────
#
# Depuis le `.xcworkspace`, pas le `.xcodeproj` : c'est lui que CocoaPods entretient, et
# le projet seul ne voit pas les pods.
dire "Construction pour l'appareil"
SORTIE="$IOS/.build-appareil"
JOURNAL="$(mktemp)"
trap 'rm -f "$JOURNAL"' EXIT
if ! xcodebuild -workspace "$IOS/Runner.xcworkspace" -scheme Runner -configuration Debug \
  -destination "platform=iOS,id=$DEVICE" -derivedDataPath "$SORTIE" \
  DEVELOPMENT_TEAM="$EQUIPE" -allowProvisioningUpdates build >"$JOURNAL" 2>&1; then
  echo "La construction a échoué :" >&2
  grep -aE "error:|Signing for|Provisioning profile" "$JOURNAL" | sort -u | head -15 >&2
  if grep -qa "program membership that is eligible" "$JOURNAL"; then
    echo >&2
    echo "L'équipe $EQUIPE n'a pas d'adhésion payante : elle ne peut pas provisionner le" >&2
    echo "groupe d'applications. Voir EQUIPE_GHOSTBIT." >&2
  fi
  if grep -qa "There is no application group" "$JOURNAL" ||
     grep -qa "is not available" "$JOURNAL"; then
    echo >&2
    echo "Un identifiant de groupe d'applications est unique chez Apple, toutes équipes" >&2
    echo "confondues, et ne se libère pas. Si group.dev.ghostbit est immobilisé, il faut" >&2
    echo "en choisir un autre — dans les deux .entitlements, les deux sources Swift," >&2
    echo "lib/services/historique.dart et cabler-extension-ios.rb." >&2
  fi
  echo >&2
  echo "Journal complet : $JOURNAL" >&2
  trap - EXIT
  exit 1
fi

APP="$(/usr/bin/find "$SORTIE/Build/Products" -maxdepth 3 -name "Runner.app" | head -1)"
[[ -n "$APP" ]] || { echo "Application introuvable après construction." >&2; exit 1; }

# ── Ce qui sépare « câblé » de « fonctionnel » ────────────────────────────────
#
# L'extension voyage **dans** l'application ; posée à côté, elle n'existe pas pour iOS.
# Si elle manque, l'installation réussit et la feuille de partage n'apparaît jamais, sans
# un mot d'explication. On regarde donc avant de poser.
if [[ ! -d "$APP/PlugIns/$APPEX" ]]; then
  echo "L'extension n'est pas dans le paquet construit : $APP/PlugIns/$APPEX" >&2
  echo "La phase « Embed App Extensions » de la cible Runner a-t-elle survécu ?" >&2
  /usr/bin/find "$APP" -maxdepth 2 -name "PlugIns" -o -maxdepth 2 -name "*.appex" >&2
  exit 1
fi
dire "Paquet"
printf '  %s\n' "$(basename "$APP")" >&2
/usr/bin/find "$APP/PlugIns" "$APP/Frameworks" -maxdepth 1 -mindepth 1 \
  \( -name "*.appex" -o -name "*.framework" \) 2>/dev/null |
  sed "s|.*/|    |" >&2

# Et elle doit être signée avec la bonne équipe, avec le bon groupe. Une extension signée
# par l'équipe personnelle s'installe et ne voit pas le conteneur partagé.
dire "Droits de l'extension, tels qu'ils sont signés"
codesign -d --entitlements - --xml "$APP/PlugIns/$APPEX" 2>/dev/null |
  plutil -convert xml1 -o - - |
  grep -A2 "application-groups\|team-identifier" | sed 's/^/  /' >&2

# ── Installation ──────────────────────────────────────────────────────────────
# `xcrun … | grep` rend le code de sortie de `grep`, pas celui de l'installation : le
# script annonçait « installé » sur un échec net. On garde donc la sortie, et le code.
dire "Installation"
POSE="$(mktemp)"
if ! xcrun devicectl device install app --device "$DEVICE" "$APP" >"$POSE" 2>&1; then
  echo "L'installation a échoué :" >&2
  grep -aE "ERROR|error|Appex|Impossible" "$POSE" | head -10 >&2
  rm -f "$POSE"
  exit 1
fi
grep -aE "App installed|bundleID|installationURL" "$POSE" | head -5 >&2
rm -f "$POSE"

cat >&2 <<'RESTE'

Reste un geste que ce script ne peut pas faire :

  Ouvrir GhostBit une fois et régler l'adresse de l'instance. Sans elle, la feuille de
  partage lève `adresseAbsente` : c'est l'application qui l'écrit dans le groupe.

Puis, pour voir la feuille : partager un texte depuis Notes ou Safari, faire défiler la
rangée d'applications jusqu'au bout, « Autres », et activer GhostBit. iOS ne montre pas
d'emblée une extension qu'il n'a jamais vue servir.

Si l'application refuse de se lancer : Réglages > Général > VPN et gestion de l'appareil
> votre compte > Se fier.
RESTE
