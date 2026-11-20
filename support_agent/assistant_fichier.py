"""Traitement d'un fichier CSV de tickets (F3) : chaque ligne est classée, puis le lot est
trié pour le technicien, cas critiques en tête.

Le fichier doit avoir une colonne de texte : `text`, `message`, `description`, `body`,
`ticket` ou `incident` (sinon la première colonne de texte) ; une colonne `subject` est
ajoutée devant le texte si elle existe. Séparateur (`,` `;` tabulation) et encodage
(UTF-8, UTF-8 avec BOM, Latin-1) sont détectés.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any, Protocol

import pandas as pd

from support_agent.config import HORS_SUJET, INDETERMINE
from support_agent.escalade import delai, groupe, motif_immediat, priorite_ticket
from support_agent.modele import Prediction

MAX_LIGNES = 2000
MAX_OCTETS = 2 * 1024 * 1024  # 2 Mo
COLONNES_TEXTE = ("text", "message", "description", "body", "ticket", "incident", "texte")
RANG_PRIORITE = {"high": 0, "medium": 1, "low": 2}


class FichierInvalide(ValueError):
    """Le fichier ne peut pas être traité ; le message est lisible par l'utilisateur."""


class Modele(Protocol):
    def predire(self, texte: str, k: int = 3) -> Prediction: ...


def _decoder(contenu: bytes) -> str:
    for encodage in ("utf-8-sig", "latin-1"):
        try:
            return contenu.decode(encodage)
        except UnicodeDecodeError:
            continue
    raise FichierInvalide("encodage du fichier non reconnu")  # pragma: no cover


def lire_csv(contenu: bytes) -> pd.DataFrame:
    """CSV -> tableau à deux colonnes : `ligne` (numéro d'origine, 1 = 1re donnée), `text`."""
    if not contenu.strip():
        raise FichierInvalide("le fichier est vide")
    if len(contenu) > MAX_OCTETS:
        raise FichierInvalide(f"fichier trop gros (plus de {MAX_OCTETS // 1024 // 1024} Mo)")
    texte = _decoder(contenu)
    try:
        separateur = csv.Sniffer().sniff(texte[:5000], delimiters=",;\t").delimiter
    except csv.Error:
        separateur = ","
    try:
        df = pd.read_csv(io.StringIO(texte), sep=separateur, dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise FichierInvalide(f"CSV illisible : {e}") from e
    colonnes = {c.strip().lower(): c for c in df.columns}
    nom = next((colonnes[c] for c in COLONNES_TEXTE if c in colonnes), None)
    if nom is None:
        raise FichierInvalide("aucune colonne de texte trouvée : nommez-la « text », "
                              f"« message » ou « description » (colonnes : {list(df.columns)})")
    messages = df[nom].astype(str)
    if "subject" in colonnes:
        sujet = df[colonnes["subject"]].astype(str)
        messages = (sujet + ". " + messages).where(sujet.str.strip() != "", messages)
    sortie = pd.DataFrame({"ligne": range(1, len(df) + 1),
                           "text": messages.str.replace(r"\s+", " ", regex=True).str.strip()})
    sortie = sortie[sortie["text"] != ""]
    if sortie.empty:
        raise FichierInvalide("aucune ligne avec du texte")
    if len(sortie) > MAX_LIGNES:
        raise FichierInvalide(f"trop de lignes ({len(sortie)}) : {MAX_LIGNES} au plus")
    return sortie.reset_index(drop=True)


def _ligne(numero: int, p: Prediction) -> dict[str, Any]:
    article = p.articles[0] if p.articles else None
    motif = motif_immediat(p.categorie, p.critique, article)
    categorie = p.categorie
    prio = priorite_ticket(p.priorite, p.critique, motif)
    return {
        "ligne": numero,
        "text": p.texte,
        "categorie": categorie,
        "categorie_probable": p.categorie_probable,
        "confiance": p.confiance,
        "priorite": prio,
        "critique": p.critique,
        "groupe": "—" if categorie == HORS_SUJET else groupe(categorie),
        "delai": "—" if categorie == HORS_SUJET else delai(prio),
        "article": article["id"] if article else "",
        "titre_article": article["titre"] if article else "",
        "technicien_requis": motif is not None or categorie == INDETERMINE,
        "raison": p.raison,
    }


def trier(lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cas critiques d'abord, puis priorité (high, medium, low), hors sujet à la fin ;
    à égalité, l'ordre du fichier est gardé."""
    return sorted(lignes, key=lambda x: (x["categorie"] == HORS_SUJET, not x["critique"],
                                         RANG_PRIORITE.get(x["priorite"], 1), x["ligne"]))


def traiter(modele: Modele, df: pd.DataFrame) -> dict[str, Any]:
    textes = df["text"].tolist()
    lot = getattr(modele, "predire_lot", None)
    preds: list[Prediction] = lot(textes) if lot else [modele.predire(t) for t in textes]
    lignes = trier([_ligne(int(n), p) for n, p in zip(df["ligne"], preds, strict=True)])
    return {"resume": resumer(lignes), "lignes": lignes}


def resumer(lignes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "lignes": len(lignes),
        "critiques": sum(x["critique"] for x in lignes),
        "technicien_requis": sum(x["technicien_requis"] for x in lignes),
        "indetermines": sum(x["categorie"] == INDETERMINE for x in lignes),
        "hors_sujet": sum(x["categorie"] == HORS_SUJET for x in lignes),
        "par_categorie": dict(Counter(x["categorie"] for x in lignes).most_common()),
        "par_priorite": {p: sum(x["priorite"] == p for x in lignes) for p in RANG_PRIORITE},
    }


def en_csv(lignes: list[dict[str, Any]]) -> bytes:
    """Résultat trié, prêt à télécharger (UTF-8 avec BOM : s'ouvre bien dans Excel)."""
    return pd.DataFrame(lignes).to_csv(index=False).encode("utf-8-sig")
