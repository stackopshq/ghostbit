#!/usr/bin/env python3
"""Engendre `lib/modeles/langages.dart` depuis `app/languages.json`.

    apps/mobile/outils/engendrer_langages.py

La liste des langages appartient au serveur : `app/languages.py` la lit pour la détection,
le gabarit Jinja pour son menu déroulant, le visualiseur pour le mode de coloration. Une
quatrième copie saisie à la main dériverait, et l'écart serait **muet** — un langage choisi
dans l'application et inconnu du serveur donne simplement un paste sans coloration, ce que
personne ne signale.

`test/langages_test.dart` relit le JSON et échoue si la sortie s'en écarte : l'artefact est
donc éprouvé contre son générateur, et non supposé à jour parce qu'il a été engendré un
jour.
"""

from __future__ import annotations

import json
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parents[2]  # apps/mobile/outils → dépôt ghostbit
SOURCE = RACINE / "app" / "languages.json"
SORTIE = ICI.parent / "lib" / "modeles" / "langages.dart"

EN_TETE = """// FICHIER GÉNÉRÉ depuis `app/languages.json` — ne pas éditer à la main.
//
// La liste des langages appartient au serveur : `app/languages.py` la lit pour la
// détection, le gabarit Jinja pour son menu déroulant, et le visualiseur pour le mode de
// coloration. Une quatrième copie saisie à la main dériverait, et l'écart serait muet —
// un langage choisi ici et inconnu là-bas donnerait simplement un paste sans coloration.
//
// `test/langages_test.dart` relit le JSON du serveur et échoue si cette liste s'en écarte.
// Régénérer avec `outils/engendrer_langages.py`.
"""


def main() -> None:
    langues = json.loads(SOURCE.read_text())
    slugs = [l["slug"] for l in langues]
    extensions = {l["slug"]: (l["extensions"][0] if l["extensions"] else "") for l in langues}

    lignes = [EN_TETE, "", "/// Les slugs de langage que l'instance connaît, dans l'ordre du serveur.", "const langagesConnus = <String>["]
    lignes += [f"  '{s}'," for s in slugs]
    lignes += [
        "];",
        "",
        "/// L'extension de fichier principale de chaque langage, pour nommer un partage.",
        "const extensionsParLangage = <String, String>{",
    ]
    lignes += [f"  '{s}': '{extensions[s]}'," for s in slugs]
    lignes.append("};")

    SORTIE.write_text("\n".join(lignes) + "\n")
    print(f"{len(slugs)} langages écrits dans {SORTIE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
