import UIKit

/// L'hôte du témoin de la feuille de partage. **Il ne part pas en production.**
///
/// ─── Pourquoi une application de plus ───
///
/// La question à laquelle il faut répondre est « GhostBit apparaît-il dans la feuille de
/// partage d'iOS, et reçoit-il vraiment le contenu ? ». Cette question ne se répond pas en
/// relisant le projet Xcode : une cible peut être câblée, compilée, signée, embarquée dans
/// le paquet, enregistrée auprès de `pluginkit` — tout cela a été vérifié — et ne jamais
/// s'afficher. Il faut ouvrir la feuille.
///
/// L'ouvrir depuis Safari ou Notes marcherait, au prix d'une dépendance à la disposition
/// interne d'applications d'Apple qui change à chaque version majeure, et qui ferait
/// rougir le témoin pour une raison sans rapport avec GhostBit. Ici, l'hôte tient en un
/// bouton : ce qui casse dans ce témoin ne peut être que la feuille de partage.
///
/// La feuille présentée est la **vraie** feuille du système. `UIActivityViewController`
/// n'est pas une imitation : c'est l'objet qu'appelle n'importe quelle application, et
/// c'est le système qui y place les extensions qu'il a enregistrées.
@main
final class HoteDePartage: UIResponder, UIApplicationDelegate {
    /// Le texte témoin. Il n'a pas le droit d'être anodin.
    ///
    /// « test » se retrouverait à l'identique dans vingt endroits de la feuille et d'iOS,
    /// et une assertion qui le cherche passerait même si rien n'était transmis. Cette
    /// chaîne-ci n'existe nulle part ailleurs sur l'appareil : la trouver dans la zone de
    /// rédaction de l'extension **prouve** qu'elle a fait le trajet.
    static let texte = "ghostbit-temoin-7f3a2b9e — ceci a traversé la feuille de partage"

    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let racine = Racine()
        let fenetre = UIWindow(frame: UIScreen.main.bounds)
        fenetre.rootViewController = racine
        fenetre.makeKeyAndVisible()
        window = fenetre
        return true
    }
}

final class Racine: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground

        let bouton = UIButton(type: .system)
        bouton.setTitle("Partager le texte témoin", for: .normal)
        // L'identifiant, et non le titre, est ce que le témoin cherche : un titre est de
        // l'interface, il se traduit et se réécrit ; un identifiant est un contrat.
        bouton.accessibilityIdentifier = "partager"
        bouton.addTarget(self, action: #selector(partager), for: .touchUpInside)
        bouton.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(bouton)
        NSLayoutConstraint.activate([
            bouton.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            bouton.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
    }

    @objc private func partager() {
        let feuille = UIActivityViewController(
            activityItems: [HoteDePartage.texte], applicationActivities: nil
        )
        feuille.popoverPresentationController?.sourceView = view
        present(feuille, animated: true)
    }
}
