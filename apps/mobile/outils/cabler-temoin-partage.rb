#!/usr/bin/env ruby
# Câble le témoin de la feuille de partage : un hôte minimal et un essai d'interface.
#
#   outils/temoin-feuille-de-partage.sh
#
# ─── Pourquoi c'est un second script ───
#
# `cabler-extension-ios.rb` câble le produit ; celui-ci câble ce qui le regarde. Les
# mélanger ferait embarquer les cibles de témoin dans tout ce qui construit l'application,
# et rendrait la lecture du premier plus difficile pour la seule raison que le second existe.
#
# Comme son voisin, il est **idempotent** : il défait puis refait.
#
# ─── Deux cibles, pas une ───
#
# `HoteDePartage` est une application UIKit d'un seul bouton, qui présente la vraie feuille
# du système. `TemoinPartage` est un `ui_test_bundle` qui la pilote. Un essai d'interface ne
# peut pas piloter son propre processus : il lui faut une application à conduire, et cette
# application doit être à nous pour que ce qui casse dans le témoin soit imputable à
# GhostBit, et non à la disposition interne de Safari cette année.

require "xcodeproj"

IOS = File.expand_path("../ios", __dir__)
PROJET = File.join(IOS, "Runner.xcodeproj")
HOTE = "HoteDePartage"
TEMOIN = "TemoinPartage"
EQUIPE = ENV.fetch("EQUIPE_GHOSTBIT", "9WHCJ5W7S6")

projet = Xcodeproj::Project.open(PROJET)
runner = projet.targets.find { |t| t.name == "Runner" } or abort("Cible Runner introuvable")
cible_deploiement =
  runner.build_configuration_list.build_settings("Release")["IPHONEOS_DEPLOYMENT_TARGET"] || "15.0"

# ─── Idempotence ─────────────────────────────────────────────────────────────
[HOTE, TEMOIN].each do |nom|
  projet.targets.select { |t| t.name == nom }.each(&:remove_from_project)
  projet.main_group.children.select { |g| g.respond_to?(:name) && g.name == nom }
        .each(&:remove_from_project)
end

# ─── L'hôte ──────────────────────────────────────────────────────────────────
hote = projet.new_target(:application, HOTE, :ios, cible_deploiement)
groupe_hote = projet.main_group.new_group(HOTE, HOTE)
hote.source_build_phase.add_file_reference(
  groupe_hote.new_reference(File.join(IOS, HOTE, "#{HOTE}.swift"))
)
hote.build_configurations.each do |config|
  s = config.build_settings
  # **Pas** un identifiant sous `dev.ghostbit.ghostbit.` : un paquet ainsi préfixé serait
  # pris pour une extension de GhostBit et devrait voyager dans son paquet. C'est une
  # application séparée, et son identifiant le dit.
  s["PRODUCT_BUNDLE_IDENTIFIER"] = "dev.ghostbit.hote-temoin"
  s["PRODUCT_NAME"] = "$(TARGET_NAME)"
  s["INFOPLIST_FILE"] = "#{HOTE}/Info.plist"
  s["SWIFT_VERSION"] = "5.0"
  s["TARGETED_DEVICE_FAMILY"] = "1,2"
  s["GENERATE_INFOPLIST_FILE"] = "NO"
  s["DEVELOPMENT_TEAM"] = EQUIPE
  s["CODE_SIGN_STYLE"] = "Automatic"
  # Il ne s'installe pas : il ne sert qu'au simulateur, où la signature est ad hoc.
  s["SKIP_INSTALL"] = "YES"
end

# ─── Le témoin ───────────────────────────────────────────────────────────────
temoin = projet.new_target(:ui_test_bundle, TEMOIN, :ios, cible_deploiement)
groupe_temoin = projet.main_group.new_group(TEMOIN, TEMOIN)
temoin.source_build_phase.add_file_reference(
  groupe_temoin.new_reference(File.join(IOS, TEMOIN, "#{TEMOIN}.swift"))
)
temoin.build_configurations.each do |config|
  s = config.build_settings
  s["PRODUCT_BUNDLE_IDENTIFIER"] = "dev.ghostbit.temoin-partage"
  s["PRODUCT_NAME"] = "$(TARGET_NAME)"
  s["SWIFT_VERSION"] = "5.0"
  s["TARGETED_DEVICE_FAMILY"] = "1,2"
  s["GENERATE_INFOPLIST_FILE"] = "YES"
  s["DEVELOPMENT_TEAM"] = EQUIPE
  s["CODE_SIGN_STYLE"] = "Automatic"
  # `TEST_TARGET_NAME` désigne l'application que le témoin **conduit**. Sans lui,
  # `xcodebuild` construit le paquet d'essai et ne lance rien à piloter.
  s["TEST_TARGET_NAME"] = HOTE
end
temoin.add_dependency(hote)
# Et de Runner : c'est lui qui porte l'extension. Sans cette dépendance, le témoin peut
# tourner contre une extension qui n'a jamais été reconstruite, et rougir — ou pire,
# verdir — sur la version d'avant.
temoin.add_dependency(runner)

# ─── Le schéma ───────────────────────────────────────────────────────────────
# Partagé, donc versionné : un schéma personnel vit sous `xcuserdata`, que ce dépôt ignore,
# et la commande d'en face ne marcherait que sur la machine qui l'a créé.
schema = Xcodeproj::XCScheme.new
schema.add_build_target(runner)
schema.add_build_target(hote)
schema.add_test_target(temoin)
schema.set_launch_target(hote)

# La pré-action que porte le schéma Runner, reprise telle quelle.
#
# Sans elle, la compilation échoue sur `unable to resolve module dependency: 'Flutter'` —
# et c'est un piège, parce que l'erreur désigne des greffons tiers et donne l'impression
# d'un problème de dépendances. `xcode_backend.sh prepare` est ce qui met Flutter.framework
# à l'endroit où les greffons le cherchent ; un schéma écrit à la main ne l'a pas, et
# aucune des cibles de ce schéma ne peut alors se construire.
#
# `action_content` fabrique un élément **détaché** : le poser ne suffit pas, il faut
# l'accrocher. Sans `add_element`, le schéma s'écrit avec un `<ExecutionAction/>` vide et
# la pré-action ne fait rien — en silence, ce qui est la pire façon de ne rien faire.
prepare = Xcodeproj::XCScheme::ExecutionAction.new(nil, :shell_script)
contenu = prepare.action_content
contenu.title = "Run Prepare Flutter Framework Script"
contenu.script_text = %(/bin/sh "$FLUTTER_ROOT/packages/flutter_tools/bin/xcode_backend.sh" prepare\n)
# `EnvironmentBuildable` va **dans** l'`ActionContent` : c'est de lui que le script tire
# `$FLUTTER_ROOT` et le reste des réglages de compilation. Accroché un niveau plus haut,
# il est accepté et ignoré.
environnement = contenu.xml_element.add_element("EnvironmentBuildable")
environnement.add_element(Xcodeproj::XCScheme::BuildableReference.new(runner).xml_element)
prepare.xml_element.add_element(contenu.xml_element)
schema.build_action.add_pre_action(prepare)

schema.save_as(PROJET, TEMOIN, true)

projet.save
puts "Témoin #{TEMOIN} câblé, avec son hôte #{HOTE} et un schéma partagé."
