import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../modeles/langages.dart';
import '../services/api.dart';
import '../services/historique.dart';
import '../services/pastes.dart';
import '../theme.dart';
import 'lien.dart';

/// Créer un paste.
///
/// L'écran est celui du web, ramené à ce qui tient dans une main : la zone de saisie, puis
/// les options dans une carte qu'on déplie. Le web les montre toutes à côté de l'éditeur
/// parce qu'il a la place ; sur un téléphone, les empiler au-dessus du clavier ferait
/// disparaître ce qu'on écrit.
class EcranCreation extends StatefulWidget {
  const EcranCreation({super.key, required this.service, this.texteInitial});

  final ServicePastes service;

  /// Le texte reçu d'un partage Android (`ACTION_SEND`). Non nul, l'écran s'ouvre déjà
  /// rempli et l'utilisateur n'a plus qu'à régler l'expiration.
  final String? texteInitial;

  @override
  State<EcranCreation> createState() => _EcranCreationState();
}

/// Les durées d'expiration proposées, en secondes. `null` veut dire « jamais ».
///
/// Le plafond du serveur est d'un an (`le=31_536_000`) : proposer davantage ferait refuser
/// la création par un 422 dont le message parlerait de bornes, pas d'expiration.
const _expirations = <String, int?>{
  '10 minutes': 600,
  '1 heure': 3600,
  '1 jour': 86400,
  '1 semaine': 604800,
  '1 mois': 2592000,
  '1 an': 31536000,
  'Jamais': null,
};

class _EcranCreationState extends State<EcranCreation> {
  late final _contenu = TextEditingController(text: widget.texteInitial ?? '');
  String? _langage;
  String _expiration = '1 jour';
  bool _brule = false;
  bool _compresser = false;
  int? _vuesMax;
  bool _optionsOuvertes = false;
  bool _occupe = false;
  String? _erreur;
  bool _detectionEnCours = false;

  @override
  void initState() {
    super.initState();
    _contenu.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _contenu.dispose();
    super.dispose();
  }

  Future<void> _creer() async {
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    try {
      final entree = await widget.service.creer(
        _contenu.text,
        langage: _langage,
        expireDansSecondes: _expirations[_expiration],
        brule: _brule,
        vuesMax: _vuesMax,
        compresser: _compresser,
      );
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => EcranLien(entree: entree)),
      );
      if (mounted) {
        setState(() {
          _contenu.clear();
          _occupe = false;
        });
      }
    } on ErreurAPI catch (e) {
      if (mounted) setState(() => (_erreur = e.message, _occupe = false).$1);
    } catch (e) {
      if (mounted) setState(() => (_erreur = e.toString(), _occupe = false).$1);
    }
  }

  /// Devine le langage — **en envoyant le texte au serveur**.
  ///
  /// C'est la seule route de ghostbit qui reçoit du clair. Le serveur ne le stocke pas,
  /// mais il le voit ; l'appeler d'office, comme le fait la page web au fil de la frappe,
  /// reviendrait à transmettre un secret que l'utilisateur croit chiffré. Ici c'est donc
  /// un geste explicite, et le bouton dit ce qu'il fait.
  Future<void> _detecter() async {
    setState(() => _detectionEnCours = true);
    try {
      final trouve = await widget.service.client.detecter(_contenu.text);
      if (mounted && trouve != null) setState(() => _langage = trouve);
    } on ErreurAPI catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    } finally {
      if (mounted) setState(() => _detectionEnCours = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    final vide = _contenu.text.trim().isEmpty;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Mesures.largeurMax),
            child: Padding(
              padding: const EdgeInsets.all(Mesures.marge),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: _saisie(gb)),
                  const SizedBox(height: Mesures.ecart),
                  _options(gb),
                  if (_erreur != null) ...[
                    const SizedBox(height: Mesures.ecart),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.warning_amber_rounded, size: 16, color: gb.danger),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(_erreur!,
                              style: TextStyle(fontSize: 13, color: gb.danger)),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: Mesures.ecart),
                  BoutonPrincipal(
                    key: const Key('bouton.creer'),
                    onPressed: vide || _occupe ? null : _creer,
                    child: _occupe
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Gb.surAccent),
                          )
                        : const Text('Chiffrer et créer le lien'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _saisie(Gb gb) => CarteDeVerre(
        marge: Mesures.ecart,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: TextField(
                key: const Key('champ.contenu'),
                controller: _contenu,
                maxLines: null,
                expands: true,
                textAlignVertical: TextAlignVertical.top,
                autocorrect: false,
                enableSuggestions: false,
                // Une police à chasse fixe : c'est du code ou de la configuration neuf
                // fois sur dix, et l'alignement est ce qui le rend relisible.
                style: TextStyle(fontFamily: 'monospace', fontSize: 14, color: gb.encre),
                decoration: const InputDecoration(
                  hintText: 'Collez votre extrait ici…',
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  filled: false,
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ),
            Row(
              children: [
                Text(
                  _taille(),
                  style: TextStyle(fontSize: 12, color: gb.estompe),
                ),
                const Spacer(),
                if (_langage != null)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Text(_langage!,
                        style: TextStyle(fontSize: 12, color: gb.accentTexte)),
                  ),
              ],
            ),
          ],
        ),
      );

  String _taille() {
    final n = _contenu.text.length;
    if (n == 0) return '';
    return n < 1024 ? '$n o' : '${(n / 1024).toStringAsFixed(1)} Kio';
  }

  Widget _options(Gb gb) => CarteDeVerre(
        marge: Mesures.ecart,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InkWell(
              onTap: () => setState(() => _optionsOuvertes = !_optionsOuvertes),
              child: Row(
                children: [
                  Expanded(child: Libelle('Expire dans $_expiration')),
                  Icon(
                    _optionsOuvertes ? Icons.expand_less : Icons.expand_more,
                    size: 20,
                    color: gb.estompe,
                  ),
                ],
              ),
            ),
            if (_optionsOuvertes) ...[
              const SizedBox(height: Mesures.ecartChamps),
              _menu(
                gb,
                'Expiration',
                _expiration,
                _expirations.keys.toList(),
                (v) => setState(() => _expiration = v!),
              ),
              const SizedBox(height: Mesures.ecartChamps),
              _menuLangage(gb),
              const SizedBox(height: Mesures.ecartChamps),
              _bascule(
                gb,
                'Brûler après lecture',
                'Le paste est détruit par la première lecture — y compris si c\'est la vôtre.',
                _brule,
                (v) => setState(() => _brule = v),
              ),
              _bascule(
                gb,
                'Compresser (gzip)',
                'Compressé avant chiffrement, comme sur le web. Utile au-delà de quelques Kio.',
                _compresser,
                (v) => setState(() => _compresser = v),
              ),
            ],
          ],
        ),
      );

  Widget _menu(Gb gb, String titre, String valeur, List<String> choix,
          ValueChanged<String?> auChangement) =>
      Champ(
        titre: titre,
        enfant: DropdownButtonFormField<String>(
          initialValue: valeur,
          isExpanded: true,
          dropdownColor: gb.surface,
          style: TextStyle(color: gb.encre, fontSize: 14),
          items: [
            for (final c in choix) DropdownMenuItem(value: c, child: Text(c)),
          ],
          onChanged: auChangement,
        ),
      );

  Widget _menuLangage(Gb gb) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Libelle('Langage'),
              const Spacer(),
              // Le libellé dit ce que le geste coûte. « Détecter » tout court laisserait
              // croire que ça se passe sur l'appareil.
              TextButton(
                onPressed: _contenu.text.trim().length < 20 || _detectionEnCours
                    ? null
                    : _detecter,
                style: TextButton.styleFrom(
                  foregroundColor: gb.accentTexte,
                  textStyle: const TextStyle(fontSize: 12),
                  minimumSize: const Size(0, 28),
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                ),
                child: Text(_detectionEnCours
                    ? 'Envoi…'
                    : 'Deviner (envoie le texte en clair)'),
              ),
            ],
          ),
          const SizedBox(height: Mesures.ecartLibelle),
          DropdownButtonFormField<String?>(
            initialValue: _langage,
            isExpanded: true,
            dropdownColor: gb.surface,
            style: TextStyle(color: gb.encre, fontSize: 14),
            items: [
              const DropdownMenuItem<String?>(value: null, child: Text('Aucun')),
              for (final l in langagesConnus)
                DropdownMenuItem<String?>(value: l, child: Text(l)),
            ],
            onChanged: (v) => setState(() => _langage = v),
          ),
        ],
      );

  Widget _bascule(Gb gb, String titre, String explication, bool valeur,
          ValueChanged<bool> auChangement) =>
      Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(titre, style: TextStyle(fontSize: 14, color: gb.encre)),
                  Text(explication,
                      style: TextStyle(fontSize: 12, color: gb.estompe, height: 1.3)),
                ],
              ),
            ),
            Switch(value: valeur, onChanged: auChangement),
          ],
        ),
      );
}

/// Le presse-papiers, avec la seule précaution qui compte : ce qu'on y met est un lien qui
/// contient une clé, et tout ce qui tourne sur l'appareil peut le lire.
Future<void> copier(BuildContext context, String texte, String quoi) async {
  await Clipboard.setData(ClipboardData(text: texte));
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$quoi copié.'), duration: const Duration(seconds: 2)),
    );
  }
}

/// Une entrée fraîchement créée, pour l'écran suivant.
typedef EntreeCreee = EntreeHistorique;
