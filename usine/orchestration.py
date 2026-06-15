"""Assemble tout : crée les MCP, les clients, les 4 agents, et lance une commande.

C'est ici qu'on câble l'arbre d'agents :

    Chef d'usine
      ├── appeler_assembleur → Assembleur (atelier)
      └── appeler_fabricant  → Fabricant (fabrication)
                                  └── appeler_fournisseur → Fournisseur (fournisseur)

Chaque agent reçoit le client FastMCP de SON serveur (boîte à outils), et les délégations
nécessaires pour appeler ses sous-agents.
"""
from __future__ import annotations

from contextlib import AsyncExitStack

from fastmcp import Client

from usine.agent import Agent
from usine.cerveau import construire_cerveau
from usine.etat import Etat
from usine.mcp_servers import (
    construire_atelier,
    construire_fabrication,
    construire_fournisseur,
    construire_pilotage,
)
from usine.trace import Trace

# Rôles (utilisés notamment par le cerveau Ollama pour cadrer chaque agent).
ROLE_CHEF = (
    "Tu orchestres la production. Pour chaque machine de la commande, fais assembler par "
    "l'Assembleur ; s'il manque des pièces, fais-les produire par le Fabricant, puis relance "
    "l'Assembleur. Quand tout est livré, clôture la commande."
)
ROLE_ASSEMBLEUR = (
    "Tu assembles UNE machine. Lis la recette, interroge le stock ; si tout est dispo, assemble "
    "puis livre ; sinon, renvoie la liste des pièces manquantes (besoin − stock)."
)
ROLE_FABRICANT = (
    "Tu produis les pièces manquantes. Pour chaque pièce, trouve un fournisseur puis commande en "
    "boucle jusqu'à obtenir la quantité demandée, et verse le tout au stock."
)
ROLE_FOURNISSEUR = "Tu livres un lot de pièces (quantité aléatoire) pour la pièce demandée."


async def lancer_commande(commande_texte: str, config, trace: Trace | None = None) -> dict:
    """Lance la production pour une commande texte et renvoie résultat + trace + état final."""
    etat = Etat.depuis_config(config)
    trace = trace or Trace()
    cerveau = construire_cerveau(config)

    # Un serveur MCP par agent (chacun capture l'état partagé).
    serveurs = {
        "pilotage": construire_pilotage(etat),
        "atelier": construire_atelier(etat),
        "fabrication": construire_fabrication(etat),
        "fournisseur": construire_fournisseur(etat, config),
    }

    # On ouvre un client FastMCP « en mémoire » par serveur (pas de sous-processus).
    async with AsyncExitStack() as pile:
        cli = {
            nom: await pile.enter_async_context(Client(serveur))
            for nom, serveur in serveurs.items()
        }

        # --- Fournisseur (feuille de l'arbre) --------------------------------
        fournisseur = Agent(
            "Fournisseur", ROLE_FOURNISSEUR,
            clients_par_outil={"fournir_pieces": cli["fournisseur"]},
            delegations={},
            cerveau=cerveau, trace=trace, etat=etat,
        )

        # --- Fabricant (appelle le Fournisseur) ------------------------------
        async def appeler_fournisseur(args, profondeur):
            return await fournisseur.executer({"piece": args["piece"]}, profondeur)

        fabricant = Agent(
            "Fabricant", ROLE_FABRICANT,
            clients_par_outil={
                "rechercher_fournisseur": cli["fabrication"],
                "ajouter_au_stock": cli["fabrication"],
            },
            delegations={"appeler_fournisseur": appeler_fournisseur},
            cerveau=cerveau, trace=trace, etat=etat,
        )

        # --- Assembleur ------------------------------------------------------
        assembleur = Agent(
            "Assembleur", ROLE_ASSEMBLEUR,
            clients_par_outil={
                "lire_recette": cli["atelier"],
                "interroger_stock": cli["atelier"],
                "assembler_vehicule": cli["atelier"],
                "livrer_vehicule": cli["atelier"],
            },
            delegations={},
            cerveau=cerveau, trace=trace, etat=etat,
        )

        # --- Chef d'usine (orchestrateur) ------------------------------------
        async def appeler_assembleur(args, profondeur):
            return await assembleur.executer(
                {"machine_id": args["machine_id"], "vehicule": args["vehicule"]}, profondeur
            )

        async def appeler_fabricant(args, profondeur):
            return await fabricant.executer({"manquants": args["manquants"]}, profondeur)

        chef = Agent(
            "Chef d'usine", ROLE_CHEF,
            clients_par_outil={
                "lire_commande": cli["pilotage"],
                "suivi_commande": cli["pilotage"],
                "livrer_commande": cli["pilotage"],
            },
            delegations={
                "appeler_assembleur": appeler_assembleur,
                "appeler_fabricant": appeler_fabricant,
            },
            cerveau=cerveau, trace=trace, etat=etat,
        )

        resultat = await chef.executer({"commande": commande_texte}, profondeur=0)

    return {"resultat": resultat, "trace": trace, "etat": etat.snapshot()}
