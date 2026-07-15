"""Configuration et données de référence.

- Les **recettes** (nomenclatures) : combien de pièces par type de machine.
- La **configuration** lue depuis l'environnement (.env) : choix du cerveau (fake/ollama),
  URL/modèle Ollama, stock initial, graine aléatoire.
- Un petit analyseur de commande texte → liste de machines à produire.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Charge le .env à la racine du projet, quel que soit le répertoire courant de lancement.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# --------------------------------------------------------------------------------------
# Recettes : pour chaque type de machine, le nombre de pièces nécessaires.
# C'est la "nomenclature" de l'usine.
# --------------------------------------------------------------------------------------
RECETTES: dict[str, dict[str, int]] = {
    "moto":    {"roue": 2, "batterie": 1, "chassis": 1},
    "voiture": {"roue": 4, "batterie": 3, "chassis": 2},
    "camion":  {"roue": 4, "batterie": 8, "chassis": 4},
}

# Pour comprendre "2 motos" → type "moto".
_SINGULIER = {
    "motos": "moto", "moto": "moto",
    "voitures": "voiture", "voiture": "voiture",
    "camions": "camion", "camion": "camion",
}


@dataclass
class Config:
    """Configuration de l'exécution, alimentée par l'environnement."""

    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "fake"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:e4b"))
    stock_initial: dict[str, int] = field(
        default_factory=lambda: _parser_stock(os.getenv("STOCK_INITIAL", "roue:3,batterie:2,chassis:1"))
    )
    seed: int | None = field(default_factory=lambda: _parser_seed(os.getenv("SEED", "")))


def _parser_stock(texte: str) -> dict[str, int]:
    """'roue:3,batterie:2' → {'roue': 3, 'batterie': 2}."""
    stock: dict[str, int] = {}
    for morceau in texte.split(","):
        morceau = morceau.strip()
        if not morceau or ":" not in morceau:
            continue
        piece, quantite = morceau.split(":", 1)
        try:
            stock[piece.strip()] = int(quantite)
        except ValueError:
            continue
    return stock


def _parser_seed(texte: str) -> int | None:
    texte = (texte or "").strip()
    return int(texte) if texte.isdigit() else None


def analyser_commande(texte: str) -> list[dict]:
    """Transforme un texte de commande en liste de machines à produire.

    Exemple : "2 motos + 2 voitures" → [
        {"id": "moto#1", "vehicule": "moto"},
        {"id": "moto#2", "vehicule": "moto"},
        {"id": "voiture#1", "vehicule": "voiture"},
        {"id": "voiture#2", "vehicule": "voiture"},
    ]
    """
    machines: list[dict] = []
    compteurs: dict[str, int] = {}

    # On découpe sur les séparateurs courants : + , et "et".
    for morceau in re.split(r"[+,]|\bet\b", texte.lower()):
        morceau = morceau.strip()
        if not morceau:
            continue
        # "2 motos" → quantité 2, mot "motos"
        correspondance = re.match(r"(\d+)?\s*([a-zàâäéèêëïîôöùûüç]+)", morceau)
        if not correspondance:
            continue
        quantite = int(correspondance.group(1) or "1")
        mot = correspondance.group(2)
        type_machine = _SINGULIER.get(mot)
        if type_machine is None:
            continue  # mot inconnu, on ignore
        for _ in range(quantite):
            compteurs[type_machine] = compteurs.get(type_machine, 0) + 1
            machines.append({
                "id": f"{type_machine}#{compteurs[type_machine]}",
                "vehicule": type_machine,
            })
    return machines
