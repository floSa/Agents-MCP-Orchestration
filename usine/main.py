"""Lancement en ligne de commande.

Exemple :
    uv run python -m usine.main "2 motos + 2 voitures"

Affiche le journal complet (arbre d'agents indenté par profondeur), puis le stock final.
"""
from __future__ import annotations

import asyncio
import sys

from usine.config import Config
from usine.orchestration import lancer_commande

# La console Windows est parfois en cp1252 : on force l'UTF-8 pour les symboles du journal.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

def afficher_journal(journal: list[dict]) -> None:
    for evenement in journal:
        marge = "    " * evenement["profondeur"]
        detail = evenement["detail"]
        texte_detail = "" if detail is None else f" {detail}"
        print(f'{evenement["ordre"]:>3} {marge}[{evenement["agent"]}] '
              f'{evenement["type"]} {evenement["nom"]}{texte_detail}')


def main() -> None:
    commande = " ".join(sys.argv[1:]).strip() or "2 motos + 2 voitures"
    config = Config()

    print(f"Commande : {commande}")
    print(f"Cerveau  : {config.provider}")
    print(f"Stock initial : {config.stock_initial}\n")

    sortie = asyncio.run(lancer_commande(commande, config))

    afficher_journal(sortie["trace"].journal)
    print("\nStock final :", sortie["etat"]["stock"])
    print("Suivi       :", sortie["etat"]["suivi"])
    print("Résultat    :", sortie["resultat"])


if __name__ == "__main__":
    main()
