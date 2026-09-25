import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostbit/services/api.dart';
import 'package:ghostbit/services/historique.dart';
import 'package:ghostbit/services/pastes.dart';

/// Ce qu'un lien reçu de l'extérieur doit produire, et surtout ce qu'il ne doit pas dire.
///
/// Depuis que l'application réclame les liens de `ghostbit.dev` et de
/// `bit.ghostsuite.cloud` (voir `AndroidManifest.xml` et `Runner.entitlements`), un lien
/// peut arriver d'un hôte que **cet appareil-ci n'a pas configuré** : la suite en déploie
/// deux, et c'est le serveur GhostPass qui choisit chez lequel il relaie le partage.
///
/// Sans contrôle, l'identifiant partait vers le serveur configuré, qui ne le connaît pas,
/// et l'écran annonçait « ce paste n'existe plus ». C'est un mensonge coûteux : il est
/// définitif, il envoie redemander un lien à l'expéditeur, et le paste est parfaitement
/// vivant à deux réglages de là.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late ServicePastes service;

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    service = ServicePastes(
      client: ClientGhostbit(base: Uri.parse('https://bit.ghostsuite.cloud')),
      historique: Historique(),
    );
  });

  test("un lien d'un autre hôte nomme les deux hôtes, et n'annonce pas une disparition",
      () async {
    // Aucun appel réseau ne doit partir : le contrôle passe avant `client.lire`. Un test
    // qui laisserait passer la requête échouerait ici sur le réseau, pas sur l'assertion,
    // et dirait donc autre chose que ce qu'il croit dire.
    final erreur = await service
        .ouvrirDepuisLien('https://ghostbit.dev/abc123#cle~jeton')
        .then<Object?>((_) => null, onError: (Object e) => e);

    expect(erreur, isA<PasteIllisible>());
    final raison = (erreur! as PasteIllisible).raison;
    expect(raison, contains('ghostbit.dev'));
    expect(raison, contains('bit.ghostsuite.cloud'));
    // Le mensonge d'avant, explicitement absent.
    expect(raison, isNot(contains("n'existe plus")));
    expect(raison, isNot(contains('expiré')));
  });

  test("un lien sans clé est distingué d'un lien vers le mauvais hôte", () async {
    // Même hôte que le serveur configuré, mais pas de fragment : c'est l'autre échec, et
    // les deux n'appellent pas le même geste — redemander le lien entier d'un côté,
    // changer de serveur de l'autre. Les confondre enverrait faire le mauvais.
    final erreur = await service
        .ouvrirDepuisLien('https://bit.ghostsuite.cloud/abc123')
        .then<Object?>((_) => null, onError: (Object e) => e);

    expect(erreur, isA<PasteIllisible>());
    final raison = (erreur! as PasteIllisible).raison;
    expect(raison, contains('fragment'));
    expect(raison, isNot(contains('réglages')));
  });

  test('un lien du serveur configuré passe le contrôle d\'hôte', () async {
    // Le pendant : un contrôle qui refuserait tout serait vert pour une mauvaise raison.
    // Celui-ci doit laisser passer, et l'échec doit alors venir d'ailleurs — ici du cœur
    // Rust, que ce test ne charge pas, ou du réseau. Ce qu'il ne doit pas contenir, c'est
    // le reproche d'hôte.
    final erreur = await service
        .ouvrirDepuisLien('https://bit.ghostsuite.cloud/abc123#cle~jeton')
        .then<Object?>((_) => null, onError: (Object e) => e);

    expect(
      erreur is PasteIllisible ? erreur.raison : '',
      isNot(contains('réglages')),
    );
  });
}
