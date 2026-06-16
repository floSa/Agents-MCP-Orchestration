"""État partagé du système : le `stock` et le `suivi_commande`.

> **EXEMPLE MÉTIER** — propre à l'usine ; à remplacer par l'état de VOTRE domaine.


C'est la **mémoire commune** :
- le **stock** est lu par l'Assembleur (`interroger_stock`), consommé par lui (`assembler_vehicule`),
  et alimenté par le Fabricant (`ajouter_au_stock`) ;
- le **suivi_commande** est géré par le Chef d'usine pour savoir où en est chaque machine.

L'Assembleur et le Fournisseur, eux, sont **sans mémoire** : ils relisent l'état à chaque appel.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Etat:
    """Conteneur de l'état partagé. Volontairement simple (mono-processus)."""

    stock: dict[str, int] = field(default_factory=dict)
    suivi: dict[str, str] = field(default_factory=dict)

    @classmethod
    def depuis_config(cls, config) -> "Etat":
        """Crée un état initialisé avec le stock de départ défini dans la config."""
        return cls(stock=dict(config.stock_initial), suivi={})

    # --- stock ---------------------------------------------------------------
    def interroger_stock(self) -> dict[str, int]:
        """Renvoie une copie du stock (lecture seule pour l'appelant)."""
        return dict(self.stock)

    def ajouter(self, piece: str, quantite: int) -> int:
        """Ajoute des pièces au stock (utilisé par le Fabricant). Renvoie le nouveau total."""
        self.stock[piece] = self.stock.get(piece, 0) + int(quantite)
        return self.stock[piece]

    def consommer(self, recette: dict[str, int]) -> dict[str, int]:
        """Retire du stock les pièces d'une recette (utilisé à l'assemblage)."""
        for piece, quantite in recette.items():
            self.stock[piece] = self.stock.get(piece, 0) - quantite
        return dict(self.stock)

    # --- suivi ---------------------------------------------------------------
    def maj_suivi(self, machine_id: str, statut: str) -> str:
        """Met à jour l'état d'une machine dans le suivi de commande."""
        self.suivi[machine_id] = statut
        return statut

    # --- divers --------------------------------------------------------------
    def snapshot(self) -> dict:
        """Photo de l'état, pratique pour l'affichage final."""
        return {"stock": dict(self.stock), "suivi": dict(self.suivi)}
