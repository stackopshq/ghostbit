#!/usr/bin/env bash
# Câble la cible « Partage » dans ios/Runner.xcodeproj — voir cabler-extension-ios.rb.
#
# La bibliothèque `xcodeproj` n'est pas installée sur le ruby du système ; elle vient avec
# CocoaPods, que Flutter exige déjà pour iOS. On emprunte donc son GEM_HOME plutôt que
# d'imposer un `gem install` de plus.
set -euo pipefail
OUTILS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBEXEC=$(ls -d /opt/homebrew/Cellar/cocoapods/*/libexec 2>/dev/null | tail -1)
if [[ -z "${LIBEXEC:-}" ]]; then
  echo "CocoaPods introuvable — c'est lui qui fournit la bibliothèque xcodeproj." >&2
  exit 1
fi
GEM_HOME="$LIBEXEC" ruby "$OUTILS/cabler-extension-ios.rb"
