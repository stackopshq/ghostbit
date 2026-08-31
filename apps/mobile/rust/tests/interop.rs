//! L'interopérabilité avec le navigateur, éprouvée sans réseau.
//!
//! `temoins/croise.mjs` est le témoin qui compte : il fait tourner le vrai `e2e.js` sur la
//! vraie WebCrypto, contre le vrai relais. Il demande donc Node et un serveur.
//!
//! Ce fichier-ci est la **barrière rapide** : il refait le croisement avec la primitive
//! AES-256-GCM prise directement, sans passer par `ghost_crypto::partage`. Si `partage`
//! devenait faux, se comparer à lui-même ne le dirait pas ; se comparer à `aes-gcm` tel
//! qu'un tiers l'appelle, si.
//!
//! Ce qu'il ne remplace pas : le validateur base64 strict du relais, et le découpage du
//! fragment par `paste.js`. Ces deux-là ne se voient que dans le témoin croisé complet.

use aes_gcm::aead::Aead;
use aes_gcm::{Aes256Gcm, Key, KeyInit, Nonce};
use base64::engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD};
use base64::Engine as _;

use rust_lib_ghostbit::api::coeur;

/// Ce que fait `crypto.subtle.encrypt({name:"AES-GCM", iv}, …)` dans un navigateur :
/// AES-256-GCM, vecteur d'initialisation de 12 octets, étiquette concaténée au chiffre.
fn comme_le_navigateur(cle: &[u8; 32], iv: &[u8; 12], clair: &[u8]) -> Vec<u8> {
    Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(cle))
        .encrypt(Nonce::from_slice(iv), clair)
        .expect("le chiffrement de référence ne doit pas échouer")
}

/// Une clé dont le base64 standard contient `+`, `/` **et** un `=` de remplissage, et dont
/// le base64url diffère donc caractère par caractère.
///
/// Sur 32 octets tirés au hasard, une clé sur quatre environ ne contient ni `+` ni `/` :
/// un témoin qui prendrait une clé aléatoire serait vert trois fois sur quatre dans un
/// monde où l'encodage du fragment est faux. On choisit donc l'octet qui fait diverger.
const CLE_QUI_DIVERGE: [u8; 32] = [
    0xfb, 0xff, 0x3e, 0x3f, 0xfb, 0xff, 0x3e, 0x3f, 0xfb, 0xff, 0x3e, 0x3f, 0xfb, 0xff, 0x3e,
    0x3f, 0xfb, 0xff, 0x3e, 0x3f, 0xfb, 0xff, 0x3e, 0x3f, 0xfb, 0xff, 0x3e, 0x3f, 0xfb, 0xff,
    0x3e, 0x3f,
];

#[test]
fn le_coeur_ouvre_ce_que_le_navigateur_scelle() {
    let cle = [7u8; 32];
    let iv = [3u8; 12];
    let chiffre = comme_le_navigateur(&cle, &iv, b"un secret venu du web");

    let clair = coeur::ouvrir(
        URL_SAFE_NO_PAD.encode(cle),
        STANDARD.encode(iv),
        STANDARD.encode(&chiffre),
    )
    .expect("un paste du navigateur doit s'ouvrir");
    assert_eq!(clair, b"un secret venu du web");
}

#[test]
fn le_navigateur_ouvrirait_ce_que_le_coeur_scelle() {
    let e = coeur::sceller(b"un secret venu du mobile".to_vec()).unwrap();
    // La clé du fragment est en base64url ; le navigateur la ramène en standard avant de
    // décoder, et on fait pareil ici pour la rendre à la primitive.
    let cle: [u8; 32] = URL_SAFE_NO_PAD.decode(&e.cle).unwrap().try_into().unwrap();
    let iv: [u8; 12] = STANDARD.decode(&e.nonce).unwrap().try_into().unwrap();
    let chiffre = STANDARD.decode(&e.chiffre).unwrap();

    // On déchiffre avec la même primitive que WebCrypto, sans passer par notre code : si
    // ceci passe, le navigateur passera aussi.
    let clair = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(&cle))
        .decrypt(Nonce::from_slice(&iv), chiffre.as_slice())
        .expect("le navigateur doit pouvoir ouvrir ce que le mobile scelle");
    assert_eq!(clair, b"un secret venu du mobile");
}

#[test]
fn la_cle_du_fragment_est_en_base64url_sans_remplissage() {
    // La mutation qu'on veut voir échouer : émettre du base64 standard dans le fragment.
    // Elle ne casse aucun aller-retour — les deux décodeurs, le nôtre et celui d'`e2e.js`,
    // sont tolérants — donc seul un témoin qui regarde la **forme** la voit.
    for _ in 0..64 {
        let e = coeur::sceller(b"x".to_vec()).unwrap();
        assert!(
            !e.cle.contains('+') && !e.cle.contains('/') && !e.cle.contains('='),
            "clé du fragment en base64 standard : {}",
            e.cle
        );
        assert_eq!(e.cle.len(), 43, "32 octets en base64url sans remplissage");
    }
}

#[test]
fn le_chiffre_et_le_nonce_sont_en_base64_standard() {
    // Le validateur du relais est `base64.b64decode(v, validate=True)` : un seul `-` ou
    // `_` le fait répondre 422. Le fragment et le corps de la requête n'ont donc pas le
    // même encodage, dans la même URL.
    for _ in 0..64 {
        let e = coeur::sceller(b"x".to_vec()).unwrap();
        for (nom, valeur) in [("chiffre", &e.chiffre), ("nonce", &e.nonce)] {
            assert!(
                !valeur.contains('-') && !valeur.contains('_'),
                "{nom} en base64url : le relais le refusera ({valeur})"
            );
        }
        // Douze octets, et pas les vingt-quatre du scellement de coffre — c'est cette
        // confusion-là qui avait rendu la création impossible depuis mobile.
        assert_eq!(STANDARD.decode(&e.nonce).unwrap().len(), 12);
    }
}

#[test]
fn une_cle_qui_distingue_les_deux_base64_fait_l_aller_retour() {
    let iv = [9u8; 12];
    let chiffre = comme_le_navigateur(&CLE_QUI_DIVERGE, &iv, b"format");

    let standard = STANDARD.encode(CLE_QUI_DIVERGE);
    let url = URL_SAFE_NO_PAD.encode(CLE_QUI_DIVERGE);
    assert_ne!(standard, url, "la clé choisie ne distingue pas les deux base64");
    assert!(standard.contains('+') && standard.contains('/') && standard.contains('='));

    // Les deux formes doivent s'ouvrir : un lien passé par un outil qui ré-encode ne doit
    // pas échouer sur « Invalid padding », un message qui accuse le format et laisse
    // croire à une clé corrompue.
    for forme in [&standard, &url] {
        assert_eq!(
            coeur::ouvrir(forme.clone(), STANDARD.encode(iv), STANDARD.encode(&chiffre)).unwrap(),
            b"format"
        );
    }
}

#[test]
fn le_fragment_se_compose_et_se_relit() {
    let f = coeur::analyser_fragment(coeur::composer_fragment(
        "LA_CLE".to_string(),
        "LE_JETON".to_string(),
    ));
    assert_eq!((f.cle.as_str(), f.jeton.as_str()), ("LA_CLE", "LE_JETON"));
}

#[test]
fn les_trois_formes_de_fragment_qui_existent_dans_la_nature() {
    // Un paste ordinaire, vu par son créateur.
    let f = coeur::analyser_fragment("CLE~JETON".to_string());
    assert_eq!((f.cle.as_str(), f.jeton.as_str()), ("CLE", "JETON"));

    // Un paste protégé par mot de passe : la clé se dérive, elle ne voyage pas.
    let f = coeur::analyser_fragment("~JETON".to_string());
    assert_eq!((f.cle.as_str(), f.jeton.as_str()), ("", "JETON"));

    // Un lien partagé, dont on a retiré le jeton. Le refuser priverait de lecture le
    // destinataire, c'est-à-dire le seul cas qui compte pour un service de partage.
    let f = coeur::analyser_fragment("CLE".to_string());
    assert_eq!((f.cle.as_str(), f.jeton.as_str()), ("CLE", ""));

    // Le `#` d'une URL, si l'appelant l'a laissé.
    let f = coeur::analyser_fragment("#CLE~JETON".to_string());
    assert_eq!(f.cle.as_str(), "CLE");
}

#[test]
fn une_mauvaise_cle_echoue_franchement() {
    let e = coeur::sceller(b"secret".to_vec()).unwrap();
    let fausse = URL_SAFE_NO_PAD.encode([0u8; 32]);
    assert!(coeur::ouvrir(fausse, e.nonce, e.chiffre).is_err());
}

#[test]
fn un_chiffre_altere_est_rejete_plutot_que_rendu_faux() {
    let e = coeur::sceller(b"secret".to_vec()).unwrap();
    let mut octets = STANDARD.decode(&e.chiffre).unwrap();
    octets[0] ^= 1;
    assert!(coeur::ouvrir(e.cle, e.nonce, STANDARD.encode(octets)).is_err());
}

#[test]
fn le_nonce_de_vingt_quatre_octets_du_coffre_est_refuse() {
    // La confusion précise qui produisait un 502 chez le relais.
    let e = coeur::sceller(b"x".to_vec()).unwrap();
    assert!(coeur::ouvrir(e.cle, STANDARD.encode([0u8; 24]), e.chiffre).is_err());
}

#[test]
fn deux_pastes_ne_partagent_ni_cle_ni_nonce() {
    // L'invariant qui rend acceptable un nonce aléatoire de 96 bits sous AES-GCM. S'il
    // tombait, une réutilisation de nonce livrerait la clé d'authentification.
    let (a, b) = (
        coeur::sceller(b"x".to_vec()).unwrap(),
        coeur::sceller(b"x".to_vec()).unwrap(),
    );
    assert_ne!(a.cle, b.cle);
    assert_ne!(a.nonce, b.nonce);
}

#[test]
fn le_contenu_binaire_traverse_intact() {
    // Un paste gzippé n'est pas du texte : forcer l'UTF-8 au retour le rendrait illisible.
    let octets: Vec<u8> = (0u8..=255).collect();
    let e = coeur::sceller(octets.clone()).unwrap();
    assert_eq!(coeur::ouvrir(e.cle, e.nonce, e.chiffre).unwrap(), octets);
}
