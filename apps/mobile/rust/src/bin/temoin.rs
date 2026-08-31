//! Le cœur, en ligne de commande, pour que le témoin croisé puisse l'interroger.
//!
//! Ce binaire n'a qu'une raison d'être : permettre à un script Node d'appeler **le code
//! que l'application appelle**, et non une transcription de ce code. Un témoin qui
//! réimplémenterait le scellement en JavaScript pour le comparer au JavaScript du site
//! comparerait deux copies l'une à l'autre, et serait vert dans le monde cassé.
//!
//!   temoin sceller <clair>                    → {"chiffre":…, "nonce":…, "cle":…}
//!   temoin sceller-avec-cle <cle> <clair>     → idem, pour éprouver un encodage choisi
//!   temoin ouvrir <cle> <nonce> <chiffre>     → le clair, sur la sortie standard
//!   temoin fragment <cle> <jeton>             → CLE~JETON
//!   temoin analyser <fragment>                → {"cle":…, "jeton":…}

use std::io::Write;

use rust_lib_ghostbit::api::coeur;

fn echapper(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let sortir = |code: i32, message: &str| -> ! {
        eprintln!("{message}");
        std::process::exit(code)
    };

    match args.get(1).map(String::as_str) {
        Some("sceller") => {
            let clair = args.get(2).unwrap_or_else(|| sortir(2, "clair manquant"));
            let e = coeur::sceller(clair.as_bytes().to_vec())
                .unwrap_or_else(|err| sortir(1, &err.message));
            println!(
                r#"{{"chiffre":"{}","nonce":"{}","cle":"{}"}}"#,
                echapper(&e.chiffre),
                echapper(&e.nonce),
                echapper(&e.cle)
            );
        }
        Some("ouvrir") => {
            let (cle, nonce, chiffre) = (
                args.get(2).unwrap_or_else(|| sortir(2, "clé manquante")),
                args.get(3).unwrap_or_else(|| sortir(2, "nonce manquant")),
                args.get(4).unwrap_or_else(|| sortir(2, "chiffre manquant")),
            );
            let clair = coeur::ouvrir(cle.clone(), nonce.clone(), chiffre.clone())
                .unwrap_or_else(|err| sortir(1, &err.message));
            // Écrit en octets bruts : un paste compressé n'est pas du texte à ce stade, et
            // le forcer en UTF-8 ici cacherait précisément le cas qu'on veut éprouver.
            std::io::stdout().write_all(&clair).expect("écriture impossible");
        }
        Some("fragment") => {
            let cle = args.get(2).unwrap_or_else(|| sortir(2, "clé manquante"));
            let jeton = args.get(3).unwrap_or_else(|| sortir(2, "jeton manquant"));
            println!("{}", coeur::composer_fragment(cle.clone(), jeton.clone()));
        }
        Some("analyser") => {
            let f = coeur::analyser_fragment(
                args.get(2).unwrap_or_else(|| sortir(2, "fragment manquant")).clone(),
            );
            println!(
                r#"{{"cle":"{}","jeton":"{}"}}"#,
                echapper(&f.cle),
                echapper(&f.jeton)
            );
        }
        _ => sortir(
            2,
            "usage : temoin sceller|ouvrir|fragment|analyser …",
        ),
    }
}
