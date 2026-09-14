import XCTest

/// Le témoin de la feuille de partage : GhostBit y apparaît-il, et reçoit-il le contenu ?
///
/// ─── Les trois états, et pourquoi ils comptent ───
///
/// Un témoin qui ne connaît que « vert » et « rouge » ment sur son troisième cas. Celui-ci
/// doit **échouer** quand il n'a pas pu regarder — feuille qui ne s'ouvre pas, extension
/// absente de la liste, zone de rédaction jamais apparue — et non passer parce qu'il n'a
/// rien trouvé à contredire. Chaque attente ci-dessous se termine donc par une assertion
/// sur ce qu'elle attendait, jamais par un `if ... { }` silencieux.
///
/// ─── Ce que le texte témoin garantit ───
///
/// `HoteDePartage.texte` contient un jeton qui n'existe nulle part ailleurs sur l'appareil.
/// Chercher « test » dans la zone de rédaction passerait sur une feuille vide, puisque le
/// mot traîne partout dans iOS ; chercher ce jeton-là ne peut réussir que s'il a traversé.
final class TemoinFeuilleDePartage: XCTestCase {
    /// Le même texte que l'hôte. Dupliqué et non partagé : la cible de témoin ne compile
    /// pas les sources de l'hôte, et un `import` entre les deux ferait dépendre le témoin
    /// du module de l'application qu'il pilote — précisément ce qu'un témoin ne doit pas
    /// faire.
    static let jeton = "ghostbit-temoin-7f3a2b9e"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testGhostbitApparaitDansLaFeuilleEtRecoitLeTexte() throws {
        let hote = XCUIApplication(bundleIdentifier: "dev.ghostbit.hote-temoin")
        hote.launch()

        let bouton = hote.buttons["partager"]
        XCTAssertTrue(
            bouton.waitForExistence(timeout: 20),
            "L'hôte du témoin ne s'est pas lancé : ce n'est pas la feuille de partage qui "
                + "est en cause, c'est le montage du témoin lui-même."
        )
        bouton.tap()

        // ── 1. La feuille s'ouvre ────────────────────────────────────────────
        //
        // On n'attend pas « la feuille » en général mais AirDrop, qui n'existe que dans la
        // vraie feuille du système. Attendre un conteneur quelconque passerait sur
        // n'importe quelle vue modale.
        let feuille = hote.otherElements["ActivityListView"]
        XCTAssertTrue(
            feuille.waitForExistence(timeout: 20),
            "La feuille de partage d'iOS ne s'est pas ouverte."
        )
        ajouterCapture(hote, "01-feuille-ouverte")

        // ── 2. GhostBit y est ────────────────────────────────────────────────
        //
        // Le nom cherché est le `CFBundleDisplayName` de `ios/Partage/Info.plist`. Il est
        // écrit ici en toutes lettres, et non lu depuis le paquet : un témoin qui lit sa
        // valeur attendue dans la chose qu'il contrôle ne contrôle rien.
        let ghostbit = premierElement(dans: hote, nomme: "GhostBit")
        XCTAssertNotNil(
            ghostbit,
            "GhostBit n'apparaît pas dans la feuille de partage. L'extension est-elle "
                + "enregistrée ? `xcrun simctl spawn <sim> pluginkit -mAv | grep ghostbit`."
        )
        ghostbit?.tap()

        // ── 3. Elle reçoit le texte ──────────────────────────────────────────
        //
        // L'extension est un **processus séparé** : ses éléments n'appartiennent pas à
        // l'arbre de l'hôte, mais à une vue distante que le système y greffe. On
        // l'interroge donc par son propre identifiant de paquet.
        let extension_ = XCUIApplication(bundleIdentifier: "dev.ghostbit.ghostbit.Partage")
        let zone = extension_.textViews.firstMatch
        XCTAssertTrue(
            zone.waitForExistence(timeout: 25),
            "La feuille de GhostBit ne s'est pas affichée après l'avoir choisie."
        )
        ajouterCapture(extension_, "02-ghostbit-ouvert")

        let contenu = (zone.value as? String) ?? ""
        XCTAssertTrue(
            contenu.contains(Self.jeton),
            "La zone de rédaction n'a pas reçu le texte partagé. Vue : « \(contenu) »"
        )
    }

    // MARK: - Outils

    /// Le premier élément portant ce nom, quel que soit son type.
    ///
    /// La feuille de partage range ses applications tantôt en `cells`, tantôt en `buttons`,
    /// tantôt en `otherElements`, et la répartition change d'une version d'iOS à l'autre.
    /// Chercher un type précis rendrait ce témoin rouge à la prochaine version majeure,
    /// pour une raison qui n'a rien à voir avec GhostBit.
    private func premierElement(dans app: XCUIApplication, nomme nom: String) -> XCUIElement? {
        for requete in [app.cells, app.buttons, app.otherElements, app.staticTexts] {
            let element = requete.matching(NSPredicate(format: "label == %@", nom)).firstMatch
            if element.waitForExistence(timeout: 5) { return element }
        }
        return nil
    }

    private func ajouterCapture(_ app: XCUIApplication, _ nom: String) {
        let piece = XCTAttachment(screenshot: app.screenshot())
        piece.name = nom
        piece.lifetime = .keepAlways
        add(piece)
    }
}
