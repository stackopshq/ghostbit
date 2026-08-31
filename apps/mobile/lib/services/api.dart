import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Ce que le serveur rend quand il refuse.
///
/// Deux formes coexistent — `{"detail": "…"}` pour les erreurs métier, et la liste de
/// validations de FastAPI pour un corps mal formé. Les confondre afficherait
/// « Instance of 'List' » à l'utilisateur. Le message est ce qu'il lira ; il mérite d'être
/// extrait, pas deviné.
class ErreurAPI implements Exception {
  ErreurAPI(this.statut, this.message);

  final int statut;
  final String message;

  /// Le serveur répond 403 aussi bien pour un jeton faux que pour un paste qui n'existe
  /// plus, **délibérément** : distinguer les deux laisserait énumérer les identifiants.
  /// L'application ne doit donc pas prétendre savoir lequel des deux c'est.
  bool get refusOuDisparu => statut == 403;

  bool get introuvable => statut == 404;

  @override
  String toString() => message;
}

/// Les métadonnées et le chiffré d'un paste, tels que le serveur les rend.
///
/// Aucun de ces champs n'est le contenu : `contenu` est du chiffré base64, et il le reste
/// jusqu'à ce que le cœur Rust l'ouvre.
class PasteDistant {
  const PasteDistant({
    required this.id,
    required this.contenu,
    required this.nonce,
    required this.langage,
    required this.creeLe,
    required this.expireLe,
    required this.brule,
    required this.vuesMax,
    required this.vues,
    required this.protegeParMotDePasse,
    required this.compresse,
    required this.kdf,
  });

  factory PasteDistant.depuisJson(Map<String, dynamic> j) => PasteDistant(
        id: j['id'] as String,
        contenu: j['content'] as String,
        nonce: j['nonce'] as String,
        langage: j['language'] as String?,
        creeLe: DateTime.fromMillisecondsSinceEpoch((j['created_at'] as int) * 1000),
        expireLe: j['expires_at'] == null
            ? null
            : DateTime.fromMillisecondsSinceEpoch((j['expires_at'] as int) * 1000),
        brule: j['burn'] as bool? ?? false,
        vuesMax: j['max_views'] as int?,
        vues: j['view_count'] as int? ?? 0,
        protegeParMotDePasse: j['has_password'] as bool? ?? false,
        compresse: j['compressed'] as bool? ?? false,
        kdf: j['kdf'] as String? ?? 'pbkdf2-sha256',
      );

  final String id;
  final String contenu;
  final String nonce;
  final String? langage;
  final DateTime creeLe;
  final DateTime? expireLe;
  final bool brule;
  final int? vuesMax;
  final int vues;
  final bool protegeParMotDePasse;
  final bool compresse;
  final String kdf;
}

/// Ce que rend la création : l'identifiant, et le jeton qui permettra de révoquer.
class PasteCree {
  const PasteCree({required this.id, required this.url, required this.jetonDeSuppression});

  final String id;
  final String url;

  /// Rendu **une seule fois**. Le serveur n'en garde que l'empreinte SHA-256 ; le perdre,
  /// c'est perdre la capacité de supprimer le paste avant son expiration.
  final String jetonDeSuppression;
}

/// Le client de l'API de ghostbit.
///
/// ─── Ce que cette classe ne fait pas, et c'est le point ───
///
/// **Elle ne chiffre ni ne déchiffre rien.** Elle ne voit que du base64 déjà scellé par le
/// cœur Rust. Aucune clé ne la traverse : `POST /api/v1/pastes` n'a pas de champ pour en
/// recevoir une, et lui en ajouter un serait la fin du modèle. C'est la même règle que
/// côté web, où le serveur refuse par principe un corps contenant du clair.
class ClientGhostbit {
  ClientGhostbit({required this.base, http.Client? client})
      : _client = client ?? http.Client();

  final Uri base;
  final http.Client _client;

  Uri _url(String chemin) => base.resolve(chemin);

  /// Crée un paste. `contenu` et `nonce` sont du base64 **standard** produit par le cœur ;
  /// le validateur du serveur décode en base64 strict et refuserait du base64url.
  Future<PasteCree> creer({
    required String contenu,
    required String nonce,
    String? langage,
    int? expireDansSecondes,
    bool brule = false,
    int? vuesMax,
    bool compresse = false,
  }) async {
    final reponse = await _client.post(
      _url('/api/v1/pastes'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'content': contenu,
        'nonce': nonce,
        'language': ?langage,
        'expires_in': ?expireDansSecondes,
        'burn': brule,
        'max_views': ?vuesMax,
        'compressed': compresse,
      }),
    );
    final corps = _decoder(reponse);
    return PasteCree(
      id: corps['id'] as String,
      url: corps['url'] as String,
      jetonDeSuppression: corps['delete_token'] as String,
    );
  }

  /// Lit un paste.
  ///
  /// **Cet appel compte comme une vue.** Un paste marqué « brûler après lecture » est
  /// détruit par cet appel-là, et un paste à vues limitées en consomme une. C'est pour ça
  /// que l'historique ne précharge rien : afficher une liste ne doit pas consommer les
  /// pastes qu'elle nomme. La règle vaut aussi pour un rafraîchissement à tirer, et c'est
  /// le genre de commodité qui détruirait les données de quelqu'un sans le prévenir.
  Future<PasteDistant> lire(String id) async {
    final reponse = await _client.get(_url('/api/v1/pastes/$id'));
    return PasteDistant.depuisJson(_decoder(reponse));
  }

  /// Révoque un paste. Le serveur répond 403 pour un jeton faux **comme** pour un paste
  /// déjà disparu ; l'appelant ne peut pas les distinguer, et ne doit pas le prétendre.
  Future<void> supprimer(String id, String jeton) async {
    final reponse = await _client.delete(
      _url('/api/v1/pastes/$id'),
      headers: {'X-Delete-Token': jeton},
    );
    if (reponse.statusCode != 204) _decoder(reponse);
  }

  /// Devine le langage d'un extrait.
  ///
  /// **Cette route reçoit du clair**, et c'est la seule. Le serveur ne le stocke pas, mais
  /// il le voit passer : l'appeler sur un secret revient à l'envoyer. Elle n'est donc
  /// jamais appelée d'office ici — c'est un geste explicite de l'utilisateur, et l'écran
  /// le dit.
  Future<String?> detecter(String clair) async {
    final reponse = await _client.post(
      _url('/api/v1/detect'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({'content': clair}),
    );
    return _decoder(reponse)['language'] as String?;
  }

  Map<String, dynamic> _decoder(http.Response reponse) {
    if (reponse.statusCode >= 200 && reponse.statusCode < 300) {
      if (reponse.body.isEmpty) return const {};
      return jsonDecode(utf8.decode(reponse.bodyBytes)) as Map<String, dynamic>;
    }
    throw ErreurAPI(reponse.statusCode, _message(reponse));
  }

  /// Extrait le message lisible des deux formes d'erreur du serveur.
  static String _message(http.Response reponse) {
    try {
      final corps = jsonDecode(utf8.decode(reponse.bodyBytes));
      final detail = corps is Map ? corps['detail'] : null;
      if (detail is String) return detail;
      // La forme de FastAPI : [{"loc": [...], "msg": "…", …}, …]. Sans ce cas, une erreur
      // de validation s'afficherait « Instance of 'List' ».
      if (detail is List && detail.isNotEmpty) {
        final premier = detail.first;
        if (premier is Map && premier['msg'] is String) return premier['msg'] as String;
      }
    } catch (_) {
      // Corps non-JSON — une page d'erreur du proxy, par exemple.
    }
    if (reponse.statusCode == 429) {
      return 'Trop de requêtes. Cette instance limite le rythme ; réessayez dans une minute.';
    }
    return 'Le serveur a répondu ${reponse.statusCode}.';
  }
}
