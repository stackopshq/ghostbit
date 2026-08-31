import Foundation
import Security

/// L'historique, écrit depuis la feuille de partage.
///
/// ─── Pourquoi l'extension écrit dans le même trousseau que l'application ───
///
/// Un paste créé depuis la feuille de partage porte une clé et un jeton de suppression
/// dont le serveur n'a **aucune copie**. S'ils restaient dans l'extension, ce paste serait
/// invisible et irrévocable depuis l'application : on pourrait le créer et jamais le
/// reprendre. Les deux processus partagent donc un groupe d'accès au trousseau.
///
/// ─── Le format n'est pas choisi ici, il est imposé ───
///
/// L'application Flutter lit cet historique par `flutter_secure_storage`. Pour qu'elle le
/// retrouve, l'élément doit porter **exactement** les attributs que ce paquet emploie :
/// un `kSecClassGenericPassword`, `kSecAttrAccount` égal au nom de la clé, `kSecAttrService`
/// égal à `flutter_secure_storage_service`, et le groupe d'accès. Un seul attribut qui
/// diffère ne produit pas d'erreur : l'écriture réussit, et l'application ne voit
/// simplement rien — le pire des deux mondes.
///
/// C'est une dépendance à un détail d'implémentation d'un paquet tiers, et il faut la
/// nommer comme telle : une montée de version de `flutter_secure_storage` qui changerait
/// ces attributs casserait ce pont **en silence**. `outils/verifier-pont-trousseau.sh`
/// relit ces constantes dans le paquet installé et échoue si elles ont bougé.
///
/// Aucune cryptographie ici non plus : c'est le trousseau qui chiffre, et c'est
/// précisément la frontière que le cœur commun laisse à la plateforme.
enum Historique {
    /// Le nom de la clé, partagé avec `lib/services/historique.dart`.
    private static let cle = "ghostbit.historique.v1"

    /// `AppleOptions.defaultAccountName` de `flutter_secure_storage`. Voir l'avertissement
    /// ci-dessus : ce n'est pas une valeur qu'on choisit.
    private static let service = "flutter_secure_storage_service"

    static func ajouter(
        identifiant: String,
        lien: String,
        jeton: String,
        octets: Int,
        expireDansSecondes: Int,
        groupe: String
    ) {
        let maintenant = Date()
        let formateur = ISO8601DateFormatter()
        let entree: [String: Any] = [
            "id": identifiant,
            "lien": lien,
            "jeton": jeton,
            "cree": formateur.string(from: maintenant),
            "langage": NSNull(),
            "expire": formateur.string(
                from: maintenant.addingTimeInterval(TimeInterval(expireDansSecondes))
            ),
            "brule": false,
            "vuesMax": NSNull(),
            "octets": octets,
            "revoque": false,
        ]

        // Relire, ajouter en tête, réécrire. La liste est courte et l'opération est rare :
        // la simplicité vaut mieux ici qu'un format incrémental que Dart devrait aussi
        // savoir lire.
        var liste = lire(groupe: groupe)
        liste.removeAll { ($0["id"] as? String) == identifiant }
        liste.insert(entree, at: 0)
        ecrire(liste, groupe: groupe)
    }

    private static func lire(groupe: String) -> [[String: Any]] {
        var requete = baseRequete(groupe: groupe)
        requete[kSecReturnData] = true
        requete[kSecMatchLimit] = kSecMatchLimitOne

        var resultat: AnyObject?
        guard
            SecItemCopyMatching(requete as CFDictionary, &resultat) == errSecSuccess,
            let donnees = resultat as? Data,
            let texte = String(data: donnees, encoding: .utf8),
            let objet = try? JSONSerialization.jsonObject(with: Data(texte.utf8)),
            let liste = objet as? [[String: Any]]
        else {
            // Rien, ou illisible. On rend vide **sans** effacer : une version ultérieure
            // pourrait encore récupérer l'octet, et l'écraser ici perdrait des clés que
            // personne ne peut redonner.
            return []
        }
        return liste
    }

    private static func ecrire(_ liste: [[String: Any]], groupe: String) {
        guard
            let donnees = try? JSONSerialization.data(withJSONObject: liste),
            let texte = String(data: donnees, encoding: .utf8)
        else { return }

        let requete = baseRequete(groupe: groupe)
        let valeur = Data(texte.utf8)

        let miseAJour = SecItemUpdate(
            requete as CFDictionary,
            [kSecValueData: valeur] as CFDictionary
        )
        if miseAJour == errSecItemNotFound {
            var creation = requete
            creation[kSecValueData] = valeur
            // `AfterFirstUnlock` et non `WhenUnlocked` : une feuille de partage peut
            // s'ouvrir écran verrouillé, et l'écriture échouerait alors — on aurait créé
            // le paste sans jamais garder son jeton.
            creation[kSecAttrAccessible] = kSecAttrAccessibleAfterFirstUnlock
            SecItemAdd(creation as CFDictionary, nil)
        }
    }

    private static func baseRequete(groupe: String) -> [CFString: Any] {
        [
            kSecClass: kSecClassGenericPassword,
            kSecAttrAccount: cle,
            kSecAttrService: service,
            kSecAttrAccessGroup: groupe,
        ]
    }
}
