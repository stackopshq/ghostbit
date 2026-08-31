import Flutter
import UIKit

/// L'hôte iOS de l'application Flutter.
///
/// Il porte une seule chose au-delà du strict nécessaire : le pont qui publie l'adresse de
/// l'instance dans le conteneur du **groupe d'applications**.
///
/// C'est indispensable et facile à manquer. `shared_preferences` écrit dans les préférences
/// propres à l'application ; la feuille de partage est un **processus séparé** qui n'y a
/// aucun accès. Sans ce pont, elle ne saurait pas où poster, et l'échec arriverait au pire
/// moment — chez l'utilisateur, la première fois qu'il partage, avec un message qui ne
/// dirait pas quoi faire.
///
/// L'adresse n'est pas un secret — c'est un nom d'hôte — donc elle passe par les
/// préférences du groupe. L'historique, lui, contient des clés et passe par le trousseau :
/// les deux canaux sont distincts, et la distinction est le point.
@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  /// Le même identifiant que dans `Partage.entitlements`, `Runner.entitlements` et
  /// `ShareViewController.swift`. `outils/verifier-pont-trousseau.sh` compare les copies.
  private static let groupe = "group.dev.ghostbit"
  private static let canal = "dev.ghostbit/groupe"

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    let canal = FlutterMethodChannel(
      name: Self.canal,
      binaryMessenger: engineBridge.applicationBinaryMessenger
    )
    canal.setMethodCallHandler { appel, reponse in
      guard
        appel.method == "publierLeServeur",
        let adresse = appel.arguments as? String
      else {
        reponse(FlutterMethodNotImplemented)
        return
      }
      // Un groupe absent rend `nil` plutôt que de lever : sans ce cas, une signature mal
      // configurée ferait planter l'application au lieu de dégrader la feuille de partage.
      UserDefaults(suiteName: Self.groupe)?.set(adresse, forKey: "ghostbit.serveur")
      reponse(nil)
    }
  }
}
