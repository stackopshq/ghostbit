#!/usr/bin/env bash
# Le cœur Rust se compile-t-il pour les trois architectures Android que Flutter livre ?
#
# ─── Ce que ce script mesure, et ce qu'il ne mesure pas ───
#
# Il **ne remplace pas** `flutter build apk`. Il ne dit rien de Gradle, de l'AGP, du
# manifeste, ni de l'empaquetage des `.so` dans l'APK — tout cela est de la mécanique
# Flutter standard, que cargokit pilote depuis `rust_builder/android/build.gradle`.
#
# Il mesure la seule partie qui nous appartient et qui peut casser à cause de **notre**
# code : est-ce que `rust_lib_ghostbit`, et à travers lui `ghost-crypto` avec ses
# dépendances cryptographiques, produit bien une bibliothèque partagée pour chacune des
# trois ABI ? C'est là que se logent les surprises — une dépendance qui suppose une
# plateforme, un `getrandom` sans support Android, une intrinsèque absente sur armv7.
#
# Il a d'abord existé faute de JDK, quand `flutter build apk` était impossible ici. Ce
# n'est plus le cas — l'APK se construit — et il garde pourtant sa raison d'être : la
# comparaison de **surface exportée** avec la bibliothèque hôte, que la construction de
# l'APK ne fait pas. Un `.so` peut entrer dans l'APK et n'exporter aucun répartiteur ;
# l'échec est alors au premier appel Dart, pas à la compilation.
#
# Ce contrôle sait rougir, et cela a été mesuré : en lui donnant une autre bibliothèque
# hôte, il sort 1 et nomme la différence. Sans cette vérification, un contrôle toujours
# vert ne dirait rien de plus qu'un contrôle absent.
set -euo pipefail

PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Le niveau d'API du wrapper clang doit être celui du `minSdk` du produit — 24, la valeur
# par défaut de Flutter (`FlutterExtension.kt`). Un wrapper d'un autre niveau lie contre
# des symboles absents des appareils qu'on prétend viser, et l'échec est à l'exécution.
API=24
NDK="${ANDROID_NDK_HOME:-$(ls -d "$HOME"/Library/Android/sdk/ndk/* 2>/dev/null | sort -V | tail -1)}"
if [[ ! -d "$NDK" ]]; then
  echo "NDK introuvable. Posez ANDROID_NDK_HOME." >&2
  exit 1
fi
BIN="$NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin"
echo "NDK : $(basename "$NDK")  (API $API)"

# Les trois ABI que Flutter livre. `x86` (i686) a été retiré de Flutter : le compiler
# donnerait une bibliothèque qu'aucun APK n'embarque.
compiler() {
  local abi="$1" cible="$2" prefixe="$3"
  local majuscule
  majuscule=$(echo "$cible" | tr 'a-z-' 'A-Z_')
  echo "  $abi ($cible)"
  env \
    "CARGO_TARGET_${majuscule}_LINKER=$BIN/${prefixe}${API}-clang" \
    "CC_${cible//-/_}=$BIN/${prefixe}${API}-clang" \
    "AR_${cible//-/_}=$BIN/llvm-ar" \
    cargo build --release --lib --manifest-path "$PRODUIT/rust/Cargo.toml" --target "$cible" 2>&1 \
    | grep -E "^(error|warning: unused)" || true
}

compiler arm64-v8a   aarch64-linux-android     aarch64-linux-android
compiler armeabi-v7a armv7-linux-androideabi   armv7a-linux-androideabi
compiler x86_64      x86_64-linux-android      x86_64-linux-android

echo
echo "Bibliothèques produites :"
echec=0
for cible in aarch64-linux-android armv7-linux-androideabi x86_64-linux-android; do
  so="$PRODUIT/rust/target/$cible/release/librust_lib_ghostbit.so"
  if [[ -f "$so" ]]; then
    printf "  ok    %-26s %s\n" "$cible" "$(du -h "$so" | cut -f1)"
    # La bibliothèque doit exporter le **répartiteur** de flutter_rust_bridge, sinon Dart
    # la charge et ne trouve rien — un échec au premier appel, pas à la compilation.
    #
    # Ce n'est pas un symbole par fonction. La première version de ce contrôle cherchait
    # `frbgen_ghostbit`, et échouait sur les trois architectures alors que les trois
    # bibliothèques étaient bonnes : flutter_rust_bridge 2.x n'exporte pas `sceller` ni
    # `ouvrir`, il expose **un** répartiteur et achemine les appels par un discriminant.
    # Le contrôle accusait la compilation d'un défaut qui était le sien.
    #
    # La bonne référence n'est donc pas un nom deviné, mais la bibliothèque **hôte** —
    # celle que `flutter test` et l'application chargent réellement. On compare les deux
    # surfaces : si l'Android exporte ce que l'hôte exporte, elle est chargeable.
    for symbole in frb_pde_ffi_dispatcher_primary frb_pde_ffi_dispatcher_sync \
                   frb_init_frb_dart_api_dl store_dart_post_cobject; do
      if ! "$BIN/llvm-nm" -D --defined-only "$so" 2>/dev/null | grep -q " T $symbole$"; then
        echo "        ÉCHEC : $symbole n'est pas exporté" >&2
        echec=1
      fi
    done
  else
    echo "  ÉCHEC $cible : pas de .so" >&2
    echec=1
  fi
done
# ─── La comparaison qui vaut mieux qu'une liste devinée ──────────────────────
# On construit la même bibliothèque pour l'hôte et on compare les surfaces exportées.
# Un symbole que l'hôte exporte et qu'Android n'exporte pas est une différence réelle ;
# une liste écrite à la main ne dit que ce que son auteur croyait.
echo
echo "Surface exportée, comparée à la bibliothèque hôte :"
cargo build --release --lib --manifest-path "$PRODUIT/rust/Cargo.toml" >/dev/null 2>&1
HOTE="$PRODUIT/rust/target/release/librust_lib_ghostbit.dylib"
if [[ -f "$HOTE" ]]; then
  nm -gU "$HOTE" | grep " T " | sed 's/.* T _//' | sort > /tmp/ghostbit-hote.syms
  for cible in aarch64-linux-android armv7-linux-androideabi x86_64-linux-android; do
    so="$PRODUIT/rust/target/$cible/release/librust_lib_ghostbit.so"
    "$BIN/llvm-nm" -D --defined-only "$so" | grep " T " | sed 's/.* T //' | sort \
      > /tmp/ghostbit-android.syms
    if diff -q /tmp/ghostbit-hote.syms /tmp/ghostbit-android.syms >/dev/null; then
      printf "  ok    %-26s %s symboles, identiques à l'hôte\n" "$cible" \
        "$(wc -l < /tmp/ghostbit-android.syms | tr -d ' ')"
    else
      echo "  ÉCHEC $cible : surface différente de l'hôte" >&2
      diff /tmp/ghostbit-hote.syms /tmp/ghostbit-android.syms >&2 || true
      echec=1
    fi
  done
else
  echo "  (bibliothèque hôte absente, comparaison sautée)" >&2
  echec=1
fi

exit $echec
