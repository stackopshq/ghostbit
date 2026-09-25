import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Le gzip de l'application se relit-il dans le navigateur, et réciproquement ?
///
/// ─── Pourquoi ce témoin existe séparément du chiffrement ───
///
/// La compression n'est pas de la cryptographie, et c'est précisément pour ça qu'elle est
/// dangereuse : elle a l'air sans conséquence, donc personne ne la croise. Or ghostbit
/// **compresse avant de chiffrer**, si bien qu'un gzip incompatible produit un paste qui se
/// déchiffre parfaitement et dont le contenu est illisible. L'erreur ne ressemble alors
/// pas à une erreur de compression : elle ressemble à une corruption.
///
/// Le côté navigateur, c'est `CompressionStream('gzip')` appelé par le vrai `e2e.js` ; le
/// côté application, c'est `GZipCodec` de `dart:io`. Ce sont deux implémentations
/// indépendantes, et rien d'autre ne vérifie qu'elles s'accordent.
///
/// ─── Le vecteur est produit à l'exécution, pas recopié ───
///
/// Un gzip figé dans un fichier de vecteurs prouverait que Dart relit un octet écrit un
/// jour, pas qu'il relit ce que le produit fabrique aujourd'hui. Le témoin appelle donc
/// Node pendant le test. Si Node manque, c'est un **échec** et non un test sauté : un
/// témoin qu'on saute est un témoin qui ne mesure rien, et il est vert.
void main() {
  const texte = 'server {\n  listen 443 ssl;\n}\n'
      'Des accents, pour éprouver l\'UTF-8 : é à ü ß 漢字\n';

  test('le gzip du navigateur se décompresse avec dart:io', () {
    final base64Gzip = _gzipDuNavigateur(texte);
    final octets = base64Decode(base64Gzip);

    // Le premier octet d'un flux gzip est 0x1f 0x8b. Un `deflate` brut, que produirait
    // `CompressionStream('deflate')`, ne les a pas : la distinction se voit ici et nulle
    // part ailleurs, parce que les deux se déchiffrent aussi bien.
    expect(octets[0], 0x1f, reason: 'ce n\'est pas un flux gzip');
    expect(octets[1], 0x8b, reason: 'ce n\'est pas un flux gzip');

    expect(utf8.decode(GZipCodec().decode(octets)), texte);
  });

  test('le gzip de dart:io se décompresse dans le navigateur', () {
    final compresse = GZipCodec().encode(utf8.encode(texte));
    final relu = _gunzipDuNavigateur(base64Encode(compresse));
    expect(relu, texte);
  });

  test('la compression réduit vraiment un contenu répétitif', () {
    // Sans ce cas, un « gzip » qui se contenterait de recopier ses octets passerait les
    // deux témoins ci-dessus : l'aller-retour serait juste des deux côtés.
    final repetitif = 'a' * 4096;
    final compresse = GZipCodec().encode(utf8.encode(repetitif));
    expect(compresse.length, lessThan(repetitif.length ~/ 4));
  });
}

/// Appelle le vrai `e2e.js` via Node, et rend le gzip en base64.
String _gzipDuNavigateur(String texte) => _node(
      ['temoins/gzip_navigateur.mjs', texte],
    );

/// Décompresse avec `DecompressionStream('gzip')`, l'API du navigateur.
String _gunzipDuNavigateur(String base64Gzip) => _node([
      '-e',
      '''
      const b = Buffer.from(process.argv[1], 'base64');
      const flux = new Blob([b]).stream().pipeThrough(new DecompressionStream('gzip'));
      new Response(flux).text().then((t) => process.stdout.write(t));
      ''',
      base64Gzip,
    ]);

String _node(List<String> arguments) {
  final resultat = Process.runSync('node', arguments, workingDirectory: _racineDuPaquet());
  if (resultat.exitCode != 0) {
    fail(
      'Node a échoué (${resultat.exitCode}) — ce témoin ne peut pas se passer de la vraie '
      'API du navigateur, donc il échoue plutôt que de se sauter.\n${resultat.stderr}',
    );
  }
  return (resultat.stdout as String);
}

/// `flutter test` s'exécute depuis la racine du paquet ; on la nomme explicitement pour
/// que le témoin survive à un lancement depuis ailleurs.
String _racineDuPaquet() {
  var repertoire = Directory.current;
  while (!File('${repertoire.path}/pubspec.yaml').existsSync()) {
    final parent = repertoire.parent;
    if (parent.path == repertoire.path) fail('pubspec.yaml introuvable');
    repertoire = parent;
  }
  return repertoire.path;
}
