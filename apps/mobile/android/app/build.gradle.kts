plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "dev.ghostbit.ghostbit"
    // ─── Ni `flutter.compileSdkVersion`, ni 37 tout court ────────────────────
    //
    // `flutter.compileSdkVersion` vaut 36, et `flutter_secure_storage` 11 exige 37 :
    //
    //     Dependency ':flutter_secure_storage' requires libraries and applications that
    //     depend on it to compile against version 37 or later of the Android APIs.
    //     :app is currently compiled against android-36.
    //
    // Flutter n'aligne pas l'application sur le plus haut compileSdk de ses greffons ; il
    // laisse le soin de le faire, et la valeur par défaut ne suit donc pas les greffons.
    //
    // Écrire `compileSdk = 37` seul échange ce message contre un autre, plus trompeur :
    //
    //     Failed to find target with hash string 'android-37' in: …/Library/Android/sdk
    //
    // Voir le commentaire du `build.gradle.kts` racine : Google ne publie plus de
    // `platforms;android-37`, seulement `android-37.0` et suivantes. `compileSdkMinor`
    // nomme la mineure ; la paire (37, 0) désigne `android-37.0`, qui est installé.
    compileSdk = 37
    compileSdkMinor = 0
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "dev.ghostbit.ghostbit"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
