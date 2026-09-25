allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

// ─── API 37 n'existe plus sans version mineure ───────────────────────────────
//
// `flutter_secure_storage` 11 exige 37 de ce qui dépend de lui, et le greffon Gradle de
// Flutter aligne les **sous-projets de greffon** sur le compileSdk de l'application — pas
// l'inverse. L'application, elle, ne bouge pas toute seule : c'est `app/build.gradle.kts`
// qui la pose en 37, et l'alignement propage ensuite ce 37 aux greffons qui étaient plus
// bas. Dans les deux sens, des sous-projets se retrouvent en 37 sans mineure, et l'AGP
// traduit un `compileSdk` seul en la chaîne de hachage `android-37` — la compilation
// échoue :
//
//     Failed to find target with hash string 'android-37' in: …/Library/Android/sdk
//
// Ce n'est pas une installation incomplète. Le dépôt de Google ne publie plus de
// `platforms;android-37` : à partir de cette version, les plateformes portent une version
// mineure, et l'on ne trouve que `android-37.0`, `android-37.1`, `android-37.2` — de même
// que `android-36.1` à côté de `android-36`. Réinstaller ne change donc rien, et le
// message, qui ressemble à un paquet manquant, envoie chercher là où il n'y a rien.
//
// `compileSdkMinor` est la réponse de l'AGP 9 à ce découpage : il nomme la mineure, et la
// paire (37, 0) désigne `android-37.0`, qui est installé. On le pose sur **tout**
// sous-projet resté en 37 sans mineure — les greffons ne sont pas à nous, et celui qui
// pose le problème n'a pas de raison d'être le seul à le poser.
//
// Le bloc s'applique **avant** l'`evaluationDependsOn` ci-dessous, et il regarde
// `state.executed` avant de choisir son moment : `evaluationDependsOn(":app")` évalue des
// projets pendant la configuration, si bien qu'un `afterEvaluate` posé après lui arrive
// trop tard et lève « Cannot run Project.afterEvaluate(Action) when the project is already
// evaluated ». C'est arrivé à la première version de ce bloc.
//
// Il reste un troisième endroit à corriger, et il n'est pas ici : cargokit lit ce même
// `compileSdkVersion` et l'analyse en entier. Voir `rust_builder/cargokit/gradle/plugin.gradle`.
fun Project.nommerLaMineureDeLApi37() {
    val android =
        extensions.findByType(com.android.build.api.dsl.CommonExtension::class.java) ?: return
    if (android.compileSdk == 37 && android.compileSdkMinor == null) {
        android.compileSdkMinor = 0
    }
}

subprojects {
    if (state.executed) nommerLaMineureDeLApi37() else afterEvaluate { nommerLaMineureDeLApi37() }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
