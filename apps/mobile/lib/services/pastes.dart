import 'dart:convert';
import 'dart:io' show GZipCodec;

import '../src/rust/api/coeur.dart' as coeur;
import 'api.dart';
import 'historique.dart';

/// Le contenu d'un paste, une fois ouvert.
class PasteOuvert {
  const PasteOuvert({
    required this.clair,
    required this.meta,
  });

  final String clair;
  final PasteDistant meta;
}

/// Ce qui empêche d'ouvrir un paste, dit dans les termes de l'utilisateur.
class PasteIllisible implements Exception {
  const PasteIllisible(this.raison, {this.motDePasseRequis = false});

  final String raison;

  /// Le paste est protégé par un mot de passe et l'application ne sait pas encore les
  /// dériver. C'est une limite connue, pas un échec de déchiffrement, et l'écran doit les
  /// distinguer : « clé refusée » et « je ne sais pas faire » n'appellent pas le même geste.
  final bool motDePasseRequis;

  @override
  String toString() => raison;
}

/// Créer, lire et révoquer un paste — la chaîne complète, en un endroit.
///
/// **Aucune cryptographie ici.** Les trois lignes qui comptent appellent le cœur Rust
/// (`coeur.sceller`, `coeur.ouvrir`, `coeur.composerFragment`) ; le reste est du transport
/// et du gzip. Le partage du travail est celui de la suite : le cœur scelle, la plateforme
/// range, le service enchaîne.
class ServicePastes {
  ServicePastes({required this.client, required this.historique});

  final ClientGhostbit client;
  final Historique historique;

  /// Crée un paste et rend son lien complet, fragment compris.
  ///
  /// L'ordre des opérations n'est pas indifférent : on **compresse, puis on chiffre**. Le
  /// faire dans l'autre sens ne compresserait rien — du chiffré est incompressible par
  /// construction — et surtout, c'est l'ordre qu'applique `static/e2e.js`. L'inverser
  /// produirait des pastes que le visualiseur web ne saurait pas rouvrir.
  Future<EntreeHistorique> creer(
    String clair, {
    String? langage,
    int? expireDansSecondes,
    bool brule = false,
    int? vuesMax,
    bool compresser = false,
  }) async {
    final octets = utf8.encode(clair);
    final charge = compresser ? GZipCodec().encode(octets) : octets;

    final enveloppe = await coeur.sceller(clair: charge);
    final cree = await client.creer(
      contenu: enveloppe.chiffre,
      nonce: enveloppe.nonce,
      langage: langage,
      expireDansSecondes: expireDansSecondes,
      brule: brule,
      vuesMax: vuesMax,
      compresse: compresser,
    );

    // Le fragment est composé par le cœur, pas ici : c'est le format de ghostbit, et
    // deux copies d'un format divergent sans que rien ne le signale.
    final fragment = await coeur.composerFragment(
      cle: enveloppe.cle,
      jeton: cree.jetonDeSuppression,
    );

    final entree = EntreeHistorique(
      id: cree.id,
      lien: '${cree.url}#$fragment',
      jetonDeSuppression: cree.jetonDeSuppression,
      creeLe: DateTime.now(),
      langage: langage,
      expireLe: expireDansSecondes == null
          ? null
          : DateTime.now().add(Duration(seconds: expireDansSecondes)),
      brule: brule,
      vuesMax: vuesMax,
      octets: octets.length,
    );
    await historique.ajouter(entree);
    return entree;
  }

  /// Ouvre un paste depuis son lien complet.
  ///
  /// **Cet appel consomme une vue** — voir [ClientGhostbit.lire]. Il n'est donc jamais
  /// déclenché par l'affichage d'une liste, seulement par un geste explicite.
  Future<PasteOuvert> ouvrirDepuisLien(String lien) async {
    final uri = Uri.tryParse(lien.trim());
    if (uri == null || uri.pathSegments.isEmpty) {
      throw const PasteIllisible("Ce lien n'a pas la forme d'un paste ghostbit.");
    }
    final id = uri.pathSegments.last;

    // `Uri.fragment` décode les échappements de pourcentage ; on relit donc la chaîne
    // brute. Une clé base64url n'en contient normalement pas, mais un lien passé par un
    // messagerie qui ré-encode `~` en `%7E` couperait au mauvais endroit — et le message
    // d'erreur accuserait la clé.
    final diese = lien.indexOf('#');
    if (diese < 0) {
      throw const PasteIllisible(
        'Ce lien ne porte pas de clé. Le fragment, après le #, est la seule chose qui '
        'permette de déchiffrer : sans lui personne ne peut lire ce paste, pas même le serveur.',
      );
    }
    final fragment = await coeur.analyserFragment(fragment: lien.substring(diese + 1));

    final meta = await client.lire(id);

    if (meta.protegeParMotDePasse) {
      throw const PasteIllisible(
        'Ce paste est protégé par un mot de passe. L\'application ne sait pas encore '
        'dériver ces clés-là : ouvrez-le dans le visualiseur web.',
        motDePasseRequis: true,
      );
    }
    if (fragment.cle.isEmpty) {
      throw const PasteIllisible(
        'Le fragment de ce lien ne contient pas de clé.',
      );
    }

    final Uint8ListLike octets;
    try {
      octets = await coeur.ouvrir(
        cle: fragment.cle,
        nonce: meta.nonce,
        chiffre: meta.contenu,
      );
    } catch (_) {
      // L'étiquette d'authentification d'AES-GCM ne connaît pas le demi-succès : soit le
      // contenu est exactement celui qui a été scellé, soit rien ne sort. Une clé fausse
      // et un contenu altéré échouent de la même façon, et on ne peut pas les distinguer.
      throw const PasteIllisible(
        'La clé de ce lien n\'ouvre pas ce paste. Le lien a peut-être été tronqué en '
        'chemin : le fragment, après le #, est souvent la partie qu\'un message coupe.',
      );
    }

    final brut = meta.compresse ? GZipCodec().decode(octets) : octets;
    try {
      return PasteOuvert(clair: utf8.decode(brut), meta: meta);
    } on FormatException {
      throw const PasteIllisible(
        'Ce paste s\'est déchiffré, mais son contenu n\'est pas du texte.',
      );
    }
  }

  /// Révoque un paste, et le note dans l'historique.
  ///
  /// Le serveur répond 403 aussi bien pour un jeton faux que pour un paste déjà disparu :
  /// on marque révoqué dans les deux cas, parce que dans les deux cas le paste n'est plus
  /// lisible. Prétendre distinguer serait inventer une information qu'on n'a pas.
  Future<void> revoquer(EntreeHistorique entree) async {
    try {
      await client.supprimer(entree.id, entree.jetonDeSuppression);
    } on ErreurAPI catch (e) {
      if (!e.refusOuDisparu) rethrow;
    }
    await historique.revoquer(entree.id);
  }
}

/// `coeur.ouvrir` rend un `Uint8List` ; l'alias garde la signature lisible sans importer
/// `dart:typed_data` pour un seul nom.
typedef Uint8ListLike = List<int>;
