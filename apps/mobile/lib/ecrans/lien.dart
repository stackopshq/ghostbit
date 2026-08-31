import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../services/historique.dart';
import '../theme.dart';
import 'creation.dart' show copier;

/// Le lien, une fois le paste créé.
///
/// ─── Pourquoi cet écran existe plutôt qu'un simple message ───
///
/// Ce lien est **la seule copie de la clé qui existe**. Le serveur n'en a pas, et ne
/// pourra jamais la redonner : il ne stocke que du chiffré. Un message éphémère au bas de
/// l'écran, qu'un changement d'application fait disparaître, laisserait quelqu'un avec un
/// paste qu'il ne peut plus ouvrir et qu'il ne peut plus supprimer.
///
/// L'écran s'interpose donc, montre le lien en entier, et nomme ce qui se passe si on le
/// perd. C'est l'endroit où le modèle zero-knowledge cesse d'être une qualité et devient
/// une contrainte pour l'utilisateur ; le taire serait le laisser la découvrir seul.
class EcranLien extends StatelessWidget {
  const EcranLien({super.key, required this.entree});

  final EntreeHistorique entree;

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Paste créé')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: Mesures.largeurMax),
              child: Padding(
                padding: const EdgeInsets.all(Mesures.marge),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    CarteDeVerre(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.check_circle_outline,
                                  size: 18, color: gb.succes),
                              const SizedBox(width: 8),
                              Text(
                                'Chiffré sur cet appareil',
                                style: TextStyle(
                                    fontSize: 14,
                                    color: gb.succes,
                                    fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                          const SizedBox(height: Mesures.ecartChamps),
                          const Libelle('Lien'),
                          const SizedBox(height: Mesures.ecartLibelle),
                          _lien(gb),
                          const SizedBox(height: Mesures.ecartChamps),
                          _avertissement(gb),
                        ],
                      ),
                    ),
                    const SizedBox(height: Mesures.ecart),
                    BoutonPrincipal(
                      key: const Key('bouton.partager'),
                      onPressed: () => SharePlus.instance.share(
                        ShareParams(text: entree.lien),
                      ),
                      child: const Text('Partager le lien'),
                    ),
                    const SizedBox(height: Mesures.ecart),
                    BoutonDiscret(
                      onPressed: () => copier(context, entree.lien, 'Lien'),
                      child: const Text('Copier'),
                    ),
                    const SizedBox(height: Mesures.ecart),
                    Text(
                      'Ce lien est aussi dans l\'historique, sur cet appareil seulement.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: gb.estompe),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// Le lien, avec le fragment détaché du reste.
  ///
  /// La séparation est visuelle et elle enseigne : ce qui est en accent après le `#` est
  /// précisément ce que le serveur ne reçoit pas. C'est aussi la partie qu'un client de
  /// messagerie tronque quand il détecte mal la fin d'une URL, et la voir aide à repérer
  /// un lien coupé avant de l'envoyer.
  Widget _lien(Gb gb) {
    final diese = entree.lien.indexOf('#');
    final avant = diese < 0 ? entree.lien : entree.lien.substring(0, diese);
    final apres = diese < 0 ? '' : entree.lien.substring(diese);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: gb.surface2,
        borderRadius: BorderRadius.circular(Mesures.rayonChamp),
        border: Border.all(color: gb.bordureFranche),
      ),
      child: SelectableText.rich(
        TextSpan(
          style: const TextStyle(fontFamily: 'monospace', fontSize: 13, height: 1.5),
          children: [
            TextSpan(text: avant, style: TextStyle(color: gb.encre)),
            TextSpan(text: apres, style: TextStyle(color: gb.accentTexte)),
          ],
        ),
      ),
    );
  }

  Widget _avertissement(Gb gb) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.key_outlined, size: 16, color: gb.estompe),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'La partie après le # est la clé. Elle n\'a pas été envoyée au serveur et '
              'ne peut pas être retrouvée : un lien tronqué est un paste perdu, pour tout '
              'le monde.',
              style: TextStyle(fontSize: 13, color: gb.estompe, height: 1.4),
            ),
          ),
        ],
      );
}
