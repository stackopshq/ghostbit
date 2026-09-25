#!/usr/bin/env bash
# Construit le cœur crypto en XCFramework consommable par Xcode, bindings Swift compris.
#
# Sortie : ios/GhostbitCrypto.xcframework + ios/Generated/*.swift
# Prérequis : macOS avec Xcode (`xcodebuild -create-xcframework`, `lipo`).
#
# ─── À quoi sert cet XCFramework, puisque l'application est en Flutter ───
#
# Il ne sert **pas** à l'application. Celle-ci passe par `flutter_rust_bridge`, qui compile
# le même cœur autrement — voir `rust/Cargo.toml`. Il sert à la **feuille de partage
# iOS**, qui est une extension : un processus séparé au budget mémoire serré, où Flutter
# ne tient pas en pratique. Cette extension est donc du Swift, et c'est UniFFI qui lui
# donne accès au cœur.
#
# Les deux générateurs sont **frères** et non empilés : chacun se pose directement sur
# `ghost-crypto`. Faire passer l'un par l'autre aurait ajouté une frontière sans rien
# apporter.
#
# ─── Une chose que ce script ne peut pas garantir ───
#
# Les bindings Swift sont générés depuis la bibliothèque **déjà compilée** (`--library`) et
# non depuis un fichier de déclaration : la surface Swift décrit donc le binaire réellement
# embarqué, et pas une déclaration qui aurait divergé. C'est la même précaution que chez
# ghostcal, dont ce script est adapté.
set -euo pipefail

CRATE=ghost-crypto-ffi
LIB=libghost_crypto_ffi.a
PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Le cœur cryptographique vit dans le dépôt de la suite, jamais recopié ici : une seule
# implémentation pour tous les produits. `GHOSTSUITE` dit où le trouver ; par défaut, le
# clone voisin, la suite vivant à côté des produits.
ROOT="${GHOSTSUITE:-$(cd "$PRODUIT/../../.." && pwd)/suite}"
if [[ ! -d "$ROOT/crates/$CRATE" ]]; then
  echo "Cœur commun introuvable : $ROOT/crates/$CRATE" >&2
  echo "Clonez git@git.stackops.ch:stackops/ghostsuite.git à côté de ce dépôt," >&2
  echo "ou indiquez son chemin :  GHOSTSUITE=/chemin/vers/ghostsuite $0" >&2
  exit 1
fi
OUT="$PRODUIT/ios"
BUILD="$ROOT/target"

cd "$ROOT"

for cible in aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios; do
  rustup target add "$cible" >/dev/null
  # `--lib` seulement : le binaire `uniffi-bindgen` est un outil d'hôte, il n'a rien à
  # faire dans une compilation croisée vers iOS.
  cargo build --release --lib -p "$CRATE" --target "$cible"
done

# Le simulateur doit accepter les deux architectures, et un XCFramework n'admet qu'une
# tranche par plateforme : d'où le `lipo`.
SIM="$BUILD/ios-simulator"
mkdir -p "$SIM"
lipo -create \
  "$BUILD/aarch64-apple-ios-sim/release/$LIB" \
  "$BUILD/x86_64-apple-ios/release/$LIB" \
  -output "$SIM/$LIB"

rm -rf "$OUT/Generated" "$OUT/Headers" "$OUT/GhostbitCrypto.xcframework"
mkdir -p "$OUT/Generated" "$OUT/Headers"

cargo run --release --bin uniffi-bindgen -- generate \
  --library "$BUILD/aarch64-apple-ios/release/$LIB" \
  --language swift \
  --out-dir "$OUT/Generated"

# Xcode exige que la carte de modules s'appelle `module.modulemap` et voisine les en-têtes.
mv "$OUT/Generated"/*.h "$OUT/Headers/"
mv "$OUT/Generated"/*.modulemap "$OUT/Headers/module.modulemap"

xcodebuild -create-xcframework \
  -library "$BUILD/aarch64-apple-ios/release/$LIB" -headers "$OUT/Headers" \
  -library "$SIM/$LIB" -headers "$OUT/Headers" \
  -output "$OUT/GhostbitCrypto.xcframework"

echo "XCFramework : $OUT/GhostbitCrypto.xcframework"
echo "Bindings Swift : $OUT/Generated"
