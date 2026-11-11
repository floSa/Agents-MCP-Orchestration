"""Mise en forme du journal d'agents — logique PURE, sans Streamlit.

Ce module ne fait que transformer des événements de `Trace` en textes/HTML/DOT/Mermaid.
Il ne dépend PAS de Streamlit, donc il est testable seul (voir tests/test_rendu.py) et
réutilisable par plusieurs modes d'affichage. Le fichier `streamlit_app.py` se contente de
brancher ces fonctions sur des emplacements d'UI qui se mettent à jour en direct.

Un « événement » est le dict produit par `Trace.log` :
    {"ordre", "profondeur", "agent", "type", "nom", "detail"}
"""
from __future__ import annotations

# --------------------------------------------------------------------------------------
# Couleurs & petits helpers HTML
# --------------------------------------------------------------------------------------
COULEUR_AGENT = {
    "Chef d'usine": "#4285f4",  # bleu
    "Assembleur": "#34a853",    # vert
    "Fabricant": "#fbbc04",     # orange
    "Fournisseur": "#a142f4",   # violet
}
COULEUR_DEFAUT = "#9aa0a6"


def couleur(agent: str) -> str:
    return COULEUR_AGENT.get(agent, COULEUR_DEFAUT)


def pastille(coul: str) -> str:
    """Petit carré coloré en HTML (rendu fiable, indépendant des emojis)."""
    return (
        f'<span style="display:inline-block;width:11px;height:11px;border-radius:3px;'
        f'background:{coul};vertical-align:middle;margin-right:6px;"></span>'
    )


def badge(agent: str) -> str:
    """Pastille + nom en gras."""
    return f"{pastille(couleur(agent))}<b>{agent}</b>"


# Libellé lisible par type d'événement.
LIBELLE_TYPE = {
    "objectif": "objectif",
    "outil": "outil",
    "observation": "résultat",
    "delegation": "délègue à",
    "retour": "reçoit de",
    "fin": "termine",
    "cerveau": "modèle (brut)",   # sortie brute du LLM (mode llm)
    "garde-fou": "correction",    # le garde-fou a forcé l'action de référence
}

# --------------------------------------------------------------------------------------
# Câblage de l'arbre d'agents (cf. orchestration.py) + vocabulaire « X fait Y »
# --------------------------------------------------------------------------------------
AGENTS_GRAPHE = ["Chef d'usine", "Assembleur", "Fabricant", "Fournisseur"]
ARETES_GRAPHE = [
    ("Chef d'usine", "Assembleur"),
    ("Chef d'usine", "Fabricant"),
    ("Fabricant", "Fournisseur"),
]
# Quelle délégation mène à quel sous-agent (pour allumer la bonne flèche / le bon message).
CALLEE_DELEGATION = {
    "appeler_assembleur": "Assembleur",
    "appeler_fabricant": "Fabricant",
    "appeler_fournisseur": "Fournisseur",
}
# Étiquette courte de la délégation (message de séquence).
ETIQ_DELEGATION = {
    "appeler_assembleur": "assemble une machine",
    "appeler_fabricant": "produis les pièces",
    "appeler_fournisseur": "fournis la pièce",
}
# Traduction outil → verbe lisible (« X fait Y »).
VERBE_OUTIL = {
    "lire_commande": "lit la commande",
    "suivi_commande": "met à jour le suivi",
    "livrer_commande": "clôture la commande",
    "lire_recette": "lit la recette",
    "interroger_stock": "interroge le stock",
    "assembler_vehicule": "assemble le véhicule",
    "livrer_vehicule": "livre le véhicule",
    "rechercher_fournisseur": "cherche un fournisseur",
    "ajouter_au_stock": "ajoute au stock",
    "fournir_pieces": "fournit des pièces",
}


def verbe_outil(nom: str) -> str:
    return VERBE_OUTIL.get(nom, f"appelle {nom}")


# --------------------------------------------------------------------------------------
# 1) Liste indentée (l'affichage d'origine)
# --------------------------------------------------------------------------------------
def ligne_evenement(evenement: dict) -> str:
    """UNE ligne HTML indentée par profondeur (mode « liste classique »)."""
    marge = "&nbsp;" * (evenement["profondeur"] * 6)
    libelle = LIBELLE_TYPE.get(evenement["type"], evenement["type"])
    nom = f" `{evenement['nom']}`" if evenement["nom"] else ""
    detail = evenement["detail"]
    texte_detail = "" if detail is None else f" — {str(detail)[:160]}"
    return f"{marge}{badge(evenement['agent'])} · {libelle}{nom}{texte_detail}"


# --------------------------------------------------------------------------------------
# 2) Journal narratif « X fait Y »
# --------------------------------------------------------------------------------------
def phrase_evenement(evenement: dict) -> str | None:
    """Une phrase « X fait Y ». Renvoie None si l'événement est du bruit (sortie brute LLM)."""
    agent = evenement["agent"]
    type_ = evenement["type"]
    nom = evenement["nom"]
    detail = evenement["detail"]

    if type_ == "cerveau":          # sortie brute du modèle : gardée dans le JSON, pas dans le récit
        return None
    if type_ == "objectif":
        return f"{badge(agent)} démarre sa tâche"
    if type_ == "outil":
        return f"{badge(agent)} {verbe_outil(nom)}"
    if type_ == "observation":
        texte = "" if detail is None else str(detail)[:120]
        return f'<span style="color:#8a8a8a">&nbsp;&nbsp;&nbsp;&nbsp;↳ {texte}</span>'
    if type_ == "delegation":
        callee = CALLEE_DELEGATION.get(nom, nom)
        return f"{badge(agent)} délègue à {badge(callee)}"
    if type_ == "retour":
        return f'<span style="color:#8a8a8a">&nbsp;&nbsp;&nbsp;&nbsp;↳ {agent} reçoit le résultat</span>'
    if type_ == "fin":
        return f"{badge(agent)} ✓ a terminé"
    if type_ == "garde-fou":
        return f'<span style="color:#c5221f">&nbsp;&nbsp;⚠️ correction → force <code>{nom}</code></span>'
    return f"{badge(agent)} · {type_}"


# --------------------------------------------------------------------------------------
# 3) Graphe animé (DOT / graphviz)
# --------------------------------------------------------------------------------------
def _pale(hexc: str, f: float = 0.16) -> str:
    """Teinte pâle d'une couleur (mélange f de couleur, le reste en blanc)."""
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    r = round(r * f + 255 * (1 - f))
    g = round(g * f + 255 * (1 - f))
    b = round(b * f + 255 * (1 - f))
    return f"#{r:02x}{g:02x}{b:02x}"


def construire_dot(actif: str | None, visites, arete_active=None) -> str:
    """Graphe DOT du pipeline : nœud actif allumé, nœuds déjà passés en teinte pâle."""
    visites = visites or set()
    lignes = [
        "digraph {",
        '  rankdir=BT; bgcolor="transparent"; pad=0.2; nodesep=0.5; ranksep=0.6;',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica",'
        ' fontsize=13, penwidth=1, color="#d0d0d0", fillcolor="#ffffff"];',
        '  edge [color="#c0c0c0", penwidth=1, arrowsize=0.8];',
    ]
    for ag in AGENTS_GRAPHE:
        coul = COULEUR_AGENT[ag]
        if ag == actif:
            style = f'fillcolor="{coul}", fontcolor="white", color="#222222", penwidth=3'
        elif ag in visites:
            style = f'fillcolor="{_pale(coul)}", fontcolor="#222222", color="{coul}", penwidth=1.6'
        else:
            style = 'fillcolor="#ffffff", fontcolor="#888888"'
        lignes.append(f'  "{ag}" [{style}];')
    for a, b in ARETES_GRAPHE:
        if arete_active == (a, b):
            lignes.append(f'  "{a}" -> "{b}" [color="#222222", penwidth=2.6];')
        else:
            lignes.append(f'  "{a}" -> "{b}";')
    lignes.append("}")
    return "\n".join(lignes)


def arete_pour(evenement: dict):
    """Pour un événement de délégation, l'arête (appelant → sous-agent) à allumer."""
    if evenement["type"] != "delegation":
        return None
    callee = CALLEE_DELEGATION.get(evenement["nom"])
    return (evenement["agent"], callee) if callee else None


# --------------------------------------------------------------------------------------
# 4) Diagramme de séquence (Mermaid, rendu via un iframe HTML)
# --------------------------------------------------------------------------------------
# Alias courts (les noms avec espace/apostrophe passent mal comme identifiants Mermaid).
ALIAS_SEQ = {
    "Chef d'usine": "Chef",
    "Assembleur": "Assembleur",
    "Fabricant": "Fabricant",
    "Fournisseur": "Fournisseur",
}
# Ordre des colonnes (gauche → droite) du diagramme de séquence. Volontairement différent
# de AGENTS_GRAPHE : ici l'Assembleur est à gauche du Chef d'usine, plus lisible à l'usage.
ORDRE_SEQ = ["Assembleur", "Chef d'usine", "Fabricant", "Fournisseur"]


def _echappe_mermaid(texte: str) -> str:
    """Neutralise les caractères qui casseraient un libellé de message Mermaid."""
    return (
        str(texte)
        .replace("\n", " ")
        .replace(";", ",")
        .replace(":", " -")
        .replace("#", "n°")
        .replace("<", "‹")
        .replace(">", "›")
    )


def mermaid_sequence(evenements, bas_vers_haut: bool = True) -> str:
    """Construit un `sequenceDiagram` Mermaid à partir des événements accumulés.

    Mermaid dessine toujours le temps de haut en bas. Pour un déroulé LU DE BAS EN HAUT
    (1re action en bas, dernière en haut), on empile les messages dans l'ordre INVERSE :
    c'est `bas_vers_haut=True` (défaut).
    """
    entete = ["sequenceDiagram"]
    for ag in ORDRE_SEQ:
        entete.append(f"  participant {ALIAS_SEQ[ag]} as {ag}")

    messages: list[str] = []
    for ev in evenements:
        agent = ALIAS_SEQ.get(ev["agent"], ev["agent"])
        type_ = ev["type"]
        nom = ev["nom"]
        if type_ == "outil":
            messages.append(f"  {agent}->>{agent}: {_echappe_mermaid(verbe_outil(nom))}")
        elif type_ == "delegation":
            callee = CALLEE_DELEGATION.get(nom)
            if callee:
                etq = ETIQ_DELEGATION.get(nom, "délègue")
                messages.append(f"  {agent}->>{ALIAS_SEQ[callee]}: {_echappe_mermaid(etq)}")
        elif type_ == "retour":
            callee = CALLEE_DELEGATION.get(nom)
            if callee:
                messages.append(f"  {ALIAS_SEQ[callee]}-->>{agent}: résultat")
        elif type_ == "fin":
            messages.append(f"  Note over {agent}: ✓ terminé")
        elif type_ == "garde-fou":
            messages.append(f"  Note over {agent}: ⚠ correction {_echappe_mermaid(nom)}")
        # objectif / observation / cerveau : volontairement omis (bruit dans une séquence)

    if bas_vers_haut:
        messages.reverse()
    return "\n".join(entete + messages)


def bloc_mermaid_html(source: str, hauteur: int = 520) -> str:
    """Enveloppe HTML autonome qui rend un diagramme Mermaid (module chargé via CDN)."""
    return f"""
<div style="background:white;border-radius:8px;padding:10px;overflow:auto;height:{hauteur - 24}px">
  <pre class="mermaid">{source}</pre>
</div>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' }});
  await mermaid.run({{ querySelector: '.mermaid' }});
</script>
"""


# --------------------------------------------------------------------------------------
# 5) Tableau structuré
# --------------------------------------------------------------------------------------
def libelle_action(evenement: dict) -> str:
    """Colonne « action » du tableau : type lisible + nom éventuel."""
    libelle = LIBELLE_TYPE.get(evenement["type"], evenement["type"])
    return f"{libelle} {evenement['nom']}".strip()


def rangee_tableau(evenement: dict) -> dict:
    """Une ligne de tableau (dict de colonnes) pour un événement."""
    detail = evenement["detail"]
    return {
        "#": evenement["ordre"],
        "prof.": evenement["profondeur"],
        "agent": evenement["agent"],
        "action": libelle_action(evenement),
        "détail": "" if detail is None else str(detail)[:200],
    }
