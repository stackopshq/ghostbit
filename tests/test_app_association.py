"""Les deux fichiers qui font qu'un lien de paste ouvre l'application mobile.

Ce que ces tests gardent est une panne muette : sans `apple-app-site-association` ni
`assetlinks.json`, un lien de partage s'ouvre dans le navigateur — ce qui ressemble trait
pour trait à un lien qui marche. Il n'y a rien à voir à l'écran, donc le seul endroit où
la régression peut être attrapée est ici.
"""

import json
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("STORAGE_BACKEND", "sqlite")
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tmp_db:
    os.environ["SQLITE_PATH"] = _tmp_db.name

from app.config import Settings, settings  # noqa: E402
from app.main import app  # noqa: E402
from app.storage import get_storage  # noqa: E402

# Une empreinte de forme valide, et qui ne signe rien : ces tests vérifient la plomberie,
# pas la clé. La vraie valeur vient de la configuration de déploiement, et il n'y a
# délibérément pas de valeur par défaut — voir `config.py`.
_EMPREINTE = ":".join(["AB"] * 32)


@pytest_asyncio.fixture(scope="module")
async def client():
    app.state.storage = await get_storage()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.storage.close()


@pytest.fixture
def avec_empreinte(monkeypatch):
    monkeypatch.setattr(settings, "android_cert_fingerprints", _EMPREINTE)


# ── apple-app-site-association ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aasa_est_servi_en_json_sans_redirection(client):
    r = await client.get("/.well-known/apple-app-site-association")
    assert r.status_code == 200
    # Sans redirection : la CDN d'Apple ne les suit pas, et un 301 vers un fichier
    # parfaitement correct produirait exactement la même panne qu'un 404.
    assert r.history == []
    # Le type doit être `application/json`, pas `text/plain` ni `application/octet-stream`.
    assert r.headers["content-type"].startswith("application/json")
    json.loads(r.content)  # lève si le corps n'est pas du JSON


@pytest.mark.asyncio
async def test_aasa_nomme_l_app_id_complet(client):
    doc = (await client.get("/.well-known/apple-app-site-association")).json()
    app_ids = doc["applinks"]["details"][0]["appIDs"]
    # `<TeamID>.<bundleID>` : le bundle seul est l'erreur classique, et elle échoue en
    # silence — iOS ne dit rien, il ouvre simplement Safari.
    assert app_ids == ["9WHCJ5W7S6.dev.ghostbit.ghostbit"]
    for app_id in app_ids:
        equipe, _, bundle = app_id.partition(".")
        assert len(equipe) == 10 and equipe.isalnum(), app_id
        assert bundle.count(".") >= 1, app_id


@pytest.mark.asyncio
async def test_aasa_ne_reclame_que_les_liens_porteurs_de_cle(client):
    doc = (await client.get("/.well-known/apple-app-site-association")).json()
    composants = doc["applinks"]["details"][0]["components"]

    # La règle attrape-tout est la dernière, et elle exige un fragment non vide : la clé
    # de déchiffrement vit après le `#`, et un paste sans elle n'a rien à montrer dans
    # l'application.
    dernier = composants[-1]
    assert dernier["/"] == "/*"
    assert dernier["#"] == "?*"
    assert "exclude" not in dernier

    # Elle n'apparaît **qu'**en dernier. iOS retient la première règle qui correspond :
    # la même règle recopiée en tête rendrait toutes les exclusions qui suivent
    # inopérantes, et le document resterait parfaitement valide. Compter les occurrences
    # est ce qui distingue les deux — une version antérieure de ce test ne le faisait pas
    # et laissait passer exactement cette erreur.
    attrape_tout = [i for i, c in enumerate(composants) if c["/"] == "/*"]
    assert attrape_tout == [len(composants) - 1]

    # Tout ce qui n'est pas un paste est exclu **avant** elle, sans quoi l'ordre de
    # lecture d'iOS ferait ouvrir l'application sur la notice de confidentialité.
    exclus = [c["/"] for c in composants if c.get("exclude")]
    for chemin in ("/api/*", "/static/*", "/.well-known/*", "/privacy"):
        assert chemin in exclus
        assert (
            composants.index(next(c for c in composants if c["/"] == chemin)) < len(composants) - 1
        )


@pytest.mark.asyncio
async def test_aasa_a_la_racine_rend_le_fichier_et_non_le_422_du_attrape_tout(client):
    # `/apple-app-site-association` tombait sur `/{paste_id}`, dont le motif refuse 26
    # caractères : le 422 qui en sortait ressemblait à une route d'API qui intercepte.
    r = await client.get("/apple-app-site-association")
    assert r.status_code == 200
    assert r.json() == (await client.get("/.well-known/apple-app-site-association")).json()


# ── assetlinks.json ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assetlinks_sans_empreinte_refuse_et_nomme_la_variable(client, monkeypatch):
    monkeypatch.setattr(settings, "android_cert_fingerprints", "")
    r = await client.get("/.well-known/assetlinks.json")
    # Le troisième état : pas « vert », pas un fichier faux, mais « je ne peux pas
    # répondre » — et la raison, en clair, pour qui tire un `curl` dessus.
    assert r.status_code == 503
    assert "ANDROID_CERT_FINGERPRINTS" in r.json()["detail"]


@pytest.mark.asyncio
async def test_assetlinks_porte_la_relation_le_paquet_et_l_empreinte(client, avec_empreinte):
    r = await client.get("/.well-known/assetlinks.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    (entree,) = r.json()
    assert entree["relation"] == ["delegate_permission/common.handle_all_urls"]
    cible = entree["target"]
    assert cible["namespace"] == "android_app"
    # Le nom de paquet doit être celui de `android/app/build.gradle.kts`.
    assert cible["package_name"] == "dev.ghostbit.ghostbit"
    assert cible["sha256_cert_fingerprints"] == [_EMPREINTE]


# ── Le garde-fou sur l'empreinte elle-même ────────────────────────────────────


@pytest.mark.parametrize(
    "mauvaise",
    [
        "AB:CD",  # tronquée
        ":".join(["AB"] * 31),  # 31 octets au lieu de 32
        ":".join(["AB"] * 31 + ["ZZ"]),  # un seul caractère non hexadécimal
        ":".join(["ABC"] * 32),  # trois chiffres par octet
        "".join(["AB"] * 32),  # les deux-points manquants
    ],
)
def test_une_empreinte_mal_formee_echoue_au_demarrage(monkeypatch, mauvaise):
    # Une faute de frappe dans 64 chiffres hexadécimaux ne se voit pas à l'œil, et Android
    # ne la signale pas : il n'ouvre pas l'application, c'est tout. Elle doit donc faire
    # échouer le démarrage, seul endroit où quelqu'un regarde.
    monkeypatch.setenv("ANDROID_CERT_FINGERPRINTS", mauvaise)
    with pytest.raises(ValueError, match="colon-separated hex pairs"):
        Settings()


def test_une_empreinte_valide_passe_et_se_normalise(monkeypatch):
    # Le pendant du test précédent : un contrôle qui refuserait tout serait vert pour une
    # mauvaise raison. `keytool` sort en majuscules, la Play Console en minuscules.
    monkeypatch.setenv("ANDROID_CERT_FINGERPRINTS", _EMPREINTE.lower())
    assert Settings().android_cert_fingerprints == _EMPREINTE
