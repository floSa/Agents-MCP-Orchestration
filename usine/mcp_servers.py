"""Les serveurs MCP (FastMCP) — un par agent.

Chaque agent a SON MCP, c'est-à-dire SA boîte à outils :

- `pilotage`    → outils du Chef d'usine
- `atelier`     → outils de l'Assembleur
- `fabrication` → outils du Fabricant
- `fournisseur` → outils du Fournisseur

Les serveurs sont construits par des *fabriques* qui « capturent » l'état partagé `etat`,
de sorte que les outils lisent/écrivent la même mémoire commune. Les outils sont des **stubs**
(ils renvoient un jeton lisible), sauf `fournir_pieces` qui tire un nombre aléatoire 1–5 :
c'est précisément ce hasard qui force la **boucle** du Fabricant.

On les appellera via un **client FastMCP en mémoire** (pas de sous-processus) — voir orchestration.py.
"""
from __future__ import annotations

import random

from fastmcp import FastMCP

from usine.config import RECETTES, analyser_commande
from usine.etat import Etat


# --------------------------------------------------------------------------------------
# MCP du Chef d'usine
# --------------------------------------------------------------------------------------
def construire_pilotage(etat: Etat) -> FastMCP:
    mcp = FastMCP("pilotage")

    @mcp.tool
    def lire_commande(commande: str) -> list[dict]:
        """Analyse le texte de commande et renvoie la liste des machines à produire."""
        return analyser_commande(commande)

    @mcp.tool
    def suivi_commande(machine_id: str = "", statut: str = "") -> dict:
        """Lit l'avancement (sans argument) ou met à jour l'état d'une machine."""
        if machine_id and statut:
            etat.maj_suivi(machine_id, statut)
        return dict(etat.suivi)

    @mcp.tool
    def livrer_commande(machines: list[str]) -> str:
        """Clôt la commande une fois toutes les machines livrées."""
        return f"[commande livrée : {', '.join(machines)}]"

    return mcp


# --------------------------------------------------------------------------------------
# MCP de l'Assembleur
# --------------------------------------------------------------------------------------
def construire_atelier(etat: Etat) -> FastMCP:
    mcp = FastMCP("atelier")

    @mcp.tool
    def lire_recette(vehicule: str) -> dict:
        """Renvoie la nomenclature (pièces nécessaires) du véhicule."""
        return dict(RECETTES.get(vehicule, {}))

    @mcp.tool
    def interroger_stock() -> dict:
        """Renvoie l'état courant du stock partagé."""
        return etat.interroger_stock()

    @mcp.tool
    def assembler_vehicule(vehicule: str) -> str:
        """Assemble le véhicule en CONSOMMANT les pièces correspondantes dans le stock."""
        etat.consommer(RECETTES.get(vehicule, {}))
        return f"[{vehicule} assemblé]"

    @mcp.tool
    def livrer_vehicule(vehicule: str) -> str:
        """Livre le véhicule assemblé."""
        return f"[{vehicule} livré]"

    return mcp


# --------------------------------------------------------------------------------------
# MCP du Fabricant
# --------------------------------------------------------------------------------------
def construire_fabrication(etat: Etat) -> FastMCP:
    mcp = FastMCP("fabrication")

    @mcp.tool
    def rechercher_fournisseur(piece: str) -> str:
        """Trouve un fournisseur pour la pièce demandée (stub)."""
        return f"[fournisseur trouvé pour {piece}]"

    @mcp.tool
    def ajouter_au_stock(piece: str, quantite: int) -> dict:
        """Ajoute les pièces fabriquées au stock partagé. Renvoie le stock à jour."""
        etat.ajouter(piece, quantite)
        return etat.interroger_stock()

    return mcp


# --------------------------------------------------------------------------------------
# MCP du Fournisseur
# --------------------------------------------------------------------------------------
def construire_fournisseur(etat: Etat, config) -> FastMCP:
    mcp = FastMCP("fournisseur")
    # Générateur aléatoire, reproductible si une graine est fournie dans la config.
    rng = random.Random(config.seed)

    @mcp.tool
    def fournir_pieces(piece: str) -> dict:
        """Livre un lot ALÉATOIRE de 1 à 5 pièces (c'est ce qui crée la boucle du Fabricant)."""
        quantite = rng.randint(1, 5)
        return {"piece": piece, "quantite": quantite}

    return mcp
