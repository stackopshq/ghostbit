import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Un paste créé depuis cet appareil.
///
/// ─── Ce qui est gardé, et pourquoi c'est délicat ───
///
/// L'entrée porte le **lien complet, fragment compris** — donc la clé de déchiffrement et
/// le jeton de suppression. C'est ce qui rend l'historique utile : sans la clé on ne
/// rouvre pas son propre paste, et sans le jeton on ne peut plus le révoquer. Le serveur
/// n'a ni l'une ni l'autre et ne peut pas les redonner ; perdre cette entrée, c'est perdre
/// le paste pour tout le monde, y compris son auteur.
///
/// Il s'ensuit deux choses :
///
/// 1. **l'historique vit dans le trousseau**, jamais dans les préférences — voir
///    [Historique] ;
/// 2. **le contenu n'y est pas.** Pas d'aperçu, pas de première ligne, pas de titre tiré
///    du texte. Un aperçu serait du clair au repos sur l'appareil, ce que ni le web ni le
///    CLI ne font, et il suffirait d'une capture d'écran de la liste pour rendre le
///    chiffrement décoratif. La liste se lit donc par langage, taille et date.
class EntreeHistorique {
  const EntreeHistorique({
    required this.id,
    required this.lien,
    required this.jetonDeSuppression,
    required this.creeLe,
    this.langage,
    this.expireLe,
    this.brule = false,
    this.vuesMax,
    this.octets = 0,
    this.revoque = false,
  });

  factory EntreeHistorique.depuisJson(Map<String, dynamic> j) => EntreeHistorique(
        id: j['id'] as String,
        lien: j['lien'] as String,
        jetonDeSuppression: j['jeton'] as String,
        creeLe: DateTime.parse(j['cree'] as String),
        langage: j['langage'] as String?,
        expireLe: j['expire'] == null ? null : DateTime.parse(j['expire'] as String),
        brule: j['brule'] as bool? ?? false,
        vuesMax: j['vuesMax'] as int?,
        octets: j['octets'] as int? ?? 0,
        revoque: j['revoque'] as bool? ?? false,
      );

  final String id;
  final String lien;
  final String jetonDeSuppression;
  final DateTime creeLe;
  final String? langage;
  final DateTime? expireLe;
  final bool brule;
  final int? vuesMax;
  final int octets;

  /// Révoqué depuis cet appareil. On garde la ligne un instant plutôt que de la faire
  /// disparaître : voir [Historique.revoquer].
  final bool revoque;

  /// Expiré d'après ce qu'on sait localement.
  ///
  /// C'est une **estimation**, pas une vérité : seul le serveur sait si le paste existe
  /// encore, et le lui demander le consommerait. Un paste peut donc être marqué vivant ici
  /// et avoir déjà brûlé là-bas. L'écran doit dire « d'après cet appareil », pas affirmer.
  bool get expireProbablement =>
      expireLe != null && expireLe!.isBefore(DateTime.now());

  Map<String, dynamic> versJson() => {
        'id': id,
        'lien': lien,
        'jeton': jetonDeSuppression,
        'cree': creeLe.toIso8601String(),
        'langage': langage,
        'expire': expireLe?.toIso8601String(),
        'brule': brule,
        'vuesMax': vuesMax,
        'octets': octets,
        'revoque': revoque,
      };

  EntreeHistorique copieAvec({bool? revoque}) => EntreeHistorique(
        id: id,
        lien: lien,
        jetonDeSuppression: jetonDeSuppression,
        creeLe: creeLe,
        langage: langage,
        expireLe: expireLe,
        brule: brule,
        vuesMax: vuesMax,
        octets: octets,
        revoque: revoque ?? this.revoque,
      );
}

/// Où l'application range ce qu'elle a créé.
///
/// **Dans le trousseau, et pas ailleurs.** Chaque entrée contient une clé de
/// déchiffrement ; `shared_preferences` écrit un plist ou un XML en clair, lisible par
/// toute sauvegarde non chiffrée de l'appareil. Le trousseau iOS et le Keystore Android
/// sont les seuls endroits où ranger du matériel de clé, et le cœur commun s'arrête
/// justement à cette frontière : le rangement est une politique de plateforme.
///
/// **Rien n'est synchronisé.** L'historique du CLI ne l'est pas non plus (`gbit list` est
/// local, et son README le dit). Une synchronisation remettrait les clés en circulation,
/// ce qui est exactement ce que le fragment évite.
class Historique {
  Historique({FlutterSecureStorage? coffre})
      : _coffre = coffre ??
            const FlutterSecureStorage(
              // Sans `first_unlock`, une entrée écrite pendant que l'appareil est
              // verrouillé est illisible : la feuille de partage, qui peut tourner
              // écran verrouillé, perdrait le jeton du paste qu'elle vient de créer.
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock,
                // Le groupe d'accès au trousseau, partagé avec la feuille de partage iOS.
                // Sans lui, un paste créé depuis la feuille serait invisible et
                // **irrévocable** depuis l'application : les deux processus écriraient
                // chacun dans son coin, sans erreur d'aucun côté.
                groupId: 'group.dev.ghostbit',
                // Explicite, alors que c'est déjà la valeur par défaut du paquet. Le côté
                // Swift doit inscrire exactement le même `kSecAttrService`, et une valeur
                // qu'on lit dans les deux fichiers se compare ; une valeur implicite d'un
                // côté et écrite de l'autre ne se compare pas.
                accountName: 'flutter_secure_storage_service',
              ),
              aOptions: AndroidOptions(
                // **`resetOnError` vaut `true` par défaut dans la version 11**, et ce
                // défaut est inacceptable ici. Il efface définitivement tout le contenu du
                // magasin dès qu'une lecture échoue — une rotation de clé du Keystore
                // après une restauration de sauvegarde, par exemple.
                //
                // Pour la plupart des applications c'est une gêne : on se reconnecte.
                // Ici, ces octets sont la **seule copie existante** des clés de
                // déchiffrement et des jetons de suppression ; le serveur ne les a pas et
                // ne peut pas les redonner. Les effacer, c'est rendre définitivement
                // illisibles tous les pastes de l'utilisateur, en silence, à la place
                // d'une erreur qu'il aurait pu signaler.
                resetOnError: false,
                // La migration entre algorithmes garde une sauvegarde plutôt que de
                // réécrire en place : même raison, il n'y a pas de seconde chance.
                migrateWithBackup: true,
              ),
            );

  final FlutterSecureStorage _coffre;

  /// La clé du trousseau. Partagée avec l'extension de partage iOS par groupe
  /// d'applications : les deux processus écrivent dans le même historique, sans quoi un
  /// paste créé depuis la feuille de partage serait irrévocable depuis l'application.
  static const _cle = 'ghostbit.historique.v1';

  Future<List<EntreeHistorique>> tout() async {
    final brut = await _coffre.read(key: _cle);
    if (brut == null || brut.isEmpty) return const [];
    try {
      final liste = jsonDecode(brut) as List<dynamic>;
      return liste
          .map((e) => EntreeHistorique.depuisJson(e as Map<String, dynamic>))
          .toList()
        ..sort((a, b) => b.creeLe.compareTo(a.creeLe));
    } on FormatException {
      // Un historique illisible ne doit pas empêcher l'application de démarrer, et
      // surtout pas être écrasé en silence : on rend vide et on laisse l'octet en place,
      // pour qu'une version ultérieure puisse encore le récupérer.
      return const [];
    }
  }

  Future<void> ajouter(EntreeHistorique entree) async {
    final liste = await tout();
    await _ecrire([entree, ...liste.where((e) => e.id != entree.id)]);
  }

  /// Marque une entrée révoquée **sans la retirer**.
  ///
  /// La faire disparaître serait plus propre et moins honnête : l'utilisateur ne saurait
  /// plus si la suppression a eu lieu ou si la ligne s'est perdue. Elle reste barrée
  /// jusqu'à ce qu'il l'efface lui-même, ce qui est un second geste et non le même.
  Future<void> revoquer(String id) async {
    final liste = await tout();
    await _ecrire([
      for (final e in liste) e.id == id ? e.copieAvec(revoque: true) : e,
    ]);
  }

  /// Retire l'entrée de l'appareil. **Ne supprime pas le paste** : sans le jeton, plus
  /// personne ne pourra le révoquer avant son expiration. L'écran doit le dire.
  Future<void> oublier(String id) async {
    final liste = await tout();
    await _ecrire(liste.where((e) => e.id != id).toList());
  }

  Future<void> viderTout() => _coffre.delete(key: _cle);

  Future<void> _ecrire(List<EntreeHistorique> liste) => _coffre.write(
        key: _cle,
        value: jsonEncode([for (final e in liste) e.versJson()]),
      );
}
