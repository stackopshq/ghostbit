import Foundation

/// Le client de l'API de ghostbit, réduit à ce dont la feuille de partage a besoin.
///
/// **Il ne chiffre ni ne déchiffre rien.** Il transporte du base64 déjà scellé par le cœur
/// Rust. `POST /api/v1/pastes` n'a aucun champ où loger une clé, et lui en ajouter un
/// serait la fin du modèle.
///
/// Il est délibérément minuscule : une extension de partage iOS est un processus séparé au
/// budget mémoire serré, et ce qu'on n'y charge pas ne peut pas la faire tuer par le
/// système au milieu d'une requête.
enum ClientGhostbit {
    struct PasteCree {
        let identifiant: String
        let jetonDeSuppression: String
    }

    enum Echec: LocalizedError {
        case adresseAbsente
        case reseau(String)
        case refus(Int, String)

        var errorDescription: String? {
            switch self {
            case .adresseAbsente:
                // Le cas qu'on rencontrera pour de vrai : quelqu'un installe l'application
                // et partage avant de l'avoir ouverte une première fois. Dire quoi faire,
                // plutôt que « erreur inconnue ».
                return "Ouvrez GhostBit une fois pour indiquer votre instance."
            case let .reseau(message):
                return message
            case let .refus(code, message):
                return code == 429
                    ? "Cette instance limite le rythme des créations. Réessayez dans une minute."
                    : message
            }
        }
    }

    /// Crée un paste. `contenu` et `nonce` sont du base64 **standard** : le validateur du
    /// serveur décode strictement (`validate=True`) et refuserait du base64url.
    static func creer(
        base: URL,
        contenu: String,
        nonce: String,
        langage: String?,
        expireDansSecondes: Int?
    ) async throws -> PasteCree {
        var requete = URLRequest(url: base.appendingPathComponent("api/v1/pastes"))
        requete.httpMethod = "POST"
        requete.setValue("application/json", forHTTPHeaderField: "Content-Type")

        var corps: [String: Any] = ["content": contenu, "nonce": nonce, "burn": false]
        if let langage { corps["language"] = langage }
        if let expireDansSecondes { corps["expires_in"] = expireDansSecondes }
        requete.httpBody = try JSONSerialization.data(withJSONObject: corps)

        let (donnees, reponse): (Data, URLResponse)
        do {
            (donnees, reponse) = try await URLSession.shared.data(for: requete)
        } catch {
            throw Echec.reseau(error.localizedDescription)
        }

        let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw Echec.refus(code, message(de: donnees, code: code))
        }
        guard
            let objet = try? JSONSerialization.jsonObject(with: donnees) as? [String: Any],
            let identifiant = objet["id"] as? String,
            let jeton = objet["delete_token"] as? String
        else {
            throw Echec.reseau("Réponse inattendue du serveur.")
        }
        return PasteCree(identifiant: identifiant, jetonDeSuppression: jeton)
    }

    /// Extrait le message lisible des deux formes d'erreur du serveur : `detail` en chaîne
    /// pour les erreurs métier, en liste pour une validation refusée. Sans le second cas,
    /// une erreur de validation s'afficherait sous une forme illisible.
    private static func message(de donnees: Data, code: Int) -> String {
        guard let objet = try? JSONSerialization.jsonObject(with: donnees) as? [String: Any]
        else { return "Le serveur a répondu \(code)." }
        if let detail = objet["detail"] as? String { return detail }
        if let liste = objet["detail"] as? [[String: Any]],
           let premier = liste.first, let message = premier["msg"] as? String {
            return message
        }
        return "Le serveur a répondu \(code)."
    }
}
