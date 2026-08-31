import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostbit/modeles/langages.dart';

/// La liste des langages de l'application est-elle encore celle du serveur ?
///
/// `lib/modeles/langages.dart` est **engendré** depuis `app/languages.json`. Un artefact
/// engendré ne prouve rien par lui-même : il prouve qu'il a été juste le jour où on l'a
/// produit. Ce témoin le relit contre sa source à chaque exécution, ce qui est la seule
/// façon de savoir qu'il l'est encore.
///
/// L'écart serait **muet** sans lui : un langage choisi dans l'application et inconnu du
/// serveur donne un paste sans coloration, pas une erreur. Personne ne le signalerait.
void main() {
  test('la liste engendrée correspond à app/languages.json', () {
    final source = File('${_racineDuDepot()}/app/languages.json');
    expect(
      source.existsSync(),
      isTrue,
      reason: 'app/languages.json est introuvable — le témoin ne mesure plus rien, '
          'et c\'est un échec, pas un test à sauter',
    );

    final langues = jsonDecode(source.readAsStringSync()) as List<dynamic>;
    final attendus = [for (final l in langues) (l as Map)['slug'] as String];

    // L'ordre compte autant que le contenu : c'est celui du menu déroulant du web, et
    // deux listes qui ne se lisent pas dans le même ordre se comparent mal à l'écran.
    expect(langagesConnus, attendus);

    for (final l in langues) {
      final m = l as Map;
      final extensions = (m['extensions'] as List).cast<String>();
      expect(
        extensionsParLangage[m['slug']],
        extensions.isEmpty ? '' : extensions.first,
        reason: 'extension divergente pour ${m['slug']}',
      );
    }
  });
}

/// Remonte de `apps/mobile` jusqu'à la racine du dépôt ghostbit.
String _racineDuDepot() {
  var repertoire = Directory.current;
  while (!File('${repertoire.path}/app/languages.json').existsSync()) {
    final parent = repertoire.parent;
    if (parent.path == repertoire.path) {
      fail('racine du dépôt ghostbit introuvable depuis ${Directory.current.path}');
    }
    repertoire = parent;
  }
  return repertoire.path;
}
