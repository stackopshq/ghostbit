import 'package:flutter_test/flutter_test.dart';
import 'package:ghostbit/services/reglages.dart';

/// L'adresse de l'instance : ce qui est accepté, ce qui est refusé, et avec quel motif.
///
/// Ghostbit est fait pour être auto-hébergé, donc cette saisie est la première chose que
/// l'application demande — et la seule qu'elle ne peut pas deviner. Un refus muet ou un
/// bouton grisé sans explication laisserait quelqu'un bloqué sur le premier écran.
void main() {
  group('normalisation', () {
    test('complète le schéma manquant en https', () {
      // Le cas qui compte : sans schéma, `Uri.parse` rend une adresse relative et la
      // première requête part vers un chemin local, avec un message qui n'oriente vers rien.
      expect(Reglages.normaliser('paste.exemple.ch'), 'https://paste.exemple.ch');
    });

    test('retire les barres obliques finales', () {
      // `Uri.resolve('/api/v1/pastes')` sur une base terminée par `/` donnerait un double
      // slash chez certains proxys, qui répondent 404 sans dire pourquoi.
      expect(Reglages.normaliser('https://p.ch///'), 'https://p.ch');
    });

    test('respecte un schéma déjà présent', () {
      expect(Reglages.normaliser('  http://localhost:8000  '), 'http://localhost:8000');
    });
  });

  group('refus', () {
    test('accepte une instance en https', () {
      expect(Reglages.refus('https://paste.exemple.ch'), isNull);
    });

    test('accepte http sur la machine locale', () {
      // Une instance de développement tourne en clair sur la machine, sans conséquence —
      // c'est ce que propose la page web elle-même quand le contexte n'est pas sûr.
      expect(Reglages.refus('http://localhost:8000'), isNull);
      expect(Reglages.refus('http://127.0.0.1:8931'), isNull);
    });

    test('refuse http vers un hôte distant, en disant pourquoi', () {
      final motif = Reglages.refus('http://paste.exemple.ch');
      expect(motif, isNotNull);
      // Le motif doit parler du canal, pas de la syntaxe : c'est ce qui distingue
      // « corrigez votre saisie » de « ceci annulerait le chiffrement du transport ».
      expect(motif, contains('https'));
    });

    test('refuse une adresse vide et un schéma inconnu', () {
      expect(Reglages.refus(''), isNotNull);
      expect(Reglages.refus('ftp://paste.exemple.ch'), isNotNull);
    });
  });
}
