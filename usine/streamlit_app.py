"""Interface Streamlit — SUIVRE EN DIRECT tout ce que font les agents.

Le même déroulé peut s'afficher de plusieurs façons (le back ne change pas — seul le rendu
diffère) ; on choisit le mode dans la barre latérale :

- Graphe animé          : le pipeline dessiné, le nœud de l'agent actif s'allume.
- Diagramme de séquence : qui appelle qui, dans le temps (Mermaid).
- Cartes narratives     : une carte encadrée par tour d'agent, phrasé « X fait Y ».
- Journal narratif      : le récit ligne à ligne, « X fait Y ».
- Tableau structuré     : un log filtrable/triable.
- Liste indentée        : l'affichage d'origine (arbre par profondeur).

Toute la mise en forme vit dans `usine/rendu.py` (pur, testable). Ici on ne fait que la
brancher sur des emplacements d'UI mis à jour à CHAQUE événement (callback `Trace.on_event`).

Lancement :
    uv run streamlit run usine/streamlit_app.py
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
import streamlit.components.v1 as components  # noqa: E402

from usine import rendu  # noqa: E402
from usine.config import RECETTES, Config  # noqa: E402
from usine.orchestration import lancer_commande  # noqa: E402
from usine.trace import Trace  # noqa: E402


# ======================================================================================
# Renderers : un par mode d'affichage. Interface commune :
#   __init__(self)                 -> pose les emplacements d'UI
#   on_event(self, evenement)      -> appelé à CHAQUE action (mise à jour en direct)
#   finalize(self, sortie)         -> après la production (facultatif)
# ======================================================================================
class Renderer:
    def on_event(self, evenement: dict) -> None: ...
    def finalize(self, sortie: dict) -> None: ...


class GrapheAnime(Renderer):
    """Le pipeline dessiné (graphviz) ; le nœud actif s'allume, le récit défile à côté."""

    def __init__(self) -> None:
        col_g, col_l = st.columns([1, 1])
        with col_g:
            st.subheader("Pipeline")
            self.zone_graphe = st.empty()
            self.zone_graphe.graphviz_chart(
                rendu.construire_dot(None, set(), None), width="stretch"
            )
        with col_l:
            st.subheader("Déroulé — en direct")
            self.zone_log = st.empty()
        self.lignes: list[str] = []
        self.visites: set[str] = set()

    def on_event(self, evenement: dict) -> None:
        agent = evenement["agent"]
        self.visites.add(agent)
        self.zone_graphe.graphviz_chart(
            rendu.construire_dot(agent, self.visites, rendu.arete_pour(evenement)),
            width="stretch",
        )
        phrase = rendu.phrase_evenement(evenement)
        if phrase is not None:
            self.lignes.append(phrase)
            self.zone_log.markdown("<br>".join(self.lignes), unsafe_allow_html=True)

    def finalize(self, sortie: dict) -> None:
        # Plus de nœud « actif » ; le chemin parcouru reste en teinte pâle.
        self.zone_graphe.graphviz_chart(
            rendu.construire_dot(None, self.visites, None), width="stretch"
        )


class DiagrammeSequence(Renderer):
    """Diagramme de séquence Mermaid, re-rendu à chaque événement."""

    def __init__(self) -> None:
        st.subheader("Diagramme de séquence — en direct")
        self.zone = st.empty()
        self.evenements: list[dict] = []
        self._afficher()

    def _afficher(self) -> None:
        # On utilise components.html (iframe) et NON st.html : Mermaid a besoin d'exécuter du
        # JavaScript, ce qui n'est fiable que dans l'iframe « srcdoc » de components.html.
        # (components.html est déprécié mais fonctionnel ; à migrer si une version le retire.)
        source = rendu.mermaid_sequence(self.evenements)
        with self.zone.container():
            components.html(rendu.bloc_mermaid_html(source), height=540, scrolling=True)

    def on_event(self, evenement: dict) -> None:
        # objectif/observation/cerveau n'ajoutent rien à une séquence → on évite de re-rendre.
        if evenement["type"] in ("outil", "delegation", "retour", "fin", "garde-fou"):
            self.evenements.append(evenement)
            self._afficher()


class CartesNarratives(Renderer):
    """Une carte encadrée par tour d'agent (ouvert par un « objectif »), phrasé « X fait Y »."""

    def __init__(self) -> None:
        st.subheader("Cartes narratives — en direct")
        self.zone = st.container()
        self.carte = None

    def _nouvelle_carte(self, agent: str) -> None:
        self.carte = self.zone.container(border=True)
        self.carte.markdown(
            f"{rendu.pastille(rendu.couleur(agent))} **{agent}**", unsafe_allow_html=True
        )

    def on_event(self, evenement: dict) -> None:
        type_ = evenement["type"]
        if type_ == "cerveau":
            return
        if type_ == "objectif":
            self._nouvelle_carte(evenement["agent"])
            return
        if self.carte is None:
            self._nouvelle_carte(evenement["agent"])
        phrase = rendu.phrase_evenement(evenement)
        if phrase is not None:
            self.carte.markdown(phrase, unsafe_allow_html=True)


class JournalNarratif(Renderer):
    """Le récit ligne à ligne « X fait Y », qui s'allonge en direct."""

    def __init__(self) -> None:
        st.subheader("Journal narratif — en direct")
        self.zone = st.empty()
        self.lignes: list[str] = []

    def on_event(self, evenement: dict) -> None:
        phrase = rendu.phrase_evenement(evenement)
        if phrase is not None:
            self.lignes.append(phrase)
            self.zone.markdown("<br>".join(self.lignes), unsafe_allow_html=True)


class TableauStructure(Renderer):
    """Un tableau (log) qui s'enrichit d'une ligne à chaque action."""

    def __init__(self) -> None:
        st.subheader("Tableau structuré — en direct")
        self.zone = st.empty()
        self.rangees: list[dict] = []

    def on_event(self, evenement: dict) -> None:
        self.rangees.append(rendu.rangee_tableau(evenement))
        self.zone.dataframe(self.rangees, width="stretch", hide_index=True)


class ListeIndentee(Renderer):
    """L'affichage d'origine : l'arbre d'agents indenté par profondeur."""

    def __init__(self) -> None:
        st.subheader("Liste indentée (classique) — en direct")
        self.zone = st.empty()
        self.lignes: list[str] = []

    def on_event(self, evenement: dict) -> None:
        self.lignes.append(rendu.ligne_evenement(evenement))
        self.zone.markdown("<br>".join(self.lignes), unsafe_allow_html=True)


MODES = {
    "Graphe animé": GrapheAnime,
    "Diagramme de séquence": DiagrammeSequence,
    "Cartes narratives": CartesNarratives,
    "Journal narratif": JournalNarratif,
    "Tableau structuré": TableauStructure,
    "Liste indentée (classique)": ListeIndentee,
}


# ======================================================================================
# Page
# ======================================================================================
st.set_page_config(page_title="Usine d'agents — suivi", layout="wide")
st.title("Usine d'agents — suivi de production")
st.caption("Tutoriel d'orchestration multi-agents + MCP. Voir docs/architecture.md.")

config = Config()

with st.sidebar:
    st.header("Affichage")
    mode = st.radio("Mode d'affichage", list(MODES), index=0)
    st.caption("Le même déroulé, présenté de plusieurs façons. À toi de choisir la plus lisible.")

    st.header("Configuration")
    st.write(f"**Cerveau** : `{config.provider}`")
    if config.provider == "ollama":
        st.write(f"**Modèle** : `{config.ollama_model}`")
    st.write(f"**Stock initial** : `{config.stock_initial}`")

    st.header("Recettes")
    for vehicule, recette in RECETTES.items():
        pieces = ", ".join(f"{n} {p}" for p, n in recette.items())
        st.write(f"- **{vehicule}** : {pieces}")

    st.header("Légende")
    for agent, coul in rendu.COULEUR_AGENT.items():
        st.markdown(f"{rendu.pastille(coul)} {agent}", unsafe_allow_html=True)

commande = st.text_input("Commande à produire", value="2 motos + 2 voitures")

if st.button("Lancer la production", type="primary"):
    renderer = MODES[mode]()

    trace = Trace(on_event=renderer.on_event)
    with st.spinner("Production en cours… (l'affichage se met à jour au fur et à mesure)"):
        sortie = asyncio.run(lancer_commande(commande, config, trace))
    renderer.finalize(sortie)

    journal = sortie["trace"].journal

    st.subheader("Résumé")
    colonnes = st.columns(3)
    colonnes[0].metric("Événements", len(journal))
    colonnes[1].metric(
        "Stock final", " · ".join(f"{p}:{n}" for p, n in sortie["etat"]["stock"].items())
    )
    machines_livrees = sum(1 for s in sortie["etat"]["suivi"].values() if s == "livrée")
    colonnes[2].metric("Machines livrées", machines_livrees)

    with st.expander("Voir le journal brut (JSON)"):
        st.json(journal)
    with st.expander("Voir l'état final (stock + suivi)"):
        st.json(sortie["etat"])
else:
    st.info("Choisis un **mode d'affichage** (barre latérale), saisis une commande, puis clique sur **Lancer la production**.")
