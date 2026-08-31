import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'ecrans/creation.dart';
import 'ecrans/entree.dart';
import 'ecrans/historique.dart';
import 'ecrans/lecture.dart';
import 'services/api.dart';
import 'services/historique.dart';
import 'services/pastes.dart';
import 'services/reglages.dart';
import 'src/rust/frb_generated.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Charge la bibliothèque du cœur avant le premier écran. Sans ce point d'entrée, le
  // premier appel de chiffrement échouerait sur une bibliothèque non initialisée, à
  // l'endroit le plus difficile à diagnostiquer.
  await RustLib.init();
  runApp(Application(reglages: await Reglages.ouvrir()));
}

class Application extends StatefulWidget {
  const Application({super.key, required this.reglages});

  final Reglages reglages;

  @override
  State<Application> createState() => _ApplicationState();
}

class _ApplicationState extends State<Application> {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GhostBit',
      debugShowCheckedModeBanner: false,
      theme: themeGhostbit(Brightness.light),
      darkTheme: themeGhostbit(Brightness.dark),
      // Le produit suit le thème du système, comme sa page web (`static/theme.js`).
      themeMode: ThemeMode.system,
      home: widget.reglages.configure
          ? Coquille(reglages: widget.reglages)
          : EcranEntree(
              reglages: widget.reglages,
              quandPret: () => setState(() {}),
            ),
    );
  }
}

/// La coquille de l'application : créer, l'historique, et ouvrir un lien reçu.
class Coquille extends StatefulWidget {
  const Coquille({super.key, required this.reglages});

  final Reglages reglages;

  @override
  State<Coquille> createState() => _CoquilleState();
}

class _CoquilleState extends State<Coquille> {
  /// Le canal par lequel l'activité Android remet le texte d'un `ACTION_SEND`.
  ///
  /// Sur Android, l'intention de partage peut viser **l'activité Flutter elle-même** : il
  /// n'y a pas de processus séparé au budget contraint, donc pas de raison d'écrire un
  /// second client. C'est l'écart avec iOS, où la feuille de partage est une extension
  /// dans laquelle Flutter ne tient pas, et où le partage passe donc par du Swift appelant
  /// le cœur par UniFFI.
  static const _canal = MethodChannel('dev.ghostbit/partage');

  late final ServicePastes _service;
  int _onglet = 0;
  String? _texteRecu;

  @override
  void initState() {
    super.initState();
    _service = ServicePastes(
      client: ClientGhostbit(base: Uri.parse(widget.reglages.serveur!)),
      historique: Historique(),
    );
    _canal.setMethodCallHandler(_recevoirLePartage);
    // L'intention qui a lancé l'application : elle est déjà arrivée avant que Dart ne
    // pose son écouteur, il faut donc aussi aller la chercher.
    _canal.invokeMethod<String>('partageInitial').then((texte) {
      if (texte != null && texte.isNotEmpty) _ouvrirAvec(texte);
    }).catchError((_) => null); // iOS n'implémente pas ce canal.
  }

  Future<dynamic> _recevoirLePartage(MethodCall appel) async {
    if (appel.method == 'partage' && appel.arguments is String) {
      _ouvrirAvec(appel.arguments as String);
    }
    return null;
  }

  /// Un texte partagé : si c'est un lien de paste, on l'ouvre ; sinon on en crée un.
  ///
  /// La distinction évite le geste absurde le plus probable — partager un lien ghostbit
  /// vers ghostbit produirait un paste chiffré contenant une URL.
  void _ouvrirAvec(String texte) {
    final t = texte.trim();
    final estUnLien = t.startsWith(widget.reglages.serveur!) && t.contains('#');
    if (estUnLien) {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => EcranLecture(service: _service, lien: t)),
      );
    } else {
      setState(() {
        _texteRecu = texte;
        _onglet = 0;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final gb = Gb.of(context);
    return FondGhost(
      child: Scaffold(
        appBar: AppBar(
          title: Text(
            'GhostBit',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              // La marque rayonne, et elle seule. L'ombre suit les glyphes : une ombre de
              // boîte peindrait un rectangle violet derrière les lettres.
              shadows: gb.haloDeTexte(0.7),
            ),
          ),
          actions: [
            IconButton(
              tooltip: 'Ouvrir un lien',
              icon: const Icon(Icons.link),
              onPressed: _demanderUnLien,
            ),
          ],
        ),
        body: IndexedStack(
          index: _onglet,
          children: [
            // La clé force la reconstruction quand un partage arrive, pour que le champ
            // s'ouvre rempli plutôt que de garder son contenu précédent.
            EcranCreation(
              key: ValueKey(_texteRecu),
              service: _service,
              texteInitial: _texteRecu,
            ),
            EcranHistorique(service: _service),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _onglet,
          backgroundColor: gb.surface.withValues(alpha: 0.9),
          onDestinationSelected: (i) => setState(() => _onglet = i),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.add_outlined),
              selectedIcon: Icon(Icons.add),
              label: 'Créer',
            ),
            NavigationDestination(
              icon: Icon(Icons.history_outlined),
              selectedIcon: Icon(Icons.history),
              label: 'Historique',
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _demanderUnLien() async {
    final controleur = TextEditingController();
    final gb = Gb.of(context);
    final lien = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        backgroundColor: gb.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Mesures.rayonCarte),
        ),
        title: Text('Ouvrir un lien', style: TextStyle(color: gb.encre, fontSize: 18)),
        content: TextField(
          controller: controleur,
          autofocus: true,
          autocorrect: false,
          decoration: const InputDecoration(hintText: 'https://…/abc123#clé~jeton'),
          onSubmitted: (v) => Navigator.of(c).pop(v),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(c).pop(),
            child: Text('Annuler', style: TextStyle(color: gb.estompe)),
          ),
          TextButton(
            onPressed: () => Navigator.of(c).pop(controleur.text),
            child: Text('Ouvrir', style: TextStyle(color: gb.accentTexte)),
          ),
        ],
      ),
    );
    if (lien != null && lien.trim().isNotEmpty && mounted) {
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => EcranLecture(service: _service, lien: lien.trim()),
        ),
      );
    }
  }
}
