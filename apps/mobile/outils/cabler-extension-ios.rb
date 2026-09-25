#!/usr/bin/env ruby
# Câble la cible « Partage » — la feuille de partage iOS — dans `ios/Runner.xcodeproj`.
#
#   outils/cabler-extension-ios.sh
#
# ─── Pourquoi un script, et pas Xcode ───
#
# Une cible ajoutée à la main dans Xcode ne se relit pas, ne se diffe pas, et ne se refait
# pas. Le jour où `flutter create` ou une régénération du projet l'efface, personne ne sait
# ce qu'il y avait. Ce script est donc **idempotent** : il retire la cible si elle existe
# et la reconstruit, si bien qu'il vaut à la fois installation et documentation exécutable.
#
# ─── Pourquoi pas xcodegen, comme ghostpass ───
#
# `apps/ios/` de ghostpass décrit tout son projet en `project.yml` et ne versionne pas le
# `.xcodeproj`. C'est plus propre, et ce serait le bon choix pour un projet iOS natif.
#
# Il ne se transpose pas ici, et la raison est mesurable : le `Runner.xcodeproj` de Flutter
# n'est pas un projet ordinaire. Il porte deux phases de script — `xcode_backend.sh build`
# et `xcode_backend.sh embed_and_thin` — une chaîne de `xcconfig` (`Generated.xcconfig`,
# puis ceux que CocoaPods pose), et il est bâti depuis un `.xcworkspace` que `pod install`
# entretient. Passer sous xcodegen voudrait dire redéclarer tout cela, puis relancer
# `pod install` après **chaque** génération — le projet généré ne serait jamais celui qu'on
# compile. On ajoute donc une cible au projet que Flutter fournit, plutôt que de reprendre
# la fabrication du projet.
#
# La bibliothèque employée, `xcodeproj`, est celle de CocoaPods : c'est déjà elle qui écrit
# dans ce fichier à chaque `pod install`. Deux écrivains, une seule grammaire.

require "xcodeproj"

IOS = File.expand_path("../ios", __dir__)
PROJET = File.join(IOS, "Runner.xcodeproj")
CIBLE = "Partage"
GROUPE = "group.dev.ghostbit"

# ─── L'équipe est imposée, jamais découverte ─────────────────────────────────
#
# Le trousseau de cette machine porte **deux** certificats « Apple Development » :
#
#   OU=6BBGV83S5C, O=CLARA SANDRA AMELIE VANACKER   ← équipe personnelle
#   OU=9WHCJ5W7S6, O=Clara Vanacker                 ← adhésion payante
#
# `flutter create` avait écrit le premier dans ce projet. C'est le pire des deux mondes :
# une équipe personnelle **ne peut pas provisionner de groupe d'applications**, et la
# signature réussit quand même. On obtient une application qui s'installe, se lance, et
# dont la feuille de partage ne trouve jamais l'adresse du serveur — `UserDefaults(suiteName:)`
# rend `nil` sans un mot. Le symptôme est à mille lieues de la cause.
#
# `EQUIPE_GHOSTBIT` permet de la changer ; l'absence de valeur ne fait pas découvrir, elle
# fait prendre celle-ci. Découvrir, c'est ce qui avait choisi la mauvaise.
EQUIPE = ENV.fetch("EQUIPE_GHOSTBIT", "9WHCJ5W7S6")

projet = Xcodeproj::Project.open(PROJET)
runner = projet.targets.find { |t| t.name == "Runner" } or abort("Cible Runner introuvable")

# ─── Idempotence : on défait avant de refaire ────────────────────────────────
ancienne = projet.targets.find { |t| t.name == CIBLE }
if ancienne
  runner.dependencies.select { |d| d.target == ancienne }.each(&:remove_from_project)
  runner.build_phases.grep(Xcodeproj::Project::Object::PBXCopyFilesBuildPhase)
        .select { |p| p.name == "Embed App Extensions" }.each(&:remove_from_project)
  ancienne.remove_from_project
end
projet.main_group.children.select { |g| g.respond_to?(:name) && g.name == CIBLE }
      .each(&:remove_from_project)

# ─── La cible ────────────────────────────────────────────────────────────────
partage = projet.new_target(
  :app_extension, CIBLE, :ios,
  runner.build_configuration_list.build_settings("Release")["IPHONEOS_DEPLOYMENT_TARGET"] || "15.0"
)

# La version vient de Flutter, par un xcconfig dédié — voir `ios/Partage/Partage.xcconfig`,
# qui explique pourquoi elle ne peut pas être écrite en dur ici.
xcconfig = projet.main_group.new_reference("Partage/Partage.xcconfig")

partage.build_configurations.each do |config|
  config.base_configuration_reference = xcconfig
  s = config.build_settings
  s["PRODUCT_BUNDLE_IDENTIFIER"] = "dev.ghostbit.ghostbit.Partage"
  s["PRODUCT_NAME"] = "$(TARGET_NAME)"
  s["INFOPLIST_FILE"] = "Partage/Info.plist"
  s["CODE_SIGN_ENTITLEMENTS"] = "Partage/Partage.entitlements"
  s["SWIFT_VERSION"] = "5.0"
  s["TARGETED_DEVICE_FAMILY"] = "1,2"
  # Une extension ne s'installe pas seule : elle voyage dans l'application.
  s["SKIP_INSTALL"] = "YES"
  # L'XCFramework est une bibliothèque **statique** — `crate-type = ["staticlib"]`. Elle se
  # lie, elle ne s'embarque pas ; et comme du Rust compilé tire la bibliothèque standard
  # C++, il faut le dire au lieur. Sans `-lc++`, l'édition de liens échoue sur des symboles
  # `std::__1::` qui ne désignent rien de compréhensible. Relevé dans le project.yml de
  # ghostpass, qui porte la même ligne pour la même raison.
  s["OTHER_LDFLAGS"] = "$(inherited) -lc++"
  s["FRAMEWORK_SEARCH_PATHS"] = ["$(inherited)", "$(PROJECT_DIR)"]
  # **Pas de `SWIFT_INCLUDE_PATHS` vers `ios/Headers`.** C'est le réflexe naturel — les
  # en-têtes UniFFI sont là — et il fait échouer la compilation :
  #
  #   error: redefinition of module 'ghost_crypto_ffiFFI'
  #
  # `xcodebuild -create-xcframework -headers` a déjà copié ces en-têtes **dans**
  # l'XCFramework, que Xcode expose à son tour. Ajouter le dossier source les fait voir
  # deux fois, sous deux chemins, et Clang refuse la seconde définition. `ios/Headers/`
  # n'est qu'un intermédiaire de construction ; le consommateur, c'est l'XCFramework.
  s["ALWAYS_SEARCH_USER_PATHS"] = "NO"
  s["ENABLE_USER_SCRIPT_SANDBOXING"] = "NO"
  s["DEVELOPMENT_TEAM"] = EQUIPE
  s["CODE_SIGN_STYLE"] = "Automatic"
  # Une extension de partage n'a pas d'écran de lancement à elle, et `SLComposeServiceViewController`
  # n'en veut pas. Le laisser vide évite qu'Xcode aille chercher celui de l'application,
  # qui n'est pas dans les sources de cette cible.
  s["INFOPLIST_KEY_UILaunchScreen_Generation"] = "NO"
end

# ─── Les sources ─────────────────────────────────────────────────────────────
groupe = projet.main_group.new_group(CIBLE, "Partage")
sources = Dir[File.join(IOS, "Partage", "*.swift")].sort
abort("Aucune source Swift dans ios/Partage") if sources.empty?

# `Temoins/main.swift` est **exclu** : c'est un exécutable de témoin, avec du code au
# premier niveau. L'embarquer dans l'extension donnerait deux points d'entrée et un échec
# d'édition de liens sans rapport visible avec sa cause.
sources.each do |chemin|
  fichier = groupe.new_reference(chemin)
  partage.source_build_phase.add_file_reference(fichier)
end

# Les liaisons UniFFI, produites par outils/construire-xcframework.sh. Compilées avec
# l'extension, jamais éditées à la main.
liaisons = File.join(IOS, "Generated", "ghost_crypto_ffi.swift")
abort("Liaisons UniFFI absentes — lancez outils/construire-xcframework.sh") unless File.exist?(liaisons)
groupe_genere = projet.main_group.new_group("Generated", "Generated")
partage.source_build_phase.add_file_reference(groupe_genere.new_reference(liaisons))

# Ressources : l'Info.plist et les droits ne sont pas des ressources, ils sont désignés par
# les réglages. Rien à copier ici — et c'est normal, l'extension n'a pas d'image à elle.

# ─── L'XCFramework, lié et non embarqué ──────────────────────────────────────
xcf = File.join(IOS, "GhostbitCrypto.xcframework")
abort("XCFramework absent — lancez outils/construire-xcframework.sh") unless File.exist?(xcf)
reference_xcf = projet.main_group.new_reference(xcf)
partage.frameworks_build_phase.add_file_reference(reference_xcf)

# ─── L'extension voyage dans l'application ───────────────────────────────────
# C'est ainsi qu'iOS la découvre : une extension posée à côté du .app n'existe pas.
runner.add_dependency(partage)
phase = runner.new_copy_files_build_phase("Embed App Extensions")
phase.symbol_dst_subfolder_spec = :plug_ins
fichier = phase.add_file_reference(partage.product_reference)
fichier.settings = { "ATTRIBUTES" => ["RemoveHeadersOnCopy"] }

# La phase d'intégration doit précéder « Thin Binary », qui signe et amincit le paquet :
# copier l'extension après coup la laisserait non signée dans un paquet déjà scellé.
amincissement = runner.build_phases.index { |p| p.respond_to?(:name) && p.name == "Thin Binary" }
if amincissement
  runner.build_phases.delete(phase)
  runner.build_phases.insert(amincissement, phase)
end

# ─── Les droits de l'application ─────────────────────────────────────────────
# Le groupe d'applications et le groupe d'accès au trousseau : les deux seuls canaux par
# lesquels l'extension et l'application se parlent. Sans eux, la feuille de partage ne sait
# pas où poster, et ce qu'elle crée est invisible — donc irrévocable — depuis l'application.
runner.build_configurations.each do |config|
  config.build_settings["CODE_SIGN_ENTITLEMENTS"] = "Runner/Runner.entitlements"
  # Et la même équipe que l'extension. Deux équipes dans un seul paquet ne se signent pas :
  # « Embedded binary's bundle identifier is not prefixed with the parent app's ».
  config.build_settings["DEVELOPMENT_TEAM"] = EQUIPE
end

projet.save
puts "Cible #{CIBLE} câblée dans #{File.basename(PROJET)}"
puts "  sources        : #{sources.map { |c| File.basename(c) }.join(", ")}"
puts "  liaisons       : ghost_crypto_ffi.swift"
puts "  bibliothèque   : GhostbitCrypto.xcframework (liée, non embarquée)"
puts "  groupe partagé : #{GROUPE}"
puts "  équipe         : #{EQUIPE}"
