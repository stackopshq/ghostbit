import Foundation

/// Le témoin du format de fragment côté Swift.
///
/// Il est écrit comme un exécutable et non comme un `XCTestCase` pour une raison
/// pratique : il tourne alors avec `swiftc`, sans projet Xcode, sans simulateur et sans
/// signature. Un témoin qui demande une chaîne d'outils complète est un témoin qu'on ne
/// lance pas, et un témoin qu'on ne lance pas est vert.
///
/// Le fichier s'appelle `main.swift` parce que Swift n'autorise le code au premier niveau
/// que là ; l'y mettre ailleurs ne compile pas.
///
/// Lancer : `outils/temoin-swift.sh`
///
/// ─── Le choix des cas ───
///
/// `Fragment.versBase64URL` fait trois substitutions. Un essai qui prendrait une clé
/// aléatoire de 32 octets ne verrait la disparition de deux d'entre elles qu'une fois sur
/// quatre : c'est la probabilité qu'une telle clé contienne au moins un `+` ou un `/`.
/// Les cas ci-dessous choisissent donc l'octet qui fait diverger, et non l'octet
/// représentatif — c'est la seule façon de savoir que la fonction fait les trois.

var echecs = 0

func verifier(_ condition: Bool, _ quoi: String) {
    if condition {
        print("  ok   \(quoi)")
    } else {
        print("  ÉCHEC \(quoi)")
        echecs += 1
    }
}

func verifierEgal(_ obtenu: String, _ attendu: String, _ quoi: String) {
    if obtenu == attendu {
        print("  ok   \(quoi)")
    } else {
        print("  ÉCHEC \(quoi)\n         attendu : \(attendu)\n         obtenu  : \(obtenu)")
        echecs += 1
    }
}

// ─── Une clé qui distingue vraiment les deux encodages ───────────────────────

/// Trente-deux octets dont le base64 standard contient `+`, `/` **et** un `=` final.
/// Les mêmes octets que ceux du témoin croisé Node et du témoin Rust, pour que les trois
/// parlent du même cas.
let cleQuiDiverge = Data((0..<32).map { [0xfb, 0xff, 0x3e, 0x3f][$0 % 4] as UInt8 })
let standard = cleQuiDiverge.base64EncodedString()

verifier(standard.contains("+"), "la clé d'essai contient un +")
verifier(standard.contains("/"), "la clé d'essai contient un /")
verifier(standard.hasSuffix("="), "la clé d'essai porte un remplissage")

let url = Fragment.versBase64URL(standard)
verifier(!url.contains("+"), "le + devient -")
verifier(!url.contains("/"), "le / devient _")
verifier(!url.contains("="), "le remplissage disparaît")
verifier(url.count == 43, "32 octets font 43 caractères en base64url sans remplissage")

// Et la conversion doit être **réversible** : ce que le navigateur relira, c'est bien la
// même clé. Sans ce cas, une fonction qui supprimerait les `+` au lieu de les remplacer
// passerait les trois essais ci-dessus.
var retour = url.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
while retour.count % 4 != 0 { retour += "=" }
verifier(
    Data(base64Encoded: retour) == cleQuiDiverge,
    "la clé se retrouve à l'identique après aller-retour"
)

// ─── Le lien complet ─────────────────────────────────────────────────────────

let base = URL(string: "https://paste.example.com")!
let lien = Fragment.lien(base: base, identifiant: "aB3kZx9m", cleBase64: standard, jeton: "JETON")

verifier(lien != nil, "le lien se compose")
if let lien {
    let texte = lien.absoluteString
    verifierEgal(texte, "https://paste.example.com/aB3kZx9m#\(url)~JETON", "le lien complet")

    // **La clé est après le `#`, et nulle part ailleurs.** C'est l'invariant du produit :
    // ce qui précède le `#` part au serveur à chaque chargement de page.
    let avantLeDiese = texte.components(separatedBy: "#").first ?? texte
    verifier(!avantLeDiese.contains(url), "la clé n'apparaît pas avant le #")
    verifier(!avantLeDiese.contains("JETON"), "le jeton n'apparaît pas avant le #")

    // Le séparateur doit survivre : `URLComponents.fragment` ré-encode les caractères
    // qu'il juge réservés, et un `~` transformé en `%7E` ferait couper le fragment au
    // mauvais endroit chez le visualiseur — qui cherche un `~` littéral.
    verifier(texte.contains("~"), "le séparateur ~ n'est pas ré-encodé en %7E")
    verifier(!texte.contains("%7E"), "aucun %7E dans le lien")
}

print(echecs == 0 ? "\nTous les témoins Swift passent." : "\n\(echecs) témoin(s) Swift en échec.")
exit(echecs == 0 ? 0 : 1)
