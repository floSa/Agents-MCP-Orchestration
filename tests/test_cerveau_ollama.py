"""Tests du `CerveauOllama` — SANS serveur Ollama.

On teste :
- l'extraction JSON robuste et la conversion en `Action` (fonctions pures) ;
- `decider()` en remplaçant l'appel réseau par un faux (monkeypatch), pour vérifier le
  parsing de la réponse et la relance en cas de JSON invalide.
"""
from __future__ import annotations

import asyncio

import pytest

from usine.cerveau import (
    CerveauOllama,
    _extraire_json,
    _vers_action,
)
from usine.config import Config
from usine.etat import Etat


# --- _extraire_json -------------------------------------------------------------------
def test_extraire_json_propre():
    assert _extraire_json('{"action": "terminer"}') == {"action": "terminer"}


def test_extraire_json_tolere_du_texte_autour():
    texte = 'Voici ma réponse : {"action": "outil", "nom": "x"} (voilà).'
    assert _extraire_json(texte) == {"action": "outil", "nom": "x"}


def test_extraire_json_renvoie_none_si_inexploitable():
    assert _extraire_json("pas de json ici") is None
    assert _extraire_json("") is None


# --- _vers_action ---------------------------------------------------------------------
def test_vers_action_terminer():
    action = _vers_action({"action": "terminer", "resultat": {"statut": "livré"}})
    assert action.type == "terminer" and action.resultat == {"statut": "livré"}


def test_vers_action_deleguer():
    action = _vers_action({"action": "deleguer", "nom": "appeler_fournisseur", "args": {"piece": "roue"}})
    assert action.type == "deleguer" and action.nom == "appeler_fournisseur"
    assert action.args == {"piece": "roue"}


def test_vers_action_outil_par_defaut():
    # Toute action non reconnue est traitée comme un appel d'outil.
    action = _vers_action({"action": "outil", "nom": "interroger_stock", "args": {}})
    assert action.type == "outil" and action.nom == "interroger_stock"


# --- decider() avec appel réseau simulé -----------------------------------------------
class _AgentFactice:
    nom = "Fournisseur"
    role = "Tu livres des pièces."

    def noms_outils(self):
        return ["fournir_pieces"]

    def noms_delegations(self):
        return []

    catalogue = {"fournir_pieces": "livre 1 à 5 pièces. args: {piece: str}"}


def test_decider_parse_la_reponse_du_modele(monkeypatch):
    cerveau = CerveauOllama(Config())

    async def faux_appel(messages):
        return '{"action": "outil", "nom": "fournir_pieces", "args": {"piece": "roue"}}'

    monkeypatch.setattr(cerveau, "_appeler", faux_appel)
    action = asyncio.run(cerveau.decider(_AgentFactice(), {"piece": "roue"}, [], Etat()))
    assert action.type == "outil" and action.nom == "fournir_pieces"


def test_decider_relance_une_fois_puis_abandonne(monkeypatch):
    cerveau = CerveauOllama(Config())
    appels = {"n": 0}

    async def toujours_invalide(messages):
        appels["n"] += 1
        return "ceci n'est pas du json"

    monkeypatch.setattr(cerveau, "_appeler", toujours_invalide)
    with pytest.raises(ValueError):
        asyncio.run(cerveau.decider(_AgentFactice(), {"piece": "roue"}, [], Etat()))
    # Une tentative + une relance = 2 appels.
    assert appels["n"] == 2
