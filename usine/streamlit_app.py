"""Interface Streamlit — pour SUIVRE tout ce que font les agents.

Lancement :
    uv run streamlit run usine/streamlit_app.py

On saisit une commande, on clique sur « Lancer la production », et on voit l'arbre d'agents se
dérouler : chaque agent, chaque outil appelé, chaque délégation (indentée par profondeur),
puis le stock final.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

# Permet de lancer ce fichier directement avec Streamlit tout en important le package `usine`.
RACINE = pathlib.Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import streamlit as st  # noqa: E402

from usine.config import RECETTES, Config  # noqa: E402
from usine.orchestration import lancer_commande  # noqa: E402

# Couleur (badge) par agent, pour repérer qui fait quoi.
COULEUR_AGENT = {
    "Chef d'usine": "🟦",
    "Assembleur": "🟩",
    "Fabricant": "🟧",
    "Fournisseur": "🟪",
}
# Libellé lisible par type d'événement.
LIBELLE_TYPE = {
    "objectif": "🎯 objectif",
    "outil": "🔧 outil",
    "observation": "↳ résultat",
    "delegation": "→ délègue à",
    "retour": "← reçoit de",
    "fin": "✅ termine",
}

st.set_page_config(page_title="Usine d'agents — suivi", page_icon="🏭", layout="wide")
st.title("🏭 Usine d'agents — suivi de production")
st.caption("Tutoriel d'orchestration multi-agents + MCP. Voir docs/architecture.md.")

config = Config()

# --- Barre latérale : configuration et recettes --------------------------------------
with st.sidebar:
    st.header("Configuration")
    st.write(f"**Cerveau** : `{config.provider}`")
    if config.provider == "ollama":
        st.write(f"**Modèle** : `{config.ollama_model}`")
    st.write(f"**Stock initial** : `{config.stock_initial}`")

    st.header("Recettes")
    for vehicule, recette in RECETTES.items():
        pieces = ", ".join(f"{n} {p}" for p, n in recette.items())
        st.write(f"- **{vehicule}** : {pieces}")

# --- Zone principale : commande + lancement ------------------------------------------
commande = st.text_input("Commande à produire", value="2 motos + 2 voitures")

if st.button("🚀 Lancer la production", type="primary"):
    with st.spinner("Production en cours…"):
        sortie = asyncio.run(lancer_commande(commande, config))

    journal = sortie["trace"].journal

    # Résumé en haut.
    colonnes = st.columns(3)
    colonnes[0].metric("Événements", len(journal))
    colonnes[1].metric("Stock final", " · ".join(f"{p}:{n}" for p, n in sortie["etat"]["stock"].items()))
    machines_livrees = sum(1 for s in sortie["etat"]["suivi"].values() if s == "livrée")
    colonnes[2].metric("Machines livrées", machines_livrees)

    # Le déroulé, indenté par profondeur. On construit UN seul bloc markdown
    # (bien plus rapide que des centaines d'appels st.markdown séparés).
    st.subheader("Déroulé (arbre d'agents)")
    lignes = []
    for evenement in journal:
        marge = "&nbsp;" * (evenement["profondeur"] * 6)
        badge = COULEUR_AGENT.get(evenement["agent"], "⬜")
        libelle = LIBELLE_TYPE.get(evenement["type"], evenement["type"])
        nom = f" `{evenement['nom']}`" if evenement["nom"] else ""
        detail = evenement["detail"]
        # Met en évidence les ruptures de stock du fournisseur.
        if isinstance(detail, dict) and isinstance(detail.get("resultat"), dict) \
                and detail["resultat"].get("statut") == "rupture":
            badge = "⚠️"
        texte_detail = "" if detail is None else f" — {str(detail)[:160]}"
        lignes.append(f"{marge}{badge} **{evenement['agent']}** · {libelle}{nom}{texte_detail}")
    st.markdown("<br>".join(lignes), unsafe_allow_html=True)

    # Détails bruts repliés.
    with st.expander("Voir le journal brut (JSON)"):
        st.json(journal)
    with st.expander("Voir l'état final (stock + suivi)"):
        st.json(sortie["etat"])
else:
    st.info("Saisis une commande puis clique sur **Lancer la production**.")
