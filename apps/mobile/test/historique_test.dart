import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostbit/services/historique.dart';

/// L'historique : ce qu'il garde, ce qu'il perd, et la différence entre les deux gestes
/// qui le vident.
///
/// Chaque entrée contient une clé de déchiffrement et un jeton de suppression dont le
/// serveur n'a pas de copie. Se tromper ici ne produit pas un bogue d'affichage : ça rend
/// des pastes définitivement inouvrables.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Historique historique;

  EntreeHistorique entree(String id, {DateTime? cree, DateTime? expire}) =>
      EntreeHistorique(
        id: id,
        lien: 'https://p.ch/$id#cle_de_$id~jeton_de_$id',
        jetonDeSuppression: 'jeton_de_$id',
        creeLe: cree ?? DateTime.now(),
        expireLe: expire,
      );

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    historique = Historique();
  });

  test('un historique neuf est vide, et ne lève pas', () async {
    expect(await historique.tout(), isEmpty);
  });

  test('garde le lien entier, fragment compris', () async {
    await historique.ajouter(entree('abc'));
    final relu = (await historique.tout()).single;
    // Sans le fragment, l'entrée est un identifiant sans clé : le paste devient
    // inouvrable, y compris par celui qui l'a créé.
    expect(relu.lien, contains('#'));
    expect(relu.lien, contains('cle_de_abc'));
    expect(relu.jetonDeSuppression, 'jeton_de_abc');
  });

  test('rend les entrées de la plus récente à la plus ancienne', () async {
    final vieux = DateTime.now().subtract(const Duration(days: 2));
    await historique.ajouter(entree('vieux', cree: vieux));
    await historique.ajouter(entree('neuf'));
    expect([for (final e in await historique.tout()) e.id], ['neuf', 'vieux']);
  });

  test('réajouter le même identifiant ne le duplique pas', () async {
    await historique.ajouter(entree('abc'));
    await historique.ajouter(entree('abc'));
    expect(await historique.tout(), hasLength(1));
  });

  group('les deux gestes qui vident, et qu\'il ne faut pas confondre', () {
    test('révoquer garde la ligne, barrée', () async {
      await historique.ajouter(entree('abc'));
      await historique.revoquer('abc');
      final liste = await historique.tout();
      // La faire disparaître serait plus propre et moins honnête : on ne saurait plus si
      // la suppression a eu lieu ou si la ligne s'est perdue.
      expect(liste, hasLength(1));
      expect(liste.single.revoque, isTrue);
      // Et le jeton reste : rien n'oblige à le jeter, et le garder permet de réessayer si
      // la requête avait échoué.
      expect(liste.single.jetonDeSuppression, isNotEmpty);
    });

    test('oublier retire la ligne — et avec elle la clé', () async {
      await historique.ajouter(entree('abc'));
      await historique.oublier('abc');
      expect(await historique.tout(), isEmpty);
    });
  });

  group('l\'expiration affichée est une estimation, pas une vérité', () {
    test('une date passée marque le paste comme probablement expiré', () async {
      final e = entree('abc', expire: DateTime.now().subtract(const Duration(hours: 1)));
      expect(e.expireProbablement, isTrue);
    });

    test('sans date d\'expiration, rien n\'est supposé', () async {
      // Le cas où une mutation naïve — « pas de date, donc expiré » — se verrait.
      expect(entree('abc').expireProbablement, isFalse);
    });

    test('une date future ne marque rien', () async {
      final e = entree('abc', expire: DateTime.now().add(const Duration(hours: 1)));
      expect(e.expireProbablement, isFalse);
    });
  });

  test('un historique corrompu rend une liste vide sans écraser l\'octet', () async {
    // Un magasin illisible ne doit pas empêcher l'application de démarrer, et surtout pas
    // être remplacé en silence : une version ultérieure pourrait encore le récupérer.
    FlutterSecureStorage.setMockInitialValues({
      'ghostbit.historique.v1': 'ceci n\'est pas du JSON',
    });
    final abime = Historique();
    expect(await abime.tout(), isEmpty);
    expect(
      await const FlutterSecureStorage().read(key: 'ghostbit.historique.v1'),
      isNotNull,
      reason: 'l\'historique illisible a été effacé au lieu d\'être conservé',
    );
  });
}
