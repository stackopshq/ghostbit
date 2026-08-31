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
 */
class MainActivity : FlutterActivity() {
    private var canal: MethodChannel? = null

    /** Le texte reçu avant que Dart n'ait pu écouter. Consommé une fois, puis oublié. */
    private var partageEnAttente: String? = null

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
                    else -> reponse.notImplemented()
                }
            }
        }
        partageEnAttente = texteDe(intent)
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

    private companion object {
        const val CANAL = "dev.ghostbit/partage"
    }
}
