"""Onglet « A file of tickets » : un CSV de tickets classé et trié, cas critiques en tête."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from support_agent.assistant_fichier import en_csv
from support_agent.ui.client import ClientAPI, ErreurAPI

ICONES_PRIORITE = {"high": "🔴 high", "medium": "🟠 medium", "low": "🟢 low"}
COLONNES = {"ligne": "Line", "critique": "Critical", "priorite": "Priority",
            "categorie": "Category", "groupe": "Team", "delai": "Response time",
            "article": "Article", "technicien_requis": "Technician", "text": "Message"}


def tableau(lignes: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(lignes)
    df["priorite"] = df["priorite"].map(ICONES_PRIORITE).fillna(df["priorite"])
    df["critique"] = df["critique"].map({True: "⚠️ yes", False: ""})
    df["technicien_requis"] = df["technicien_requis"].map({True: "yes", False: ""})
    return df[list(COLONNES)].rename(columns=COLONNES)


def afficher(resultat: dict[str, Any], nom: str) -> None:
    r = resultat["resume"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickets", r["lignes"])
    c2.metric("Critical", r["critiques"])
    c3.metric("Need a technician", r["technicien_requis"])
    c4.metric("Off-topic", r["hors_sujet"])
    if r["critiques"]:
        st.error(f"{r['critiques']} critical ticket(s) at the top of the list: handle them first.")
    st.dataframe(tableau(resultat["lignes"]), hide_index=True, use_container_width=True)
    st.caption("Sorted: critical first, then priority high → low, off-topic last. "
               "Per category: " + ", ".join(f"{k} {v}" for k, v in r["par_categorie"].items()))
    st.download_button("⬇️ Download the sorted file (CSV)", en_csv(resultat["lignes"]),
                       file_name=f"sorted_{nom}", mime="text/csv")


def onglet_fichier(client: ClientAPI) -> None:
    st.write("Upload a CSV file of tickets: each one is classified, then the list is sorted "
             "for the technicians, **critical cases first**. The file needs a text column "
             "(`text`, `message` or `description`); 2,000 rows and 2 MB at most.")
    envoi = st.file_uploader("CSV file of tickets", type=["csv"])
    if envoi is not None and st.session_state.get("fichier_nom") != envoi.name:
        try:
            with st.spinner("Classifying the tickets..."):
                st.session_state.fichier_resultat = client.assist_csv(envoi.getvalue())
            st.session_state.fichier_nom, st.session_state.fichier_erreur = envoi.name, None
        except ErreurAPI as e:
            st.session_state.fichier_resultat, st.session_state.fichier_erreur = None, str(e)
            st.session_state.fichier_nom = envoi.name
    if st.session_state.get("fichier_erreur"):
        st.error(st.session_state.fichier_erreur)
    if st.session_state.get("fichier_resultat"):
        afficher(st.session_state.fichier_resultat, st.session_state.get("fichier_nom", "x.csv"))
