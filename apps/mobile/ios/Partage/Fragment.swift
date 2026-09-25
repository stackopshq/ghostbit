import Foundation

/// Le format de fragment de GhostBit, côté Swift.
///
/// ─── Ce fichier est un compromis, et il faut le savoir en le lisant ───
///
/// La règle de la suite est qu'un format de fil s'écrit **une seule fois**, dans le cœur
/// Rust, et que les clients ne font que transporter des chaînes. C'est ce que fait
/// l'application Flutter : `rust/src/api/coeur.rs` compose et analyse le fragment, et Dart
/// n'en sait rien.
///
/// L'extension de partage ne peut pas en faire autant aujourd'hui, pour une raison
/// précise. Elle passe par UniFFI, dont la façade `vault` expose `sealSend(plaintext:)` —
/// et cette fonction rend la clé en **base64 standard**, parce qu'elle a été écrite pour
/// ghostpass, dont les partages n'ont pas le format de ghostbit. Or le fragment de
/// ghostbit veut du **base64url sans remplissage** : `-` et `_` là où le standard met `+`
/// et `/`, et pas de `=` final.
///
/// Il manque donc au binding UniFFI une façade `ghostbit` qui rendrait le fragment déjà
/// composé. Tant qu'elle n'existe pas, la conversion est ici — isolée dans un seul fichier
/// plutôt que dispersée, et éprouvée par `PartageTests.swift`.
///
/// **Ce n'est pas de la cryptographie** : pas un octet n'est chiffré, dérivé ou tiré au
/// hasard dans ce fichier. C'est de l'encodage. Mais c'est de l'encodage qui décide si un
/// paste s'ouvre, et le défaut de la journée n'était pas non plus un défaut de
/// chiffrement — les deux côtés chiffraient correctement, chacun dans son format.
enum Fragment {
    /// Le séparateur entre la clé et le jeton de suppression, tel que `static/index.js`
    /// l'écrit et que `static/paste.js` le relit.
    static let separateur: Character = "~"

    /// Ramène du base64 standard vers le base64url sans remplissage.
    ///
    /// Les trois substitutions comptent, et l'oubli d'une seule ne se voit pas toujours :
    /// sur 32 octets tirés au hasard, une clé sur quatre environ ne contient ni `+` ni `/`.
    /// Un essai qui prendrait une clé au hasard serait donc vert trois fois sur quatre
    /// dans un monde où cette fonction est fausse. Le `=` final, lui, est toujours là sur
    /// une clé de 32 octets, et c'est le seul des trois qu'un essai naïf attraperait.
    static func versBase64URL(_ standard: String) -> String {
        standard
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    /// Compose le lien complet d'un paste : `https://hôte/id#CLÉ~JETON`.
    ///
    /// La clé n'apparaît qu'après le `#`. La poser ailleurs — dans le chemin, dans une
    /// requête — la ferait partir au serveur au prochain chargement, et ce serait la fin du
    /// modèle. C'est la seule ligne de ce fichier qui mérite une relecture attentive.
    static func lien(base: URL, identifiant: String, cleBase64: String, jeton: String) -> URL? {
        let cle = versBase64URL(cleBase64)
        var composants = URLComponents(url: base, resolvingAgainstBaseURL: false)
        composants?.path = "/\(identifiant)"
        composants?.fragment = "\(cle)\(separateur)\(jeton)"
        return composants?.url
    }
}
