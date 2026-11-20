"""Tests de T8 : lecture du CSV, tri (critiques en tête), /assist, onglet fichier."""

from __future__ import annotations

import io
from typing import Any

import httpx
import pandas as pd
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from support_agent import assistant_fichier as af
from support_agent.api.main import creer_app
from support_agent.config import EVAL, SAMPLE
from support_agent.modele import ModeleSupport, Prediction
from support_agent.stockage import Conversations
from support_agent.tickets import Tickets
from support_agent.ui.client import ClientAPI, ErreurAPI
from tests.test_chat import Bouchon, Reglages
from tests.test_ui import APP

# --- lecture du fichier -------------------------------------------------------------


@pytest.mark.parametrize("contenu", [
    b"text,autre\nVPN down,1\nPrinter jam,2\n",
    b"text;autre\nVPN down;1\nPrinter jam;2\n",
    b"text\tautre\nVPN down\t1\nPrinter jam\t2\n",
    "﻿text\nVPN down\nPrinter jam\n".encode(),  # UTF-8 avec BOM (Excel)
    "Message\nVPN down\nPrinter jam\n".encode("latin-1"),  # autre nom de colonne
])
def test_lire_csv_formats(contenu: bytes) -> None:
    df = af.lire_csv(contenu)
    assert df["text"].tolist() == ["VPN down", "Printer jam"] and df["ligne"].tolist() == [1, 2]


def test_lire_csv_sujet_accents_et_lignes_vides() -> None:
    contenu = "subject,body\nVPN,ne marche pas  depuis   hier\n,   \n,Imprimante cassée\n"
    df = af.lire_csv(contenu.encode("latin-1"))
    assert df["text"].tolist() == ["VPN. ne marche pas depuis hier", "Imprimante cassée"]
    assert df["ligne"].tolist() == [1, 3]  # numéros d'origine gardés


@pytest.mark.parametrize(("contenu", "message"), [
    (b"", "vide"), (b"   \n", "vide"),
    (b"id,date\n1,2026\n", "aucune colonne de texte"),
    (b"text\n   \n", "aucune ligne avec du texte"),
    (b'text\n"ouvert sans fin\n', "illisible"),
])
def test_lire_csv_erreurs(contenu: bytes, message: str) -> None:
    with pytest.raises(af.FichierInvalide, match=message):
        af.lire_csv(contenu)


def test_lire_csv_limites(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(af, "MAX_LIGNES", 2)
    with pytest.raises(af.FichierInvalide, match="trop de lignes"):
        af.lire_csv(b"text\na\nb\nc\n")
    monkeypatch.setattr(af, "MAX_OCTETS", 10)
    with pytest.raises(af.FichierInvalide, match="trop gros"):
        af.lire_csv(b"text\n" + b"x" * 20)


def test_vrais_fichiers_du_depot() -> None:
    assert len(af.lire_csv((EVAL / "jeu_validation.csv").read_bytes())) == 120
    assert len(af.lire_csv((SAMPLE / "tobi_bueck_extrait.csv").read_bytes())) == 100


# --- classement et tri ---------------------------------------------------------------

TEXTES = ["What's the weather?", "My VPN keeps disconnecting", "The printer is jammed",
          "I clicked a phishing link", "It does not work", "Our VPN is down for everyone"]


def _traiter(modele: Any = None) -> dict[str, Any]:
    df = pd.DataFrame({"ligne": range(1, len(TEXTES) + 1), "text": TEXTES})
    return af.traiter(modele or Bouchon(), df)


def test_tri_critiques_en_tete_hors_sujet_a_la_fin() -> None:
    r = _traiter()
    ordre = [x["ligne"] for x in r["lignes"]]
    assert ordre[0] == 4  # phishing : critique
    assert ordre[-1] == 1  # météo : hors sujet, en dernier
    assert ordre.index(2) < ordre.index(3)  # même priorité : ordre du fichier gardé
    phishing = r["lignes"][0]
    assert phishing["critique"] and phishing["priorite"] == "high"
    assert phishing["groupe"] == "Security team" and phishing["delai"] == "4 hours"
    assert phishing["technicien_requis"] and phishing["article"] == "KB-SEC-01"
    meteo = r["lignes"][-1]
    assert meteo["groupe"] == "—" and meteo["article"] == ""


def test_resume() -> None:
    res = _traiter()["resume"]
    assert res["lignes"] == 6 and res["critiques"] == 1 and res["hors_sujet"] == 1
    assert res["indetermines"] == 1 and res["technicien_requis"] == 2  # critique + indéterminé
    assert sum(res["par_priorite"].values()) == 6


def test_utilise_predire_lot_si_disponible() -> None:
    class Lot(Bouchon):
        appels: list[int] = []

        def predire_lot(self, textes: list[str], k: int = 3) -> list[Prediction]:
            Lot.appels.append(len(textes))
            return [self.predire(t) for t in textes]

    _traiter(Lot())
    assert Lot.appels == [6]  # un seul appel pour tout le lot


def test_predire_lot_identique_a_predire(modele: ModeleSupport) -> None:
    lot = modele.predire_lot(["My VPN keeps disconnecting", "printr offlin"])
    seul = [modele.predire("My VPN keeps disconnecting"), modele.predire("printr offlin")]
    assert [p.en_dict() for p in lot] == [p.en_dict() for p in seul]
    assert modele.predire_lot([]) == []


def test_en_csv() -> None:
    donnees = af.en_csv(_traiter()["lignes"])
    assert donnees.startswith(b"\xef\xbb\xbf")  # BOM : Excel lit bien les accents
    relu = pd.read_csv(io.BytesIO(donnees), encoding="utf-8-sig")
    assert relu["ligne"].tolist()[0] == 4 and "groupe" in relu.columns


# --- API ------------------------------------------------------------------------------


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("support_agent.api.main.get_settings", lambda: Reglages())
    return TestClient(creer_app(Bouchon(), Conversations(None), Tickets(None)))


def test_api_assist_json(api: TestClient) -> None:
    r = api.post("/assist", json={"textes": TEXTES + ["   "]})
    assert r.status_code == 200
    assert r.json()["lignes"][0]["ligne"] == 4 and r.json()["resume"]["lignes"] == 6
    assert api.post("/assist", json={"textes": []}).status_code == 422
    assert api.post("/assist", json={"textes": ["  ", ""]}).status_code == 422
    assert api.post("/assist", json={"textes": ["x" * 2001]}).status_code == 422


def test_api_assist_csv(api: TestClient) -> None:
    corps = "text\n" + "\n".join(f'"{t}"' for t in TEXTES)
    r = api.post("/assist/csv", content=corps.encode(), headers={"Content-Type": "text/csv"})
    assert r.status_code == 200 and r.json()["lignes"][0]["critique"]
    r = api.post("/assist/csv", content=b"id\n1\n", headers={"Content-Type": "text/csv"})
    assert r.status_code == 422 and "colonne de texte" in r.json()["detail"]


def test_api_assist_validation_120_lignes(api: TestClient) -> None:
    """Critère de T8 (sur la validation : l'indépendant reste réservé à T12)."""
    r = api.post("/assist/csv", content=(EVAL / "jeu_validation.csv").read_bytes(),
                 headers={"Content-Type": "text/csv"}).json()
    assert r["resume"]["lignes"] == 120
    critiques = [x["critique"] for x in r["lignes"]]
    assert critiques == sorted(critiques, reverse=True)  # tous les critiques en tête


# --- interface ------------------------------------------------------------------------


def test_client_assist_csv() -> None:
    vus: list[httpx.Request] = []

    def gestion(req: httpx.Request) -> httpx.Response:
        vus.append(req)
        return httpx.Response(200, json={"resume": {}, "lignes": []})

    c = ClientAPI("http://api", cle="", transport=httpx.MockTransport(gestion))
    c.assist_csv(b"text\nvpn\n")
    assert vus[0].url.path == "/assist/csv" and vus[0].headers["content-type"] == "text/csv"
    assert vus[0].content == b"text\nvpn\n"


class FauxFichier:
    name = "tickets.csv"

    def getvalue(self) -> bytes:
        return b"text\nvpn\n"


def test_onglet_fichier(monkeypatch: pytest.MonkeyPatch) -> None:
    resultat = _traiter()
    appels: list[bytes] = []

    def assist(self: ClientAPI, contenu: bytes) -> dict[str, Any]:
        appels.append(contenu)
        return resultat

    monkeypatch.setattr(ClientAPI, "assist_csv", assist)
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: FauxFichier())
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert appels == [b"text\nvpn\n"]
    assert [m.value for m in at.metric][-4:] == ["6", "1", "2", "1"]
    assert "critical ticket(s) at the top" in at.error[0].value
    tableau = at.dataframe[0].value
    assert tableau.iloc[0]["Line"] == 4 and tableau.iloc[0]["Critical"] == "⚠️ yes"
    at.run()  # même fichier : pas de nouvel envoi
    assert len(appels) == 1


def test_onglet_fichier_erreur(monkeypatch: pytest.MonkeyPatch) -> None:
    def panne(self: ClientAPI, contenu: bytes) -> dict[str, Any]:
        raise ErreurAPI("Erreur 422 : aucune colonne de texte trouvée")

    monkeypatch.setattr(ClientAPI, "assist_csv", panne)
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: FauxFichier())
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert "aucune colonne de texte" in at.error[0].value
