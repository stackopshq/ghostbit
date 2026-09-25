import Flutter
import UIKit

/// La scène de l'application, et le seul endroit où un lien universel arrive.
///
/// ─── Pourquoi ici, et pas dans `AppDelegate` ───
///
/// La documentation d'Apple sur les liens universels, et la quasi-totalité de ce qui
/// s'écrit à leur sujet, montre `application(_:continueUserActivity:restorationHandler:)`
/// sur le délégué d'application. Cette méthode **n'est jamais appelée** dès lors que
/// l'application adopte le cycle de vie `UIScene` — ce que fait celle-ci, par
/// `UIApplicationSceneManifest` dans `Info.plist`. UIKit remet alors l'activité à la
/// scène, et à elle seule.
///
/// C'est le genre d'erreur qui ne produit aucun symptôme distinctif : le fichier
/// d'association est bon, les droits sont bons, le lien ouvre bien l'application — qui
/// s'ouvre sur son écran d'accueil, exactement comme si l'utilisateur avait touché son
/// icône. Rien à lire nulle part.
class SceneDelegate: FlutterSceneDelegate {

  /// L'application était fermée : l'activité arrive dans les options de connexion.
  ///
  /// `FlutterSceneDelegate` fait ici le câblage du moteur Flutter, donc `super` d'abord.
  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)
    for activite in connectionOptions.userActivities {
      if transmettre(activite) { break }
    }
  }

  /// L'application tournait déjà : l'activité arrive par cette voie.
  override func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    if !transmettre(userActivity) {
      super.scene(scene, continue: userActivity)
    }
  }

  /// Remet l'URL d'un lien universel au pont, et dit si c'en était un.
  ///
  /// `absoluteString` et non `path` : **la clé de déchiffrement vit dans le fragment**,
  /// après le `#`. Reconstruire l'adresse depuis ses morceaux est le moyen le plus sûr de
  /// le perdre en route, et un fragment perdu ne se voit qu'au bout de la chaîne, sur un
  /// écran qui dit « cette clé n'ouvre pas » en accusant la mauvaise chose.
  private func transmettre(_ activite: NSUserActivity) -> Bool {
    guard
      activite.activityType == NSUserActivityTypeBrowsingWeb,
      let url = activite.webpageURL
    else { return false }
    PontDeLien.partage.remettre(url.absoluteString)
    return true
  }
}
