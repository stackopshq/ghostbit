//! Ce que Dart peut appeler du cœur commun — et **rien de plus**.
//!
//! **Aucune cryptographie ici.** Cette façade traduit des types et encode du base64 ;
//! le chiffrement lui-même est celui de `ghost_crypto::partage`, partagé avec les autres
//! produits de la suite. La règle est celle de ghostcal : pas une ligne de crypto hors du
//! cœur, ni en Dart, ni en Swift, ni en Kotlin.
//!
//! ─── Pourquoi le **fragment** est décrit ici et pas côté client ───
//!
//! Ghostbit range sa clé dans le fragment d'une URL, sous une forme qui lui est propre :
//!
//! ```text
//! https://paste.example.com/aB3kZx9m#CLE_B64URL~JETON_DE_SUPPRESSION
//!                                     └──────────────┬────────────┘
//!                                    jamais envoyé au serveur
//! ```
//!
//! Ce n'est pas de la cryptographie, et c'est justement pourquoi il fallait y penser :
//! **un format recopié de chaque côté d'une frontière diverge sans que rien ne le
//! signale.** Le défaut de la journée n'était pas un défaut de chiffrement — les deux
//! côtés chiffraient correctement, chacun dans son format. Le fragment est donc composé
//! et analysé **une seule fois**, ici, et les clients ne font que transporter la chaîne.
//!
//! Deux détails du format se paient cher si on les manque, et ils sont tous deux dans
//! l'encodage plutôt que dans l'algorithme :
//!
//! 1. **la clé s'écrit en base64url sans remplissage** — `-` et `_` là où le base64
//!    standard met `+` et `/`, et pas de `=` final. C'est ce que produit
//!    `crypto.subtle.exportKey` suivi du `_b64url` de `static/e2e.js` ;
//! 2. **le chiffre et le nonce s'écrivent en base64 standard**, parce que ce sont eux qui
//!    partent au serveur, dont le validateur décode en base64 strict.
//!
//! Les deux encodages coexistent dans la même URL. Les confondre ne casse rien tout de
//! suite : sur 32 octets tirés au hasard, environ une clé sur quatre ne contient ni `+`
//! ni `/`, et le test passe. C'est le pire mode de défaillance qui soit, et c'est pour ça
//! que le témoin croisé choisit une clé qui contient les deux.

use base64::engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD};
use base64::Engine as _;
use ghost_crypto::partage;

/// L'erreur telle que Dart la verra.
///
/// Le type d'erreur du cœur ne traverse pas : il porte des variantes qui n'ont de sens
/// qu'en Rust. On rend un message, comme le fait déjà le binding UniFFI — ce qui compte,
/// c'est que l'échec soit un échec, pas qu'il soit typé de l'autre côté.
#[derive(Debug)]
pub struct ErreurDuCoeur {
    pub message: String,
}

impl<E: std::fmt::Display> From<E> for ErreurDuCoeur {
    fn from(erreur: E) -> Self {
        Self {
            message: erreur.to_string(),
        }
    }
}

/// Une enveloppe prête à partir : deux champs pour le serveur, un pour le fragment.
///
/// La séparation est celle de l'API de ghostbit, et elle porte tout le modèle : le serveur
/// reçoit `chiffre` et `nonce`, jamais `cle`. Nommer les trois champs dans un même objet
/// est le seul endroit où ils se touchent, et c'est un objet qu'on lit d'un coup d'œil.
pub struct Enveloppe {
    /// Base64 **standard** — c'est le champ `content` de `POST /api/v1/pastes`.
    pub chiffre: String,
    /// Base64 **standard**, 12 octets une fois décodé — le champ `nonce`.
    pub nonce: String,
    /// Base64**url** sans remplissage — la part gauche du fragment. Ne part jamais au
    /// serveur : la mettre dans le corps d'une requête serait la fin du modèle.
    pub cle: String,
}

/// Ce qu'on retrouve dans un fragment lu depuis une URL reçue.
pub struct Fragment {
    /// Vide pour un paste protégé par mot de passe : la clé s'y dérive, elle ne voyage pas.
    pub cle: String,
    /// Vide pour qui n'est pas le créateur — un lien partagé se coupe avant le `~`.
    pub jeton: String,
}

/// Scelle un contenu sous une clé neuve, tirée pour ce seul paste.
///
/// L'invariant qui rend sûr le nonce de 96 bits d'AES-GCM est **une clé par paste**, et il
/// appartient à `ghost_crypto::partage` : le tirage reste en Rust, aucun client ne produit
/// de matière cryptographique.
pub fn sceller(clair: Vec<u8>) -> Result<Enveloppe, ErreurDuCoeur> {
    let e = partage::sceller(&clair)?;
    Ok(Enveloppe {
        chiffre: STANDARD.encode(&e.chiffre),
        nonce: STANDARD.encode(e.nonce),
        cle: URL_SAFE_NO_PAD.encode(e.cle),
    })
}

// L'édition d'un paste par son propriétaire (`PUT /api/v1/pastes/{id}`) n'est pas ici, et
// son absence est un choix plutôt qu'un oubli. Elle demande de **rechiffrer sous une clé
// déjà connue** — celle du fragment, qui ne peut pas changer sans casser tous les liens
// déjà partagés — et `ghost_crypto::partage` ne sait que sceller sous une clé qu'il tire
// lui-même. L'écrire ici, c'est-à-dire hors du cœur, serait exactement la divergence que
// ce module existe pour empêcher. Il manque au cœur un `partage::sceller_avec(cle, clair)`.

/// Ouvre ce que le serveur a rendu. Rend des **octets** et non une chaîne : un paste peut
/// avoir été gzippé avant chiffrement (`compressed: true`), auquel cas ce qui sort n'est
/// pas encore du texte. Forcer l'UTF-8 ici rendrait ces pastes-là impossibles à lire.
pub fn ouvrir(cle: String, nonce: String, chiffre: String) -> Result<Vec<u8>, ErreurDuCoeur> {
    let cle = decoder_cle(&cle)?;
    Ok(partage::ouvrir(
        &cle,
        &decoder_souple(&nonce)?,
        &decoder_souple(&chiffre)?,
    )?)
}

/// Compose le fragment d'une URL de paste : `CLE~JETON`, ou `~JETON` sans clé.
///
/// La forme sans clé n'est pas un cas dégradé, c'est celle des pastes protégés par mot de
/// passe : la clé se dérive chez le lecteur et n'a rien à faire dans le lien.
pub fn composer_fragment(cle: String, jeton: String) -> String {
    format!("{cle}~{jeton}")
}

/// Analyse le fragment d'une URL reçue.
///
/// Trois formes existent dans la nature et il faut les rendre toutes les trois, sans quoi
/// on refuse des liens parfaitement valides :
///
/// - `CLE~JETON` — ce que voit le créateur, juste après création ;
/// - `~JETON` — un paste protégé par mot de passe, vu par son créateur ;
/// - `CLE` — un lien partagé, dont on a retiré le jeton avant de l'envoyer.
///
/// Le séparateur est cherché à la **première** occurrence : un jeton
/// (`secrets.token_urlsafe`) ne contient jamais de `~`, mais couper à la dernière ferait
/// dépendre le résultat d'une hypothèse qu'on ne contrôle pas.
pub fn analyser_fragment(fragment: String) -> Fragment {
    let brut = fragment.trim().trim_start_matches('#');
    match brut.find('~') {
        Some(i) => Fragment {
            cle: brut[..i].to_string(),
            jeton: brut[i + 1..].to_string(),
        },
        None => Fragment {
            cle: brut.to_string(),
            jeton: String::new(),
        },
    }
}

// ─── Encodage ────────────────────────────────────────────────────────────────

/// Décode une clé de 32 octets écrite en base64url sans remplissage, **ou** en base64
/// standard.
///
/// Accepter les deux ne coûte rien et évite un échec qui désigne le mauvais coupable : une
/// clé parfaitement valide, refusée pour un tiret. Le binding UniFFI de la suite fait le
/// même choix, pour la même raison — et son commentaire dit que l'avoir manqué a coûté un
/// diagnostic.
fn decoder_cle(cle: &str) -> Result<[u8; 32], ErreurDuCoeur> {
    let octets = decoder_souple(cle)?;
    octets.try_into().map_err(|_| ErreurDuCoeur {
        message: "la clé ne fait pas 32 octets une fois décodée".to_string(),
    })
}

/// Décode du base64 standard ou base64url, avec ou sans remplissage.
fn decoder_souple(entree: &str) -> Result<Vec<u8>, ErreurDuCoeur> {
    let mut s: String = entree.trim().replace('-', "+").replace('_', "/");
    while s.len() % 4 != 0 {
        s.push('=');
    }
    Ok(STANDARD.decode(s)?)
}
