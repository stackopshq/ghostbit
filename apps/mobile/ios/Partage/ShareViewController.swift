import Social
import UIKit
import UniformTypeIdentifiers

/// La feuille de partage de GhostBit sur iOS.
///
/// ─── Pourquoi ceci est du Swift et non du Flutter ───
///
/// Une Share Extension est un **processus séparé**, au budget mémoire serré : le système la
/// tue sans ménagement quand elle dépasse, et un moteur Flutter n'y tient pas en pratique.
/// C'est la seule raison de cette asymétrie avec Android, où l'intention `ACTION_SEND` peut
/// viser l'activité Flutter et emprunter le même chemin que la création ordinaire.
///
/// L'asymétrie est **dans l'interface, jamais dans la cryptographie**. Ce fichier n'en
/// contient pas une ligne : il appelle `sealSend`, du binding UniFFI, qui appelle
/// `ghost_crypto::partage` — le même code que celui qu'appelle Dart par
/// `flutter_rust_bridge`. Deux générateurs frères au-dessus d'un seul cœur ; ce sont les
/// interfaces qui diffèrent, pas ce qui chiffre.
///
/// ─── Ce que cette feuille ne fait pas ───
///
/// Elle **ne propose aucune option**. Ni mot de passe, ni brûler-après-lecture, ni vues
/// limitées : elle chiffre, elle poste, elle rend un lien. Une feuille de partage est
/// utilisée d'une main en trois secondes ; y empiler le formulaire de l'application en
/// ferait un endroit où l'on se trompe. Les réglages fins appartiennent à l'application,
/// où l'on a le temps de les lire.
final class ShareViewController: SLComposeServiceViewController {
    /// La durée par défaut d'un paste créé depuis la feuille de partage.
    ///
    /// Un défaut est nécessaire — il n'y a pas de formulaire — et « jamais » serait le
    /// mauvais : quelqu'un qui partage vite depuis une feuille système partage
    /// généralement quelque chose de ponctuel, et un secret qui reste en ligne
    /// indéfiniment parce que personne n'a choisi est un défaut qui coûte cher. Une
    /// semaine se révoque, et se remplace par un lien de l'application si besoin.
    private static let expirationParDefaut = 7 * 24 * 3600

    /// L'adresse de l'instance, écrite par l'application dans les préférences partagées.
    ///
    /// Le groupe d'applications est la seule façon pour l'extension de lire ce que
    /// l'application a réglé : les deux processus ne partagent aucun conteneur par défaut.
    private static let groupe = "group.dev.ghostbit"

    override func isContentValid() -> Bool {
        !(contentText ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    override func presentationAnimationDidFinish() {
        // Préremplir avec le texte partagé : sans cela, la feuille s'ouvre vide et
        // l'utilisateur croit que le partage a échoué.
        guard (contentText ?? "").isEmpty else { return }
        Task {
            if let texte = await texteParTage() {
                await MainActor.run {
                    self.textView.text = texte
                    self.validateContent()
                }
            }
        }
    }

    override func didSelectPost() {
        let clair = contentText ?? ""
        Task {
            do {
                let lien = try await creer(clair)
                // Le lien va au presse-papiers : c'est la seule sortie dont dispose une
                // feuille de partage, qui n'a pas d'écran de résultat. Il **contient la
                // clé**, et tout ce qui tourne sur l'appareil peut lire le presse-papiers ;
                // c'est le compromis que fait aussi le bouton « copier » du web.
                UIPasteboard.general.string = lien.absoluteString
                await MainActor.run { self.terminer() }
            } catch {
                await MainActor.run { self.echouer(error) }
            }
        }
    }

    // MARK: - Le chemin qui compte

    private func creer(_ clair: String) async throws -> URL {
        guard
            let defauts = UserDefaults(suiteName: Self.groupe),
            let adresse = defauts.string(forKey: "ghostbit.serveur"),
            let base = URL(string: adresse)
        else {
            throw ClientGhostbit.Echec.adresseAbsente
        }

        // **La seule ligne de cryptographie de toute l'extension, et elle est ailleurs.**
        // `sealSend` tire une clé neuve pour ce seul paste et scelle en AES-256-GCM avec un
        // nonce de douze octets, dans `ghost_crypto::partage`. Rien n'est chiffré ici.
        let scelle = try sealSend(plaintext: clair)

        let cree = try await ClientGhostbit.creer(
            base: base,
            contenu: scelle.ciphertext,
            nonce: scelle.nonce,
            langage: nil,
            expireDansSecondes: Self.expirationParDefaut
        )

        guard
            let lien = Fragment.lien(
                base: base,
                identifiant: cree.identifiant,
                // `sealSend` rend la clé en base64 **standard** ; le fragment de ghostbit
                // la veut en base64url sans remplissage. Voir `Fragment.swift` : cette
                // conversion ne devrait pas exister ici, il manque une façade `ghostbit`
                // au binding UniFFI.
                cleBase64: scelle.key,
                jeton: cree.jetonDeSuppression
            )
        else {
            throw ClientGhostbit.Echec.reseau("Lien impossible à composer.")
        }

        Historique.ajouter(
            identifiant: cree.identifiant,
            lien: lien.absoluteString,
            jeton: cree.jetonDeSuppression,
            octets: clair.utf8.count,
            expireDansSecondes: Self.expirationParDefaut,
            groupe: Self.groupe
        )
        return lien
    }

    /// Récupère le texte de l'élément partagé quand l'hôte ne l'a pas déjà mis dans
    /// `contentText` — un fichier `.txt` déposé depuis Fichiers, par exemple.
    private func texteParTage() async -> String? {
        guard
            let element = (extensionContext?.inputItems as? [NSExtensionItem])?.first,
            let fournisseurs = element.attachments
        else { return nil }

        for fournisseur in fournisseurs
        where fournisseur.hasItemConformingToTypeIdentifier(UTType.text.identifier) {
            if let objet = try? await fournisseur.loadItem(
                forTypeIdentifier: UTType.text.identifier
            ) {
                if let texte = objet as? String { return texte }
                // Un `.txt` arrive comme URL, pas comme chaîne. Ne traiter que le premier
                // cas ferait échouer le partage depuis Fichiers, en silence.
                if let url = objet as? URL,
                   let contenu = try? String(contentsOf: url, encoding: .utf8) {
                    return contenu
                }
            }
        }
        return nil
    }

    // MARK: - Fin

    private func terminer() {
        extensionContext?.completeRequest(returningItems: nil)
    }

    private func echouer(_ erreur: Error) {
        // Une feuille de partage qui se referme sans rien dire laisse croire que le paste
        // a été créé. Ce n'est pas une politesse : c'est la différence entre « c'est
        // partagé » et « votre secret n'est nulle part ».
        let alerte = UIAlertController(
            title: "Le paste n'a pas été créé",
            message: erreur.localizedDescription,
            preferredStyle: .alert
        )
        alerte.addAction(UIAlertAction(title: "Fermer", style: .default) { _ in
            self.extensionContext?.cancelRequest(withError: erreur)
        })
        present(alerte, animated: true)
    }
}
