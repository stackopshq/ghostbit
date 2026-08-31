import 'package:flutter/material.dart';

import '../services/historique.dart';
import '../services/pastes.dart';
import '../theme.dart';
import 'creation.dart' show copier;
import 'lecture.dart';

/// Ce que cet appareil a créé, et ce qu'on peut encore en faire.
///
/// ─── La règle qui gouverne cet écran ───
///
/// **Il n'interroge pas le serveur.** Pas au chargement, pas en tirant pour rafraîchir,
/// jamais. `GET /api/v1/pastes/{id}` **compte comme une vue** : un paste « brûler après
/// lecture » serait détruit par le simple fait d'afficher la liste qui le nomme, et un
/// paste à vues limitées en perdrait une à chaque coup d'œil. La commodité de montrer un
/// état à jour détruirait les données qu'elle prétend décrire.
///
/// L'état affiché est donc **ce que cet appareil sait**, et l'écran le dit avec ces
/// mots-là. Un paste peut y paraître vivant et avoir déjà brûlé ailleurs. Afficher une
/// certitude qu'on n'a pas serait pire que d'afficher une estimation nommée comme telle.
///
/// ─── Et le contenu n'y est pas ───
///
/// Aucun aperçu, aucune première ligne. Ce serait du clair au repos sur l'appareil, et une
/// capture d'écran de la liste rendrait le chiffrement décoratif. On lit donc par langage,
/// taille et date.
class EcranHistorique extends StatefulWidget {
  const EcranHistorique({super.key, required this.service});

  final ServicePastes service;

  @override
  State<EcranHistorique> createState() => _EcranHistoriqueState();
}

class _EcranHistoriqueState extends State<EcranHistorique> {
  late Future<List<EntreeHistorique>> _entrees;

  @override
  void initState() {
    super.initState();
    _recharger();
  }

  void _recharger() {
    // Relit le trousseau, et **rien d'autre** : aucune requête ne part d'ici.
    setState(() => _entrees = widget.service.historique.tout());
  }

  Future<void> _revoquer(EntreeHistorique e) async {
    final confirme = await _confirmer(
      titre: 'Révoquer ce paste ?',
      corps: 'Il deviendra illisible pour tout le monde, y compris pour qui a déjà le lien. '
          'C\'est immédiat et sans retour.',
      action: 'Révoquer',
      dangereux: true,
    );
    if (confirme != true) return;
    try {
      await widget.service.revoquer(e);
      _recharger();
    } catch (err) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Échec : $err')));
      }
    }
  }

  Future<void> _oublier(EntreeHistorique e) async {
    final confirme = await _confirmer(
      titre: 'Retirer de l\'historique ?',
      // La distinction que cet écran doit absolument porter : retirer la ligne n'efface
      // pas le paste, et jette la seule copie du jeton qui permettrait de l'effacer.
      corps: 'Le paste **ne sera pas supprimé**. Cet appareil oubliera sa clé et son jeton, '
          'donc plus personne ne pourra ni l\'ouvrir ni le révoquer avant son expiration.',
      action: 'Retirer',
      dangereux: true,
    );
    if (confirme != true) return;
    await widget.service.historique.oublier(e.id);
    _recharger();
  }

  Future<bool?> _confirmer({
    required String titre,
    required String corps,
    required String action,
    bool dangereux = false,
  }) {
    final gb = Gb.of(context);
    return showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        backgroundColor: gb.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Mesures.rayonCarte),
        ),
        title: Text(titre, style: TextStyle(color: gb.encre, fontSize: 18)),
        content: Text(corps.replaceAll('**', ''),
            style: TextStyle(color: gb.estompe, fontSize: 14, height: 1.4)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(c).pop(false),
            child: Text('Annuler', style: TextStyle(color: gb.estompe)),
          ),
          TextButton(
            onPressed: () => Navigator.of(c).pop(true),
            child: Text(action,
                style: TextStyle(color: dangereux ? gb.danger : gb.accentTexte)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Mesures.largeurMax),
            child: FutureBuilder<List<EntreeHistorique>>(
              future: _entrees,
              builder: (context, instantane) {
                if (!instantane.hasData) {
                  return const Center(child: CircularProgressIndicator());
                }
                final entrees = instantane.data!;
                if (entrees.isEmpty) return _vide(gb);
                return ListView.separated(
                  padding: const EdgeInsets.all(Mesures.marge),
                  itemCount: entrees.length + 1,
                  separatorBuilder: (_, _) => const SizedBox(height: Mesures.ecart),
                  itemBuilder: (_, i) => i == entrees.length
                      ? _mentionDEtat(gb)
                      : _ligne(gb, entrees[i]),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _vide(Gb gb) => Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.history, size: 40, color: gb.estompe),
            const SizedBox(height: 12),
            Text(
              'Rien pour l\'instant.',
              style: TextStyle(fontSize: 16, color: gb.encre),
            ),
            const SizedBox(height: 6),
            Text(
              'Les pastes créés depuis cet appareil apparaîtront ici, avec leur clé. '
              'Rien n\'est synchronisé : cet historique ne quitte pas le téléphone.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: gb.estompe, height: 1.4),
            ),
          ],
        ),
      );

  /// La mention qui rend l'écran honnête, et qui n'est pas une politesse.
  Widget _mentionDEtat(Gb gb) => Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 24),
        child: Text(
          'État d\'après cet appareil. Le vérifier auprès du serveur consommerait une '
          'lecture, ce qui détruirait les pastes à brûler.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: gb.estompe, height: 1.4),
        ),
      );

  Widget _ligne(Gb gb, EntreeHistorique e) {
    final mort = e.revoque || e.expireProbablement;
    return CarteDeVerre(
      marge: Mesures.ecart,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  e.id,
                  style: TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 15,
                    color: mort ? gb.estompe : gb.encre,
                    decoration: e.revoque ? TextDecoration.lineThrough : null,
                  ),
                ),
              ),
              if (e.brule) _puce(gb, 'brûle à la lecture', gb.danger),
              if (e.vuesMax != null) _puce(gb, '${e.vuesMax} vues max', gb.estompe),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            _sousTitre(e),
            style: TextStyle(fontSize: 12, color: gb.estompe),
          ),
          const SizedBox(height: Mesures.ecart),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (!mort)
                BoutonDiscret(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => EcranLecture(
                        service: widget.service,
                        lien: e.lien,
                      ),
                    ),
                  ),
                  child: const Text('Ouvrir'),
                ),
              BoutonDiscret(
                onPressed: () => copier(context, e.lien, 'Lien'),
                child: const Text('Copier'),
              ),
              if (!e.revoque)
                BoutonDiscret(
                  teinte: gb.danger,
                  onPressed: () => _revoquer(e),
                  child: const Text('Révoquer'),
                ),
              BoutonDiscret(
                onPressed: () => _oublier(e),
                child: const Text('Retirer'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _sousTitre(EntreeHistorique e) {
    final morceaux = <String>[
      if (e.langage != null) e.langage!,
      if (e.octets > 0)
        e.octets < 1024 ? '${e.octets} o' : '${(e.octets / 1024).toStringAsFixed(1)} Kio',
      _quand(e.creeLe),
    ];
    if (e.revoque) return 'Révoqué · ${morceaux.join(' · ')}';
    if (e.expireProbablement) return 'Expiré · ${morceaux.join(' · ')}';
    if (e.expireLe != null) {
      morceaux.add('expire ${_quand(e.expireLe!, futur: true)}');
    }
    return morceaux.join(' · ');
  }

  static String _quand(DateTime t, {bool futur = false}) {
    final d = futur ? t.difference(DateTime.now()) : DateTime.now().difference(t);
    final prefixe = futur ? 'dans ' : 'il y a ';
    if (d.inMinutes < 1) return futur ? 'bientôt' : 'à l\'instant';
    if (d.inHours < 1) return '$prefixe${d.inMinutes} min';
    if (d.inDays < 1) return '$prefixe${d.inHours} h';
    return '$prefixe${d.inDays} j';
  }

  Widget _puce(Gb gb, String texte, Color teinte) => Container(
        margin: const EdgeInsets.only(left: 6),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: teinte.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(texte, style: TextStyle(fontSize: 11, color: teinte)),
      );
}
