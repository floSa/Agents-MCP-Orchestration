"""Tests d'intégration : `lancer_commande` de bout en bout (cerveau déterministe).

Ces tests câblent les 4 vrais agents et leurs MCP, et font tourner une commande complète.
Avec une graine fixe, le résultat est entièrement reproductible — c'est ce qui rend le mode
`fake` si pratique pour apprendre et tester.
"""
from __future__ import annotations

import asyncio

import pytest

from usine.config import Config

# `usine.orchestration` importe FastMCP, qui sur Windows dépend de pywin32. Quand le venv est
# sur un montage réseau (chemin `\\?\UNC\...`, ex. projet WSL ouvert depuis Windows), le chargement
# de la DLL pywin32 échoue UNIQUEMENT au sein de pytest. Le moteur, lui, tourne (voir `usine.main`).
# On saute donc proprement ces tests dans ce cas ; ils s'exécutent normalement ailleurs (CI Linux).
try:
    from usine.orchestration import lancer_commande
except ImportError as exc:  # pragma: no cover - dépend de l'environnement
    pytest.skip(f"FastMCP indisponible ici ({exc}).", allow_module_level=True)


def _config(seed=42, stock="roue:3,batterie:2,chassis:1"):
    """Config isolée de l'environnement, en mode `fake`, graine fixe."""
    from usine.config import _parser_stock

    config = Config()
    config.provider = "fake"
    config.seed = seed
    config.stock_initial = _parser_stock(stock)
    return config


def _lancer(commande, config=None):
    return asyncio.run(lancer_commande(commande, config or _config()))


# --- comportement nominal -------------------------------------------------------------
def test_commande_complete_est_livree():
    sortie = _lancer("2 motos + 2 voitures")
    suivi = sortie["etat"]["suivi"]
    assert suivi == {
        "moto#1": "fini",
        "moto#2": "fini",
        "voiture#1": "fini",
        "voiture#2": "fini",
    }
    assert sortie["resultat"]["statut"] == "commande_livrée"
    assert sortie["resultat"]["machines"] == ["moto#1", "moto#2", "voiture#1", "voiture#2"]


def test_resultat_reproductible_avec_graine_fixe():
    # Graine 42 + ce stock initial → exactement ce stock final (valeur de référence).
    sortie = _lancer("2 motos + 2 voitures")
    assert sortie["etat"]["stock"] == {"roue": 3, "batterie": 2, "chassis": 2}


def test_deux_executions_identiques_a_graine_egale():
    a = _lancer("2 motos + 2 voitures")
    b = _lancer("2 motos + 2 voitures")
    assert a["etat"] == b["etat"]
    assert len(a["trace"].journal) == len(b["trace"].journal)


# --- structure de l'arbre d'agents ----------------------------------------------------
def test_la_trace_contient_les_quatre_agents():
    sortie = _lancer("1 voiture")
    agents = {e["agent"] for e in sortie["trace"].journal}
    assert agents == {"Chef d'usine", "Assembleur", "Fabricant", "Fournisseur"}


def test_la_profondeur_atteint_le_fournisseur():
    # Chef (0) → Fabricant (1) → Fournisseur (2) : la profondeur 2 prouve la délégation imbriquée.
    sortie = _lancer("1 voiture")
    profondeurs = {e["profondeur"] for e in sortie["trace"].journal}
    assert max(profondeurs) == 2
    fournisseur = [e for e in sortie["trace"].journal if e["agent"] == "Fournisseur"]
    assert all(e["profondeur"] == 2 for e in fournisseur)


# --- robustesse de l'analyse de commande ----------------------------------------------
def test_le_suivi_passe_par_en_cours_puis_fini():
    # Cycle de vie d'une machine, visible dans la trace : "en cours" puis "fini".
    sortie = _lancer("1 moto")
    statuts = [
        e["detail"]["args"]["statut"]
        for e in sortie["trace"].journal
        if e["agent"] == "Chef d'usine" and e["type"] == "outil" and e["nom"] == "suivi_commande"
    ]
    assert statuts == ["en cours", "fini"]


def test_camion_seul_est_produit():
    sortie = _lancer("1 camion")
    assert sortie["etat"]["suivi"] == {"camion#1": "fini"}


def test_stock_suffisant_evite_le_fabricant():
    # Stock pléthorique → l'Assembleur n'a jamais besoin du Fabricant.
    config = _config(stock="roue:100,batterie:100,chassis:100")
    sortie = _lancer("1 moto", config)
    agents = {e["agent"] for e in sortie["trace"].journal}
    assert "Fabricant" not in agents
    assert sortie["etat"]["suivi"] == {"moto#1": "fini"}
