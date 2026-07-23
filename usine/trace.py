"""Journal d'événements : enregistre TOUT ce que font les agents.

Chaque action (objectif, appel d'outil, observation, délégation, retour, fin) est consignée
avec sa **profondeur** dans l'arbre d'agents. C'est ce journal que l'interface Streamlit affiche
pour qu'on puisse « se balader » dans le déroulé.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

# Types d'événements possibles (pour information / filtrage côté UI) :
#   "objectif"    : un agent démarre une tâche
#   "outil"       : un agent appelle un outil de son MCP
#   "observation" : le résultat renvoyé par l'outil
#   "delegation"  : un agent appelle un sous-agent
#   "retour"      : le résultat renvoyé par le sous-agent
#   "fin"         : un agent termine et renvoie son résultat


@dataclass
class Trace:
    """Collecteur d'événements, en mémoire (et exportable en JSONL).

    `on_event`, s'il est fourni, est appelé avec CHAQUE événement au moment où il est
    journalisé — c'est ce qui permet un affichage EN DIRECT (ex. Streamlit) au lieu
    d'attendre la fin de la production. Il reste optionnel : sans lui, rien ne change.
    """

    journal: list[dict] = field(default_factory=list)
    on_event: Optional[Callable[[dict], None]] = None

    def log(self, profondeur: int, agent: str, type_: str, nom: str = "", detail=None) -> dict:
        """Ajoute un événement au journal, notifie l'observateur éventuel, et le renvoie."""
        evenement = {
            "ordre": len(self.journal) + 1,
            "profondeur": profondeur,
            "agent": agent,
            "type": type_,
            "nom": nom,
            "detail": detail,
        }
        self.journal.append(evenement)
        if self.on_event is not None:
            self.on_event(evenement)
        return evenement

    def to_jsonl(self, chemin: str) -> None:
        """Exporte le journal au format JSON Lines (un événement par ligne)."""
        with open(chemin, "w", encoding="utf-8") as fichier:
            for evenement in self.journal:
                fichier.write(json.dumps(evenement, ensure_ascii=False) + "\n")
