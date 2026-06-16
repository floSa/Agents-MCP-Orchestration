"""Tests de `usine.config` : analyse de commande + parseurs de configuration.

Ces tests valent aussi comme **documentation** du langage de commande accepté.
"""
from __future__ import annotations

from usine.config import (
    RECETTES,
    _parser_seed,
    _parser_stock,
    analyser_commande,
)


# --- analyser_commande ----------------------------------------------------------------
def test_commande_simple():
    machines = analyser_commande("2 motos + 2 voitures")
    assert machines == [
        {"id": "moto#1", "vehicule": "moto"},
        {"id": "moto#2", "vehicule": "moto"},
        {"id": "voiture#1", "vehicule": "voiture"},
        {"id": "voiture#2", "vehicule": "voiture"},
    ]


def test_quantite_implicite_vaut_un():
    # "moto" sans nombre = 1 machine.
    assert analyser_commande("moto") == [{"id": "moto#1", "vehicule": "moto"}]


def test_singulier_et_pluriel_equivalents():
    assert analyser_commande("1 camion") == analyser_commande("1 camions")


def test_separateurs_varies():
    # +, virgule et "et" sont tous acceptés comme séparateurs.
    par_plus = analyser_commande("1 moto + 1 voiture")
    par_virgule = analyser_commande("1 moto, 1 voiture")
    par_et = analyser_commande("1 moto et 1 voiture")
    assert par_plus == par_virgule == par_et


def test_mot_inconnu_ignore():
    # "tank" n'est pas une machine connue : il est ignoré, le reste passe.
    machines = analyser_commande("2 tanks + 1 moto")
    assert machines == [{"id": "moto#1", "vehicule": "moto"}]


def test_compteur_par_type_independant():
    # Les identifiants sont numérotés par type, pas globalement.
    machines = analyser_commande("1 moto + 1 voiture + 1 moto")
    ids = [m["id"] for m in machines]
    assert ids == ["moto#1", "voiture#1", "moto#2"]


def test_commande_vide():
    assert analyser_commande("") == []


def test_tous_les_vehicules_ont_une_recette():
    # Garde-fou : tout type produit par l'analyseur doit avoir une recette.
    for machine in analyser_commande("1 moto + 1 voiture + 1 camion"):
        assert machine["vehicule"] in RECETTES


# --- _parser_stock --------------------------------------------------------------------
def test_parser_stock_nominal():
    assert _parser_stock("roue:3,batterie:2,chassis:1") == {
        "roue": 3,
        "batterie": 2,
        "chassis": 1,
    }


def test_parser_stock_tolere_espaces_et_morceaux_invalides():
    # Espaces autour, morceau sans ":" et quantité non entière : ignorés proprement.
    assert _parser_stock(" roue : 3 , nimportequoi , batterie:x ") == {"roue": 3}


def test_parser_stock_vide():
    assert _parser_stock("") == {}


# --- _parser_seed ---------------------------------------------------------------------
def test_parser_seed_entier():
    assert _parser_seed("42") == 42


def test_parser_seed_vide_ou_invalide_vaut_none():
    assert _parser_seed("") is None
    assert _parser_seed("abc") is None
