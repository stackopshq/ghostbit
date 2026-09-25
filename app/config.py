from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_backend: str = "sqlite"  # "sqlite" or "redis"
    sqlite_path: str = "./ghostbit.db"
    # Number of SQLite connections held in the pool. WAL mode lets multiple
    # readers progress in parallel; writers still serialize at the DB level.
    # Raise if `ghostbit_sqlite_pool_wait_seconds` histogram shows backlog.
    sqlite_pool_size: int = 5
    redis_url: str = "redis://localhost:6379"
    redis_password: str = ""  # injected into redis_url if set
    max_paste_size: int = 524288  # 512 KB
    port: int = 8000

    # Rate limits (slowapi / limits syntax: "N/period", e.g. "30/minute")
    rate_limit_create: str = "30/minute"  # POST /api/v1/pastes
    rate_limit_view: str = "120/minute"  # GET  /api/v1/pastes/{id}

    # Optional shared secret for signing webhook payloads (HMAC-SHA256).
    # If set, every webhook delivery includes X-Ghostbit-Signature: sha256=<hex>.
    webhook_secret: str = ""

    # Who operates THIS instance: rendered into the /privacy notice, which
    # legally must name the data controller (GDPR art. 13 / nLPD art. 19).
    # Left empty, the notice falls back to neutral wording ("the operator of
    # this instance"), which is honest but weaker: set all three when you
    # deploy publicly. ghostbit.dev sets:
    #   PRIVACY_OPERATOR="StackOps (France)"
    #   PRIVACY_CONTACT_URL="https://stackops.ch"
    #   PRIVACY_AUTHORITY="the CNIL (France)"
    privacy_operator: str = ""
    privacy_contact_url: str = ""
    privacy_authority: str = ""

    # Optional bearer token for GET /metrics. Empty (default) leaves the
    # endpoint open: fine on private networks; on a public deployment the
    # aggregate counters and the Python version are readable by anyone.
    # When set, scrapes must send `Authorization: Bearer <token>`.
    metrics_token: str = ""

    # Trust X-Forwarded-For for rate limiting. Enable ONLY when behind a
    # reverse proxy that strips/overwrites this header: otherwise clients
    # can spoof it and bypass rate limits.
    trust_proxy_headers: bool = False

    # Public-facing base URL (scheme + host [+ :port]), e.g. "https://paste.example.com".
    # Builds the absolute URLs in social-preview meta tags (og:image, og:url).
    # Empty → derived from the incoming request, which is correct for direct
    # exposure and for proxies that forward scheme + Host. Set it explicitly when
    # a TLS-terminating proxy would otherwise leave the app advertising http://.
    base_url: str = ""

    # Repo whose stargazer count the footer shows, fetched server-side once an
    # hour. Set to "" to disable the outbound call entirely: the footer then
    # omits the number. Never fetched from the visitor's browser: that would
    # disclose every visitor's IP to GitHub, paste readers included.
    github_repo: str = "stackopshq/ghostbit"

    # ── Association des applications mobiles ────────────────────────────────
    #
    # Ces trois réglages ne servent qu'à deux fichiers : `/.well-known/apple-app-site-association`
    # et `/.well-known/assetlinks.json`. Sans eux, un lien de paste s'ouvre toujours dans le
    # navigateur, même quand l'application est installée — et rien ne le signale, puisque
    # « le navigateur s'est ouvert » est exactement ce à quoi ressemble un fonctionnement
    # normal. C'est la panne que ces deux routes existent pour supprimer.
    #
    # En configuration plutôt qu'en dur parce que ce dépôt s'auto-héberge : une instance
    # tierce qui publierait l'App ID de StackOps annoncerait une application qu'elle ne
    # signe pas, et l'association échouerait sans rien dire non plus.
    ios_app_ids: str = "9WHCJ5W7S6.dev.ghostbit.ghostbit"
    android_package_name: str = "dev.ghostbit.ghostbit"

    # SHA-256 du certificat qui signe l'APK, en hexadécimal séparé par deux-points — la
    # sortie de `keytool -list -v -keystore <clé>`. Plusieurs valeurs séparées par des
    # virgules : Play App Signing en impose deux, la clé d'envoi et celle de Google.
    #
    # **Vide par défaut, et c'est délibéré.** Il n'existe pas de valeur par défaut honnête
    # ici : l'empreinte dépend de la clé qui signe *ce* build-là. Une valeur inventée
    # produirait un `assetlinks.json` syntaxiquement parfait que le vérificateur d'Android
    # rejetterait — sans message, sans journal que l'utilisateur puisse voir, et avec pour
    # seul symptôme un lien qui s'ouvre dans le navigateur. Tant qu'elle n'est pas
    # renseignée, la route rend 503 en nommant la variable manquante, plutôt qu'un fichier
    # faux qui aurait l'air juste.
    android_cert_fingerprints: str = ""

    # Ignore extra env vars (e.g. a stale ENCRYPTION_KEY from pre-E2E setups)
    # instead of failing at startup.
    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, v: str) -> str:
        # Fail fast on a malformed value rather than silently emitting broken
        # <meta> URLs. Trailing slash stripped so callers can join cleanly.
        v = v.strip().rstrip("/")
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("BASE_URL must start with http:// or https://")
        return v

    @field_validator("android_cert_fingerprints")
    @classmethod
    def _normalize_fingerprints(cls, v: str) -> str:
        # Échouer au démarrage plutôt que de servir une empreinte que seul le vérificateur
        # d'Android rejettera, silencieusement et des jours plus tard. Une faute de frappe
        # dans 64 chiffres hexadécimaux ne se voit pas à l'œil : c'est le genre d'erreur
        # dont on a besoin qu'une machine la trouve.
        sorties = []
        for brut in v.split(","):
            fp = brut.strip().upper()
            if not fp:
                continue
            octets = fp.split(":")
            if len(octets) != 32 or not all(
                len(o) == 2 and all(c in "0123456789ABCDEF" for c in o) for o in octets
            ):
                raise ValueError(
                    "ANDROID_CERT_FINGERPRINTS must be SHA-256 fingerprints as 32 "
                    "colon-separated hex pairs (the `keytool -list -v` format), "
                    f"got {brut.strip()!r}"
                )
            sorties.append(fp)
        return ",".join(sorties)


settings = Settings()
