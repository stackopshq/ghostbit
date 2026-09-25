import Flutter
import UIKit

/// Le pont par lequel un **lien universel** atteint Dart.
///
/// ─── Pourquoi un canal, et non le routage de liens profonds de Flutter ───
///
/// Flutter sait recevoir un lien universel tout seul, à condition que l'application soit
/// bâtie autour d'un `Router`. Celle-ci ne l'est pas : `MaterialApp` y a un `home:` et pas
/// de table de routes, donc la route initiale que Flutter pousserait — « /abc123#clé » —
/// ne correspondrait à rien et retomberait sur l'écran d'accueil. L'application s'ouvrirait
/// sans le paste, ce qui est très exactement la panne que les liens universels étaient
/// censés supprimer, déplacée d'un cran.
///
/// Ce canal est en revanche celui que le partage Android emprunte déjà
/// (`MainActivity.kt`), et il aboutit au même endroit côté Dart. Les deux plateformes
/// remettent donc leurs liens par le même chemin.
///
/// ─── Les deux moments, comme côté Android ───
///
/// 1. **L'application était fermée.** La scène se connecte avec l'activité en main, avant
///    que Dart n'ait posé son écouteur : le lien est mis de côté, et Dart vient le
///    chercher par `lienInitial`.
/// 2. **L'application tournait.** `scene(_:continueUserActivity:)` le remet, et Dart
///    écoute déjà : on pousse.
///
/// Ne traiter que le second cas donnerait le défaut le plus déroutant qui soit — le lien
/// marche, sauf la première fois.
final class PontDeLien {
  static let partage = PontDeLien()

  static let nomDuCanal = "dev.ghostbit/partage"

  private var canal: FlutterMethodChannel?
  /// Le lien arrivé avant que Dart ne puisse écouter. Consommé une fois, puis oublié.
  private var enAttente: String?
  /// Dart a-t-il déjà réclamé `lienInitial` ? Tant qu'il ne l'a pas fait, `invokeMethod`
  /// partirait vers un gestionnaire qui n'existe pas encore et serait perdu sans un mot.
  private var dartEcoute = false

  func brancher(_ messager: FlutterBinaryMessenger) {
    let c = FlutterMethodChannel(name: Self.nomDuCanal, binaryMessenger: messager)
    c.setMethodCallHandler { [weak self] appel, reponse in
      guard let self else { return reponse(nil) }
      switch appel.method {
      case "lienInitial":
        self.dartEcoute = true
        // Rendu une seule fois : sans cela, revenir sur l'application rouvrirait
        // indéfiniment le même paste — et rouvrir consomme une vue.
        reponse(self.enAttente)
        self.enAttente = nil
      case "partageInitial":
        // iOS remet le texte partagé par l'extension de partage, pas par ce canal.
        // Répondre `nil` plutôt que `notImplemented` évite au Dart de traverser un
        // `catchError` à chaque démarrage pour un cas parfaitement normal.
        reponse(nil)
      default:
        reponse(FlutterMethodNotImplemented)
      }
    }
    canal = c
    // Un lien reçu avant le branchement du canal reste en attente : `lienInitial` le
    // trouvera. Rien à pousser ici.
  }

  func remettre(_ lien: String) {
    guard let c = canal, dartEcoute else {
      enAttente = lien
      return
    }
    c.invokeMethod("lien", arguments: lien)
  }
}

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

    // Le messager vient de l'`applicationRegistrar`, et non du `pluginRegistry`.
    //
    // Le bridge expose les deux, et c'est le second qui saute aux yeux puisque la ligne
    // au-dessus s'en sert. Mais `pluginRegistry` ne fabrique que des registrars *de
    // greffon* ; le messager de niveau application est sur `applicationRegistrar`, dont
    // c'est justement la raison d'être. Compilé avant d'être écrit ici : la première
    // version ne l'était pas et n'a pas survécu à `flutter build ios`.
    let canal = FlutterMethodChannel(
      name: Self.canal,
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    // Le canal des liens universels partage ce messager. Il est branché ici parce que
    // c'est le seul endroit où le messager de niveau application existe : le
    // `SceneDelegate`, qui reçoit les liens, n'y a pas accès.
    PontDeLien.partage.brancher(engineBridge.applicationRegistrar.messenger())

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
