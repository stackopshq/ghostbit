package dev.ghostbit.ghostbit

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * L'activité Flutter, qui reçoit aussi les partages.
 *
 * ─── Pourquoi Android n'a pas besoin de la feuille native qu'iOS exige ───
 *
 * Sur iOS, une Share Extension est un **processus séparé** au budget mémoire serré, où
 * Flutter ne tient pas en pratique : la feuille de partage y est donc du Swift qui appelle
 * le cœur Rust par UniFFI. C'est un coût réel — un second client à écrire et à maintenir.
 *
 * Android n'impose rien de tel. Une intention `ACTION_SEND` peut viser **cette activité**,
 * qui est déjà l'application entière : le partage arrive dans le même processus, dans le
 * même moteur Flutter, et emprunte donc exactement le même chemin de chiffrement que la
 * création ordinaire. Écrire ici un client Kotlin pour recopier ce que Dart fait déjà
 * ajouterait une seconde implémentation du format, sans qu'aucune contrainte l'exige.
 *
 * **Aucune cryptographie dans ce fichier**, et rien qui y ressemble : il transporte une
 * chaîne de caractères, et c'est tout ce qu'il a le droit de faire.
 *
 * ─── Les deux moments où un partage arrive, et pourquoi il en faut deux ───
 *
 * 1. **L'application était fermée.** L'intention a lancé le processus, et elle est déjà là
 *    quand Dart pose son écouteur. Dart doit donc venir la chercher : `partageInitial`.
 * 2. **L'application tournait déjà.** `launchMode="singleTop"` fait qu'aucune nouvelle
 *    activité n'est créée : l'intention arrive par `onNewIntent`, et il faut la pousser.
 *
 * N'implémenter que le second cas donne le défaut le plus déroutant qui soit : partager
 * marche, sauf la première fois.
 *
 * ─── Et les liens universels, qui empruntent le même canal ───
 *
 * Une intention `ACTION_VIEW` sur un lien de paste vérifié arrive exactement de la même
 * façon, aux deux mêmes moments, et repart par le même canal — sous un autre nom de
 * méthode, `lien` plutôt que `partage`.
 *
 * Les deux **ne se confondent pas**, et c'est délibéré. Un texte partagé est trié côté Dart
 * par une heuristique : « commence par l'adresse du serveur configuré, et contient un
 * dièse ». Un lien universel, lui, vient forcément d'un domaine que le système a vérifié —
 * mais pas nécessairement de celui que cet appareil a configuré. Le faire passer par la
 * même heuristique le ferait prendre pour du texte ordinaire, et GhostBit créerait un paste
 * chiffré **contenant l'URL** au lieu de l'ouvrir. Deux provenances, deux noms.
 */
class MainActivity : FlutterActivity() {
    private var canal: MethodChannel? = null

    /** Le texte reçu avant que Dart n'ait pu écouter. Consommé une fois, puis oublié. */
    private var partageEnAttente: String? = null

    /** Le lien reçu avant que Dart n'ait pu écouter. Même cycle de vie. */
    private var lienEnAttente: String? = null

    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        canal = MethodChannel(engine.dartExecutor.binaryMessenger, CANAL).also { c ->
            c.setMethodCallHandler { appel, reponse ->
                when (appel.method) {
                    "partageInitial" -> {
                        // Rendu une seule fois : sans cela, revenir sur l'application
                        // rouvrirait indéfiniment le même partage.
                        reponse.success(partageEnAttente)
                        partageEnAttente = null
                    }
                    "lienInitial" -> {
                        // Même raison, et elle pèse plus lourd ici : rouvrir un paste
                        // marqué « brûler après lecture » le consomme pour de bon.
                        reponse.success(lienEnAttente)
                        lienEnAttente = null
                    }
                    else -> reponse.notImplemented()
                }
            }
        }
        partageEnAttente = texteDe(intent)
        lienEnAttente = lienDe(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // `singleTop` réutilise l'activité ; sans cette ligne, l'intention est bien reçue
        // par le système et n'atteint jamais Dart.
        setIntent(intent)
        texteDe(intent)?.let { texte ->
            val c = canal
            if (c != null) c.invokeMethod("partage", texte) else partageEnAttente = texte
        }
        lienDe(intent)?.let { lien ->
            val c = canal
            if (c != null) c.invokeMethod("lien", lien) else lienEnAttente = lien
        }
    }

    /**
     * Extrait le texte d'une intention de partage.
     *
     * `EXTRA_TEXT` peut être un `Spanned` plutôt qu'une `String` — c'est le cas quand on
     * partage depuis une application qui met en forme, un navigateur par exemple. Le
     * transtyper directement en `String` lèverait une `ClassCastException` au moment
     * précis où l'utilisateur attend quelque chose. `toString()` traverse les deux.
     */
    private fun texteDe(intent: Intent?): String? {
        if (intent == null || intent.action != Intent.ACTION_SEND) return null
        val texte = intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()
        return texte?.takeIf { it.isNotBlank() }
    }

    /**
     * Extrait l'URL d'une intention de lien universel.
     *
     * `data.toString()` et non `data.path` : **la clé de déchiffrement vit dans le
     * fragment**, après le `#`. Elle ne quitte jamais l'appareil — le navigateur ne
     * l'envoie pas au serveur, et c'est tout l'intérêt du format. Reconstruire l'adresse
     * à partir de ses morceaux est le moyen le plus sûr de la perdre, et la perte ne se
     * voit qu'au bout de la chaîne, sur un écran qui accuse la clé d'être mauvaise alors
     * qu'elle a simplement été coupée ici.
     */
    private fun lienDe(intent: Intent?): String? {
        if (intent == null || intent.action != Intent.ACTION_VIEW) return null
        return intent.data?.toString()?.takeIf { it.isNotBlank() }
    }

    private companion object {
        const val CANAL = "dev.ghostbit/partage"
    }
}
