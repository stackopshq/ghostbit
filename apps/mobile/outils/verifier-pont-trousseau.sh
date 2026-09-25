#!/usr/bin/env bash
# Le pont de trousseau entre la feuille de partage iOS et l'application tient-il encore ?
#
# ─── Ce que ce script mesure, et pourquoi il existe ───
#
# La feuille de partage est du Swift ; elle écrit l'historique **directement** dans le
# trousseau, avec l'API `Security` d'Apple. L'application est en Flutter et le lit par
# `flutter_secure_storage`. Pour que le second retrouve ce que le premier a écrit,
# l'élément doit porter exactement les attributs que ce paquet emploie.
#
# Le mode de défaillance est le pire qui soit : si un attribut diffère, **rien n'échoue**.
# L'écriture réussit côté Swift, la lecture réussit côté Dart, et l'historique est
# simplement vide. Un paste créé depuis la feuille de partage devient alors invisible et
# irrévocable, sans qu'aucun message n'apparaisse nulle part.
#
# Ce script relit donc la constante **dans le paquet installé**, plutôt que de faire
# confiance à une valeur recopiée dans un commentaire. Une montée de version qui la
# changerait fait échouer ce contrôle au lieu de casser le pont en silence.
set -euo pipefail

PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWIFT="$PRODUIT/ios/Partage/Historique.swift"
DART="$PRODUIT/lib/services/historique.dart"

paquet() {
  local chemin
  chemin=$(grep -A8 "^  flutter_secure_storage:$" "$PRODUIT/pubspec.lock" \
    | grep 'version:' | tr -d ' "' | cut -d: -f2)
  echo "$HOME/.pub-cache/hosted/pub.dev/flutter_secure_storage-$chemin"
}

PAQUET="$(paquet)"
if [[ ! -d "$PAQUET" ]]; then
  echo "Paquet flutter_secure_storage introuvable : $PAQUET" >&2
  echo "Lancez d'abord « flutter pub get »." >&2
  exit 1
fi

# `AppleOptions.defaultAccountName` — le `kSecAttrService` que le paquet emploie.
ATTENDU=$(grep -o "defaultAccountName = '[^']*'" "$PAQUET/lib/options/apple_options.dart" \
  | cut -d"'" -f2)
if [[ -z "$ATTENDU" ]]; then
  echo "ÉCHEC : la constante defaultAccountName n'existe plus dans le paquet." >&2
  echo "Le pont ne peut plus être vérifié — c'est un échec, pas un contrôle à sauter." >&2
  exit 1
fi

echec=0
verifier() {
  local fichier="$1" motif="$2" quoi="$3"
  if grep -q "$motif" "$fichier"; then
    echo "  ok   $quoi"
  else
    echo "  ÉCHEC $quoi — attendu « $motif » dans ${fichier#"$PRODUIT"/}" >&2
    echec=1
  fi
}

echo "kSecAttrService attendu par le paquet : $ATTENDU"
verifier "$SWIFT" "\"$ATTENDU\"" "le Swift emploie le même service que le paquet"
verifier "$DART" "'$ATTENDU'" "le Dart nomme le même service, explicitement"

# Le groupe d'accès doit être identique des deux côtés, et il n'a pas de défaut : c'est
# une valeur que nous choisissons, donc elle ne peut être vérifiée que par comparaison.
GROUPE_SWIFT=$(grep -o 'group\.[a-z.]*' "$PRODUIT/ios/Partage/ShareViewController.swift" | head -1)
verifier "$DART" "$GROUPE_SWIFT" "le Dart et le Swift partagent le groupe $GROUPE_SWIFT"

# Le nom de la clé, enfin : c'est lui qui désigne l'élément.
CLE=$(grep -o 'ghostbit\.historique\.v[0-9]*' "$DART" | head -1)
verifier "$SWIFT" "$CLE" "la clé $CLE est la même des deux côtés"

exit $echec
