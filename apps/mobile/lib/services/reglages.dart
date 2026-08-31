import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// L'adresse de l'instance, et rien d'autre.
///
/// Ghostbit n'a **ni compte ni session** : il n'y a donc ni jeton ni identité à ranger, et
/// ce réglage n'est pas un secret — c'est un nom d'hôte. Il vit dans les préférences
/// ordinaires, tandis que l'historique vit dans le trousseau, et la différence est
/// délibérée : mélanger les deux ferait passer une clé de déchiffrement pour un réglage.
///
/// Le produit est fait pour être auto-hébergé. L'adresse est donc **demandée**, pas
/// devinée : coder `https://ghostbit.dev` en dur enverrait chez un tiers les pastes de
/// quelqu'un qui fait tourner sa propre instance, en silence et une seule fois suffit.
class Reglages {
  Reglages(this._prefs);

  static const _cleServeur = 'ghostbit.serveur';

  static Future<Reglages> ouvrir() async => Reglages(await SharedPreferences.getInstance());

  final SharedPreferences _prefs;

  String? get serveur => _prefs.getString(_cleServeur);

  bool get configure => (serveur ?? '').isNotEmpty;

  /// Le canal qui publie l'adresse dans le conteneur du groupe d'applications iOS.
  ///
  /// `shared_preferences` écrit dans les préférences propres à l'application ; la feuille
  /// de partage est un **processus séparé** qui n'y a aucun accès. Sans cette publication,
  /// elle ne saurait pas où poster. Android n'en a pas besoin : le partage y arrive dans
  /// l'activité Flutter elle-même, qui lit les mêmes préférences.
  static const _canalGroupe = MethodChannel('dev.ghostbit/groupe');

  Future<void> poserLeServeur(String valeur) async {
    final adresse = normaliser(valeur);
    await _prefs.setString(_cleServeur, adresse);
    try {
      await _canalGroupe.invokeMethod<void>('publierLeServeur', adresse);
    } on MissingPluginException {
      // Android et les tests n'implémentent pas ce canal, et c'est normal : l'absence de
      // conteneur partagé n'est pas un échec du réglage lui-même. L'attraper précisément
      // — plutôt qu'un `catch` général — évite d'avaler une vraie erreur de plateforme.
    }
  }

  /// Ramène ce que quelqu'un tape à une base d'URL utilisable.
  ///
  /// Le cas qui compte est l'absence de schéma : « paste.exemple.ch » saisi tel quel
  /// donnerait une `Uri` relative, et la première requête partirait vers un chemin du
  /// système de fichiers avec un message qui n'oriente vers rien. On complète en
  /// **https**, jamais en http : ce produit refuse de chiffrer hors d'un contexte sûr,
  /// exactement comme sa page web.
  static String normaliser(String entree) {
    var s = entree.trim();
    if (s.isEmpty) return s;
    if (!s.contains('://')) s = 'https://$s';
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
    return s;
  }

  /// Une adresse est-elle utilisable ? Rendue en clair pour que l'écran puisse dire
  /// *pourquoi* il refuse, plutôt que de griser un bouton sans explication.
  static String? refus(String entree) {
    final s = normaliser(entree);
    if (s.isEmpty) return 'Indiquez l\'adresse de votre instance.';
    final uri = Uri.tryParse(s);
    if (uri == null || uri.host.isEmpty) return 'Cette adresse n\'est pas lisible.';
    if (uri.scheme == 'http' && !_estLocal(uri.host)) {
      // Le web refuse de chiffrer hors contexte sûr et le dit ; l'application applique la
      // même règle plutôt que d'envoyer du chiffré sur un canal que n'importe qui relit.
      return 'En clair (http), le lien voyagerait à découvert. Utilisez https.';
    }
    if (uri.scheme != 'http' && uri.scheme != 'https') {
      return 'Seul https est accepté.';
    }
    return null;
  }

  /// Une instance de développement tourne sur la machine, où http est sans conséquence —
  /// c'est aussi ce que fait la page web, qui propose de basculer sur localhost.
  static bool _estLocal(String hote) =>
      hote == 'localhost' || hote == '127.0.0.1' || hote == '::1';
}
