import 'package:flutter/material.dart';

import '../services/reglages.dart';
import '../theme.dart';

/// Entrer dans GhostBit — **le même écran que le déverrouillage de GhostPass et la
/// connexion de GhostCal**, aux couleurs et à la marque de GhostBit.
///
/// C'est délibéré et ça se copie structure par structure (charte §2) : enseigne sur plaque
/// avec son halo, nom du produit, sous-titre discret, puis une carte de verre bornée à
/// 420 portant les champs et l'action. Les applications de la suite sont des frères ; un
/// écran d'entrée qui diverge fait douter qu'elles viennent du même endroit, ce qu'un
/// produit chiffré ne peut pas se permettre.
///
/// ─── Ce que cet écran demande, et pourquoi il en demande si peu ───
///
/// Ghostbit n'a **ni compte ni mot de passe maître** : il n'y a donc rien à déverrouiller.
/// Là où ses frères demandent une phrase, celui-ci demande la seule chose qu'il ne peut pas
/// deviner — **l'adresse de l'instance**. Le produit est fait pour être auto-hébergé, et
/// coder une adresse par défaut enverrait chez un tiers les pastes de quelqu'un qui fait
/// tourner la sienne, en silence.
///
/// Un seul champ dans une carte prévue pour deux paraîtrait vide. Il est accompagné de ce
/// que cet écran doit dire de toute façon : ce que l'application ne transmettra jamais.
class EcranEntree extends StatefulWidget {
  const EcranEntree({super.key, required this.reglages, required this.quandPret});

  final Reglages reglages;
  final VoidCallback quandPret;

  @override
  State<EcranEntree> createState() => _EcranEntreeState();
}

class _EcranEntreeState extends State<EcranEntree> {
  late final _serveur = TextEditingController(text: widget.reglages.serveur ?? '');
  String? _refus;
  bool _occupe = false;

  @override
  void dispose() {
    _serveur.dispose();
    super.dispose();
  }

  Future<void> _valider() async {
    final refus = Reglages.refus(_serveur.text);
    if (refus != null) {
      setState(() => _refus = refus);
      return;
    }
    setState(() {
      _refus = null;
      _occupe = true;
    });
    await widget.reglages.poserLeServeur(_serveur.text);
    if (mounted) widget.quandPret();
  }

  @override
  Widget build(BuildContext context) {
    return FondGhost(
      child: Scaffold(
        body: SafeArea(
          child: SingleChildScrollView(
            // Le clavier couvre le bas de la carte. Faire défiler le referme ; un appui
            // dans le vide, non.
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: Mesures.largeurMax),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 40),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Enseigne(sousTitre: 'Pastes chiffrés de bout en bout'),
                      const SizedBox(height: 24),
                      _carte(),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _carte() {
    final gb = Gb.of(context);
    return CarteDeVerre(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Champ(
            titre: 'Instance',
            enfant: TextField(
              key: const Key('champ.serveur'),
              controller: _serveur,
              keyboardType: TextInputType.url,
              autocorrect: false,
              enableSuggestions: false,
              textCapitalization: TextCapitalization.none,
              onChanged: (_) => setState(() => _refus = null),
              onSubmitted: (_) => _valider(),
              // Le domaine est celui que la RFC 2606 réserve aux exemples : il ne résout
              // nulle part, donc personne ne postera par mégarde chez un tiers.
              decoration: const InputDecoration(hintText: 'https://paste.example.com'),
            ),
          ),
          const SizedBox(height: Mesures.ecartChamps),
          _promesse(gb),
          if (_refus != null) ...[
            const SizedBox(height: Mesures.ecartChamps),
            _avertissement(gb.danger, Icons.warning_amber_rounded, _refus!),
          ],
          const SizedBox(height: Mesures.ecartChamps),
          BoutonPrincipal(
            key: const Key('bouton.entrer'),
            onPressed: _occupe || _serveur.text.trim().isEmpty ? null : _valider,
            child: _occupe
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Gb.surAccent),
                  )
                : const Text('Continuer'),
          ),
        ],
      ),
    );
  }

  /// Ce que l'instance ne recevra pas. Dit ici parce que c'est le seul écran que tout le
  /// monde voit, et parce qu'une promesse de chiffrement qui n'est écrite nulle part ne
  /// se distingue pas d'une promesse de marketing.
  Widget _promesse(Gb gb) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.lock_outline, size: 16, color: gb.estompe),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Le contenu est chiffré sur cet appareil. La clé reste dans le lien, '
              'après le #, et n\'est jamais envoyée : cette instance ne stocke que du chiffré.',
              style: TextStyle(fontSize: 13, color: gb.estompe, height: 1.4),
            ),
          ),
        ],
      );

  Widget _avertissement(Color teinte, IconData icone, String texte) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icone, size: 16, color: teinte),
          const SizedBox(width: 8),
          Expanded(child: Text(texte, style: TextStyle(fontSize: 13, color: teinte))),
        ],
      );
}
