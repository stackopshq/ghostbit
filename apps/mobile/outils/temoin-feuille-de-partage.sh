#!/usr/bin/env bash
# GhostBit apparaît-il dans la feuille de partage d'iOS, et reçoit-il le contenu ?
#
#   outils/temoin-feuille-de-partage.sh [udid-du-simulateur]
#
# ─── Ce qu'il répond, et ce que rien d'autre ne répondait ───
#
# « La cible est câblée » n'est pas « la feuille apparaît ». Entre les deux il y a eu, dans
# ce dépôt, un `CFBundleVersion` vide qui laissait tout compiler et tout signer, et que
# seule l'installation sur un appareil a révélé. Ce script pousse d'un cran : il ouvre la
# feuille et regarde.
#
# Il tourne sur le **simulateur**, et c'est assumé. Sur un appareil, le geste équivalent
# demande une main humaine, et un journal ne la remplace pas : `NSLog` depuis une extension
# iOS n'est visible ni par `devicectl --console` ni par `idevicesyslog`.
set -euo pipefail

PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IOS="$PRODUIT/ios"

SIM="${1:-}"
if [[ -z "$SIM" ]]; then
  # Un simulateur déjà démarré, s'il n'y en a qu'un — même refus que pour les appareils
  # branchés : choisir seul entre deux, c'est mesurer sur celui qu'on ne regarde pas.
  demarres="$(xcrun simctl list devices booted | grep -oE '\([0-9A-F-]{36}\) \(Booted\)' | grep -oE '[0-9A-F-]{36}' || true)"
  nombre="$(printf '%s' "$demarres" | grep -c . || true)"
  if [[ "$nombre" -gt 1 ]]; then
    echo "Plusieurs simulateurs sont démarrés — précisez lequel :" >&2
    xcrun simctl list devices booted >&2
    exit 1
  fi
  SIM="$demarres"
fi
if [[ -z "$SIM" ]]; then
  echo "Aucun simulateur démarré. Par exemple :" >&2
  echo "  xcrun simctl boot 'iPhone 17 Pro'" >&2
  exit 1
fi
echo "▸ Simulateur : $SIM" >&2

# `xcodebuild` éteint parfois le simulateur entre deux invocations, et `simctl install`
# répond alors « Unable to lookup in current state: Shutdown » — un message qui ressemble
# à un identifiant erroné. `bootstatus -b` le rallume s'il le faut et **attend** qu'il
# soit prêt ; sans l'attente, l'installation part sur un simulateur à moitié démarré.
xcrun simctl bootstatus "$SIM" -b >/dev/null

[[ -d "$IOS/GhostbitCrypto.xcframework" ]] ||
  { echo "XCFramework absent — lancez outils/construire-xcframework.sh" >&2; exit 1; }
"$PRODUIT/outils/cabler-extension-ios.sh" >/dev/null
GEM_HOME="$(ls -d /opt/homebrew/Cellar/cocoapods/*/libexec | tail -1)" \
  ruby "$PRODUIT/outils/cabler-temoin-partage.rb" >/dev/null

RESULTATS="$IOS/.temoin-partage"
DERIVE="$IOS/.build-temoin"
rm -rf "$RESULTATS"

commun=(
  -workspace "$IOS/Runner.xcworkspace"
  -scheme TemoinPartage
  -destination "platform=iOS Simulator,id=$SIM"
  -derivedDataPath "$DERIVE"
)

# ─── Construire, **poser**, puis regarder ────────────────────────────────────
#
# `xcodebuild test` installe l'application que conduit le témoin — l'hôte — et **pas**
# Runner, qui n'est qu'une dépendance de compilation. L'extension enregistrée auprès du
# simulateur reste donc celle de la fois d'avant.
#
# Ce n'est pas théorique : le témoin a d'abord rougi sur un nom d'application corrigé dans
# les sources et jamais réinstallé. Un témoin qui mesure la version précédente peut aussi
# bien verdir à tort, et c'est le cas qui ne se voit pas.
xcodebuild build-for-testing "${commun[@]}" CODE_SIGNING_ALLOWED=NO

APP="$(/usr/bin/find "$DERIVE/Build/Products" -maxdepth 3 -name "Runner.app" | head -1)"
[[ -n "$APP" ]] || { echo "Runner.app introuvable après construction." >&2; exit 1; }
[[ -d "$APP/PlugIns/Partage.appex" ]] || {
  echo "L'extension n'est pas dans le paquet : $APP/PlugIns/Partage.appex" >&2
  exit 1
}
echo "▸ Pose de $(basename "$APP") (avec Partage.appex)" >&2
xcrun simctl install "$SIM" "$APP"

# L'enregistrement auprès du système, avant même d'ouvrir la feuille. S'il manque, le
# témoin échouera plus loin sans dire pourquoi ; ici, la cause est nommée.
#
# Il est **asynchrone** : `simctl install` rend la main avant que `pluginkit` ne connaisse
# l'extension. Regarder tout de suite donnait un échec parfaitement reproductible et
# parfaitement faux. On attend donc, avec une borne — une attente sans borne transformerait
# une vraie absence en blocage, et « pas pu regarder » doit échouer, pas pendre.
#
# Et l'installation ne suffit pas à la déclencher : il faut que l'application ait été
# **lancée** une fois. Installée et jamais ouverte, elle reste soixante secondes absente de
# `pluginkit` — mesuré, et déroutant, puisque le paquet est bien là et que la commande ne
# se plaint de rien. C'est aussi le geste réel : personne n'installe GhostBit sans
# l'ouvrir, ne serait-ce que pour régler l'adresse de l'instance.
xcrun simctl launch "$SIM" dev.ghostbit.ghostbit >/dev/null
sleep 3
xcrun simctl terminate "$SIM" dev.ghostbit.ghostbit >/dev/null 2>&1 || true

#
# ─── `grep -q` derrière `pipefail` ne peut pas dire oui ──────────────────────
#
# La première version écrivait `simctl spawn … | grep -q …`. Elle a rendu « pas enregistrée »
# soixante secondes durant, sur un simulateur où la même commande, tapée à la main,
# trouvait l'extension. `grep -q` s'arrête au premier accord et ferme le tube ; `simctl`
# reçoit SIGPIPE et sort en 141 ; `pipefail` retient ce 141 et l'`if` lit un échec. Le
# contrôle ne pouvait **pas** réussir — et c'est le pire mode de défaillance d'un témoin,
# parce qu'un témoin toujours rouge se soupçonne, tandis qu'un `! grep -q` toujours vrai
# aurait tout laissé passer. On capture d'abord, on cherche ensuite.
enregistree=0
for _ in $(seq 1 60); do
  liste="$(xcrun simctl spawn "$SIM" pluginkit -mAv 2>/dev/null || true)"
  if [[ "$liste" == *"dev.ghostbit.ghostbit.Partage"* ]]; then
    enregistree=1
    break
  fi
  sleep 1
done
if [[ "$enregistree" -ne 1 ]]; then
  echo "L'extension n'est pas enregistrée auprès du simulateur 60 s après l'installation." >&2
  exit 1
fi
echo "▸ Enregistrée auprès de pluginkit" >&2

xcodebuild test-without-building "${commun[@]}" \
  -resultBundlePath "$RESULTATS" \
  CODE_SIGNING_ALLOWED=NO
