import 'package:flutter/material.dart';

import '../services/api.dart';
import '../services/pastes.dart';
import '../theme.dart';
import 'creation.dart' show copier;

/// Lire un paste.
///
/// ─── Ce que cet écran doit dire, et que la charte §8 réclame ───
///
/// **Ce qui ne se déchiffre pas s'affiche quand même, en disant qu'il est illisible.** Un
/// écran vide, ou un retour silencieux à la liste, se lit comme « il n'y avait rien » — ce
/// qui est faux, et ce qui laisse quelqu'un croire que son paste n'a jamais existé alors
/// qu'il est simplement inouvrable avec cette clé-là.
///
/// Trois échecs se ressemblent à l'écran et n'appellent pas le même geste, donc ils sont
/// distingués ici :
///
/// - **le paste n'existe plus** — expiré, brûlé, ou révoqué. Il n'y a rien à faire ;
/// - **la clé n'ouvre pas** — le lien a probablement été tronqué après le `#`, ce qu'un
///   client de messagerie fait couramment. Il y a quelque chose à faire : redemander le
///   lien entier ;
/// - **le paste est protégé par un mot de passe** — l'application ne sait pas encore
///   dériver ces clés-là. Ce n'est pas un échec de déchiffrement, c'est une limite du
///   produit, et la confondre avec les deux autres enverrait chercher un lien intact qui
///   n'aurait rien changé.
///
/// **Ouvrir consomme une vue** : arriver sur cet écran est le geste qui brûle un paste
/// marqué « brûler après lecture ». C'est pour ça que rien ne le déclenche automatiquement.
class EcranLecture extends StatefulWidget {
  const EcranLecture({super.key, required this.service, required this.lien});

  final ServicePastes service;
  final String lien;

  @override
  State<EcranLecture> createState() => _EcranLectureState();
}

class _EcranLectureState extends State<EcranLecture> {
  late Future<PasteOuvert> _paste;

  @override
  void initState() {
    super.initState();
    _paste = widget.service.ouvrirDepuisLien(widget.lien);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Paste')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: Padding(
              padding: const EdgeInsets.all(Mesures.marge),
              child: FutureBuilder<PasteOuvert>(
                future: _paste,
                builder: (context, instantane) {
                  if (instantane.connectionState != ConnectionState.done) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (instantane.hasError) {
                    return _echec(instantane.error!);
                  }
                  return _contenu(instantane.data!);
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _contenu(PasteOuvert p) {
    final gb = Gb.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (p.meta.brule || (p.meta.vuesMax != null && p.meta.vues >= p.meta.vuesMax!))
          Padding(
            padding: const EdgeInsets.only(bottom: Mesures.ecart),
            child: _bandeau(
              gb.danger,
              Icons.local_fire_department_outlined,
              'Ce paste vient d\'être détruit par cette lecture. Ce qui est à l\'écran est '
              'la dernière copie : elle disparaîtra avec cet écran.',
            ),
          ),
        Expanded(
          child: CarteDeVerre(
            marge: Mesures.ecart,
            child: SingleChildScrollView(
              child: SizedBox(
                width: double.infinity,
                child: SelectableText(
                  p.clair,
                  style: TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 13,
                    height: 1.45,
                    color: gb.encre,
                  ),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: Mesures.ecart),
        Text(
          _details(p),
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: gb.estompe),
        ),
        const SizedBox(height: Mesures.ecart),
        BoutonPrincipal(
          onPressed: () => copier(context, p.clair, 'Contenu'),
          child: const Text('Copier le contenu'),
        ),
      ],
    );
  }

  String _details(PasteOuvert p) {
    final m = <String>[
      if (p.meta.langage != null) p.meta.langage!,
      if (p.meta.compresse) 'compressé',
      '${p.meta.vues} vue${p.meta.vues > 1 ? 's' : ''}',
    ];
    if (p.meta.vuesMax != null) {
      final reste = p.meta.vuesMax! - p.meta.vues;
      m.add(reste > 0 ? '$reste restante${reste > 1 ? 's' : ''}' : 'plus aucune');
    }
    return m.join(' · ');
  }

  Widget _echec(Object erreur) {
    final gb = Gb.of(context);
    final (titre, corps, icone) = switch (erreur) {
      PasteIllisible(motDePasseRequis: true, raison: final r) => (
          'Protégé par un mot de passe',
          r,
          Icons.password_outlined,
        ),
      PasteIllisible(raison: final r) => ('Illisible', r, Icons.key_off_outlined),
      ErreurAPI(introuvable: true) => (
          'Ce paste n\'existe plus',
          'Il a expiré, atteint sa limite de vues, ou été brûlé par une lecture précédente. '
              'Le serveur ne fait pas la différence, et nous non plus : dans les trois cas, '
              'il n\'y a plus rien à ouvrir.',
          Icons.local_fire_department_outlined,
        ),
      ErreurAPI(message: final m) => ('Le serveur a refusé', m, Icons.cloud_off_outlined),
      _ => (
          'Échec',
          erreur.toString(),
          Icons.error_outline,
        ),
    };

    // On affiche l'échec **dans la même carte** que le contenu aurait occupée, plutôt que
    // de revenir en arrière : une ligne absente se lit comme « il n'y avait rien ».
    return Center(
      child: CarteDeVerre(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icone, size: 36, color: gb.estompe),
            const SizedBox(height: 12),
            Text(titre,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 17, color: gb.encre, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text(corps,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: gb.estompe, height: 1.45)),
          ],
        ),
      ),
    );
  }

  Widget _bandeau(Color teinte, IconData icone, String texte) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: teinte.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(Mesures.rayon),
          border: Border.all(color: teinte.withValues(alpha: 0.35)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icone, size: 16, color: teinte),
            const SizedBox(width: 8),
            Expanded(
              child: Text(texte,
                  style: TextStyle(fontSize: 13, color: teinte, height: 1.4)),
            ),
          ],
        ),
      );
}
