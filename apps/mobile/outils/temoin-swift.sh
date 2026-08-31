#!/usr/bin/env bash
# Le témoin du format de fragment côté Swift, sans Xcode ni simulateur.
#
# Compile `Fragment.swift` avec son témoin et l'exécute. Volontairement indépendant du
# projet Xcode : un témoin qui exige une chaîne d'outils complète est un témoin qu'on ne
# lance pas — et un témoin qu'on ne lance pas est vert.
set -euo pipefail
PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SORTIE="$(mktemp -d)"
trap 'rm -rf "$SORTIE"' EXIT
swiftc -O \
  "$PRODUIT/ios/Partage/Fragment.swift" \
  "$PRODUIT/ios/Partage/Temoins/main.swift" \
  -o "$SORTIE/temoin"
"$SORTIE/temoin"
