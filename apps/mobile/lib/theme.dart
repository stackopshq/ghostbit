import 'dart:ui';

import 'package:flutter/material.dart';

/// La palette de GhostBit, relevée sur `suite/assets/ghostbit/ghost-theme.css`.
///
/// **Les jetons font foi** (charte §5). L'accent, ses deux variantes et les neutres
/// viennent du fichier généré par `tools/brand/emit_theme.py` ; rien n'est choisi ici.
///
/// ─── Un écart relevé et non tranché ───
///
/// Le produit porte aujourd'hui **deux violets**. `suite/assets/ghostbit/ghost-theme.css`
/// dit `--color-accent: #A93BFF`, la valeur qu'on retrouve au stop médian de `logo.svg`.
/// Le CSS servi par le produit, `static/style.css`, dit `--brand-primary: #BC13FE` et
/// l'emploie partout — boutons, focus, halo, dégradé du mot-marque.
///
/// Ce sont deux violets voisins mais distincts, et rien ne signale l'écart : chacun est
/// cohérent chez lui. Ce fichier suit les **jetons de la suite**, parce que c'est ce que la
/// charte désigne comme source, et parce que c'est le violet du logo posé juste au-dessus
/// sur l'écran d'entrée — un halo d'une autre teinte que la marque qu'il entoure se
/// remarque. L'écart est signalé dans le rapport ; il se tranche à la source, pas ici.
///
/// Chaque couleur existe en deux versions : le thème clair n'est pas le sombre éclairci.
/// Les surfaces claires viennent du bloc `[data-theme="light"]` de `static/style.css`,
/// seul endroit du produit où un thème clair est décrit.
class Gb {
  const Gb._(this.sombre);

  final bool sombre;

  factory Gb.of(BuildContext context) =>
      Gb._(Theme.of(context).brightness == Brightness.dark);

  Color _c(int fonce, int clair) => Color(0xFF000000 | (sombre ? fonce : clair));

  /// `--color-base` / le `--bg-page` clair du produit.
  Color get base => _c(0x0B0F19, 0xF6F7FB);
  Color get surface => _c(0x161B26, 0xFFFFFF);
  Color get surface2 => _c(0x1E2431, 0xF0F1F7);

  /// `--color-foreground` / `--text`.
  Color get encre => _c(0xE8ECF5, 0x1C1E2A);

  /// `--color-muted` / `--text-muted`.
  Color get estompe => _c(0x9AA3B8, 0x5B6480);

  /// `--color-accent`. En aplat il porte de l'encre **noire** (`--color-accent-ink`) :
  /// c'est un violet clair, et du blanc dessus tombe sous le rapport de contraste.
  Color get accent => _c(0xA93BFF, 0xA93BFF);

  /// L'accent lisible **en texte**, sur fond clair : `--color-accent-deep`. Le violet de
  /// l'aplat passe derrière des lettres noires, pas devant.
  Color get accentTexte => _c(0xC77BFF, 0x6C1BD8);

  Color get bordure =>
      sombre ? Colors.white.withValues(alpha: 0.06) : const Color(0x1A1C1E2A);
  Color get bordureFranche =>
      sombre ? Colors.white.withValues(alpha: 0.12) : const Color(0x2E1C1E2A);

  Color get danger => _c(0xFF5555, 0xC43333);
  Color get succes => _c(0x50FA7B, 0x0A5F2A);

  /// La teinte du halo. Fixe : c'est une source de lumière, pas une surface, et elle ne
  /// s'adapte donc pas au thème. C'est l'accent de la marque.
  static const neon = Color(0xFFA93BFF);

  /// L'encre posée **sur** l'aplat d'accent : `--color-accent-ink`, qui vaut `#000000`
  /// pour ghostbit. Elle est dérivée de la luminance de l'accent par le générateur, et
  /// c'est pour ça qu'elle n'est pas blanche comme chez ghostcal — la recopier d'un
  /// produit frère donnerait du texte illisible sur le bouton principal.
  static const surAccent = Color(0xFF000000);

  /// Le halo de la suite : **deux** rayonnements superposés, l'un serré et vif, l'autre
  /// large et diffus (charte §3, transposition de `--brand-glow`).
  ///
  /// Les deux comptent : un seul halo fait une tache molle, tandis que la superposition
  /// d'un noyau net et d'une aura étalée donne l'impression d'une source de lumière. Le
  /// rayon tombe à 45 % en thème clair, où un néon sur fond blanc devient une bavure.
  List<BoxShadow> halo(double force) {
    final echelle = sombre ? force : force * 0.45;
    if (echelle <= 0) return const [];
    return [
      BoxShadow(color: neon.withValues(alpha: 0.60 * echelle), blurRadius: 8 * echelle),
      BoxShadow(color: neon.withValues(alpha: 0.35 * echelle), blurRadius: 20 * echelle),
    ];
  }

  /// Le même halo, pour du **texte**.
  ///
  /// Un `BoxShadow` suit la boîte : posé derrière des lettres, il peint un rectangle
  /// coloré au lieu de les faire rayonner. Seules les ombres du style de texte suivent la
  /// forme des glyphes. Constaté sur le portage Flutter de ghostcal, corrigé de même.
  List<Shadow> haloDeTexte(double force) {
    final echelle = sombre ? force : force * 0.45;
    if (echelle <= 0) return const [];
    return [
      Shadow(color: neon.withValues(alpha: 0.60 * echelle), blurRadius: 8 * echelle),
      Shadow(color: neon.withValues(alpha: 0.35 * echelle), blurRadius: 20 * echelle),
    ];
  }
}

/// Mesures partagées, relevées sur les jetons de `ghost-theme.css`.
///
/// `rayonChamp` vaut **8** et non 12 : `--radius-sm`, ce que `.ghost-input` applique
/// depuis le 2026-08-31. Un champ moins arrondi qu'un bouton creuse la hiérarchie entre ce
/// qu'on remplit et ce sur quoi on appuie.
class Mesures {
  /// `--radius-sm` — les champs.
  static const rayonChamp = 8.0;

  /// `--radius` — les boutons. Le web les arrondit en pilule (`--radius-pill`) ; le mobile
  /// ne le fait pas, et c'est une **exception écrite** (charte §7), pas une dérive :
  /// le champ de recherche appartient au système sur iOS et n'est pas une pilule chez
  /// Material non plus, si bien qu'un bouton en pilule posé à côté jure davantage que
  /// l'écart avec le web — qu'on ne voit jamais côte à côte.
  static const rayon = 12.0;

  /// `--radius-lg` — les cartes.
  static const rayonCarte = 18.0;

  static const ecart = 12.0;
  static const marge = 16.0;

  /// Propre au mobile : le CSS n'a pas de marge intérieure de carte (charte §5).
  static const margeCarte = 24.0;

  /// Écart entre deux champs, et entre un libellé et son champ (charte §5).
  static const ecartChamps = 18.0;
  static const ecartLibelle = 7.0;

  /// Au-delà, sur tablette, les champs s'étirent sur toute la dalle et le formulaire perd
  /// sa forme (charte §2).
  static const largeurMax = 420.0;
}

/// Le fond de l'application : nuit profonde et halo diffusé depuis le haut.
///
/// Le dégradé sombre est celui de `--bg-gradient` du produit, ramené à ses quatre arrêts.
/// En thème clair il disparaît : quatre nuances de blanc ne se distinguent pas.
class FondGhost extends StatelessWidget {
  const FondGhost({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    return Stack(
      children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: gb.sombre
                  ? const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        Color(0xFF0D0B14),
                        Color(0xFF110720),
                        Color(0xFF080F1A),
                        Color(0xFF0A0810),
                      ],
                    )
                  : null,
              color: gb.sombre ? null : gb.base,
            ),
          ),
        ),
        Positioned(
          top: -140,
          left: 0,
          right: 0,
          height: 620,
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment.topCenter,
                  radius: 0.9,
                  colors: [
                    Gb.neon.withValues(alpha: gb.sombre ? 0.22 : 0.10),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        ),
        child,
      ],
    );
  }
}

/// Carte de verre fumé : surface translucide, filet clair, et le flou qui la rend vitreuse.
///
/// Le `BackdropFilter` est ce qui distingue une carte de verre d'un rectangle gris : sans
/// lui, la translucidité ne montre rien puisque rien n'est flouté derrière (charte §4).
///
/// La charte note qu'Android n'a pas d'équivalent et s'en passe. Flutter n'a pas ce
/// problème : `BackdropFilter` floute bien ce qui est **derrière** le composant sur les
/// deux plateformes, parce que c'est le moteur de rendu de Flutter qui compose et non
/// celui du système. L'écart de la §7 est propre à Compose, et il ne se transpose pas ici.
class CarteDeVerre extends StatelessWidget {
  const CarteDeVerre({super.key, required this.child, this.marge = Mesures.margeCarte});

  final Widget child;
  final double marge;

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    return ClipRRect(
      borderRadius: BorderRadius.circular(Mesures.rayonCarte),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: EdgeInsets.all(marge),
          decoration: BoxDecoration(
            color: gb.surface.withValues(alpha: 0.65),
            borderRadius: BorderRadius.circular(Mesures.rayonCarte),
            border: Border.all(color: gb.bordure),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// L'enseigne de l'écran d'entrée : la marque sur sa plaque, le nom, un sous-titre.
///
/// Copiée **structure par structure** de l'écran d'entrée de la suite, et non « dans
/// l'esprit » : plaque de 64 pt avec 14 pt de marge, rayon 22, filet, fond franchement
/// noir ou blanc. Pas une surface du thème, qui la ferait se fondre à nouveau.
///
/// **La marque rayonne, et elle seule.** C'est le seul néon de cet écran, et c'est ce qui
/// rattache GhostBit au reste de la suite.
class Enseigne extends StatelessWidget {
  const Enseigne({super.key, required this.sousTitre});

  final String sousTitre;

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    return Column(
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            color: gb.sombre ? Colors.black : Colors.white,
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: gb.bordure),
            boxShadow: gb.halo(1),
          ),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Image.asset('assets/marque/logo.png', width: 64, height: 64),
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'GhostBit',
          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: gb.encre),
        ),
        const SizedBox(height: 2),
        Text(sousTitre, style: TextStyle(fontSize: 13, color: gb.estompe)),
      ],
    );
  }
}

/// Le libellé de section de la charte : petites capitales espacées, teinte estompée.
/// Il nomme sans se disputer l'attention avec ce qu'on saisit.
class Libelle extends StatelessWidget {
  const Libelle(this.texte, {super.key});

  final String texte;

  @override
  Widget build(BuildContext context) => Text(
        texte.toUpperCase(),
        style: TextStyle(
          color: Gb.of(context).estompe,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.1,
        ),
      );
}

/// Un libellé et son champ, à l'écart que la charte fixe (§5).
class Champ extends StatelessWidget {
  const Champ({super.key, required this.titre, required this.enfant});

  final String titre;
  final Widget enfant;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Libelle(titre),
          const SizedBox(height: Mesures.ecartLibelle),
          enfant,
        ],
      );
}

/// Action principale : un bloc d'accent plein, pleine largeur, qui rayonne.
///
/// L'aplat est **plein** et porte un halo, parce que c'est ce que les jetons de ghostbit
/// disent : `--accent-surface: var(--color-accent)` et `--accent-glow: 0 0 18px …`. Le
/// générateur dérive cette forme de la luminance de l'accent, et elle diffère d'un produit
/// à l'autre — ghostcal remplit le sien à 14 % et n'a pas de halo du tout. Recopier le
/// bouton d'un produit frère est exactement ce que `emit_theme.py` a été écrit pour
/// empêcher.
class BoutonPrincipal extends StatelessWidget {
  const BoutonPrincipal({super.key, required this.child, this.onPressed});

  final Widget child;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    final actif = onPressed != null;
    return DecoratedBox(
      decoration: ShapeDecoration(
        // Rectangulaire, et non la pilule du web : exception assumée, charte §7.
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Mesures.rayon),
        ),
        // Seule l'action disponible rayonne. Faire luire un bouton inerte appellerait
        // l'œil vers ce sur quoi on ne peut pas appuyer.
        shadows: gb.halo(actif ? 0.85 : 0),
      ),
      child: Material(
        color: gb.accent.withValues(alpha: actif ? 1 : 0.35),
        borderRadius: BorderRadius.circular(Mesures.rayon),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(Mesures.rayon),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 15),
            alignment: Alignment.center,
            child: DefaultTextStyle.merge(
              style: const TextStyle(
                color: Gb.surAccent,
                fontWeight: FontWeight.w600,
                fontSize: 16,
              ),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}

/// Action secondaire : le `.ghost-btn-quiet` du CSS — transparent, filet franc.
class BoutonDiscret extends StatelessWidget {
  const BoutonDiscret({super.key, required this.child, this.onPressed, this.teinte});

  final Widget child;
  final VoidCallback? onPressed;
  final Color? teinte;

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    final couleur = teinte ?? gb.encre;
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        foregroundColor: couleur,
        side: BorderSide(color: gb.bordureFranche),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Mesures.rayon),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
      ),
      child: child,
    );
  }
}

ThemeData themeGhostbit(Brightness luminosite) {
  final gb = Gb._(luminosite == Brightness.dark);
  return ThemeData(
    useMaterial3: true,
    brightness: luminosite,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Gb.neon,
      brightness: luminosite,
      surface: gb.surface,
      // Sans cette ligne, `fromSeed` fabrique un violet terne à partir de la graine et le
      // pose sur tous les boutons : l'accent de la charte n'apparaît nulle part, alors
      // qu'il est la seule couleur vive de l'interface.
      primary: gb.accent,
      onPrimary: Gb.surAccent,
    ),
    // Le fond est peint par `FondGhost`, qui porte le dégradé et le halo. Un Scaffold
    // opaque par-dessus les masquerait tous les deux.
    scaffoldBackgroundColor: Colors.transparent,
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      foregroundColor: gb.encre,
      elevation: 0,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: gb.surface2,
      hintStyle: TextStyle(color: gb.estompe.withValues(alpha: 0.7)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      // `--radius-sm`, le rayon des champs — pas celui des boutons.
      border: _filet(gb.bordureFranche),
      enabledBorder: _filet(gb.bordureFranche),
      focusedBorder: _filet(gb.accentTexte, epaisseur: 1.5),
    ),
  );
}

OutlineInputBorder _filet(Color couleur, {double epaisseur = 1}) => OutlineInputBorder(
      borderRadius: BorderRadius.circular(Mesures.rayonChamp),
      borderSide: BorderSide(color: couleur, width: epaisseur),
    );
