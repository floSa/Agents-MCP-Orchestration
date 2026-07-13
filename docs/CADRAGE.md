# Cadrage — MCP-Orchestration (Usine d'agents)

Ce document décrit le **pourquoi** du projet (objectifs, périmètre, hypothèses, décisions).
Le **comment** (composants, flux, règles) est dans [`architecture.md`](architecture.md) ;
le guide de réutilisation est dans [`adapter-a-votre-projet.md`](adapter-a-votre-projet.md).

## 1. Pitch

Tutoriel d'orchestration multi-agents + MCP sur un fil rouge concret : une usine qui fabrique
des machines à la commande. Trois capacités :

1. **Montrer les cas de figure de l'orchestration** sur un seul exemple : orchestrateur,
   sous-agents, boucles, réutilisation d'agents, profondeur (un agent qui appelle un agent),
   état partagé.
2. **Exposer les outils via MCP** : un serveur FastMCP par agent, appelé par un client en mémoire.
3. **Rendre l'arbre explorable** : chaque action est journalisée par profondeur et affichée dans
   une interface Streamlit ; le mode `fake` (cerveau déterministe) rend l'exécution reproductible.

---

## 2. Objectifs & périmètre

**Dans le périmètre (V1)** :
- Un orchestrateur (Chef d'usine) et trois sous-agents (Assembleur, Fabricant, Fournisseur).
- Les quatre situations d'orchestration : boucle (Fabricant), réutilisation d'un agent (le Chef
  rappelle l'Assembleur), profondeur (Fabricant appelle le Fournisseur), état partagé (stock + suivi).
- Un MCP FastMCP par agent, via un client **en mémoire** (pas de sous-processus).
- Deux cerveaux interchangeables : `fake` (déterministe, référence) et `ollama` (Gemma E4B, expérimental).
- Journal indenté par profondeur + interface de suivi Streamlit.
- Suite `pytest` reproductible grâce à la graine `SEED`.

**Hors périmètre (V1)** :
- Pas de logique de production réelle : les outils sont des **stubs** (ils renvoient un jeton),
  sauf `fournir_pieces` qui tire un aléatoire 1 à 5.
- Pas de persistance externe : l'état est en mémoire, mono-processus (voir [`etat.py`](../usine/etat.py)).
- Pas d'API HTTP exposée : les MCP sont appelés en mémoire ; la seule interface est Streamlit.
- Pas de garantie sur la qualité du cerveau LLM : elle dépend du modèle et du prompt.

---

## 3. Contraintes (fermes)

| Contrainte | Détail |
|---|---|
| Licences | Open-source uniquement (FastMCP et Streamlit en Apache-2.0, httpx / python-dotenv en BSD). |
| Déploiement | Local via `uv`, ou Docker Compose (Ollama + application Streamlit). |
| Matériel | Aucun en mode `fake`. En mode `ollama` : un modèle local léger (Gemma E4B) via Ollama. |
| Langage | Python **≥ 3.11** (voir [`pyproject.toml`](../pyproject.toml)). |

---

## 4. Hypothèses

Hypothèses non lisibles directement dans le code, posées volontairement :

- **La règle d'or** : on ne met un **agent** (donc un LLM, donc du coût et de l'incertitude) que là
  où il y a une **vraie décision** ou une **itération de longueur inconnue**. Tout le reste reste du
  code déterministe (un outil MCP). Ce qui la remettrait en cause : l'apparition d'un choix flou
  supplémentaire justifiant un nouvel agent. Dans l'exemple, le Fabricant est un agent **parce qu'il
  boucle** (le Fournisseur renvoie 1 à 5 pièces au hasard) ; s'il livrait toujours la quantité
  demandée, il ne serait qu'un outil.
- **Un MCP par agent** : chaque agent a sa propre boîte à outils, plutôt qu'un MCP global partagé —
  c'est ce qui matérialise le découpage.
- **Le mode `fake` est la référence** : gratuite, déterministe, reproductible ; le cerveau LLM est un
  ajout, pas un prérequis pour comprendre l'architecture.

---

## 5. Stack technique

| Brique | Choix | Licence |
|---|---|---|
| Langage | Python ≥ 3.11 | PSF |
| Gestion d'env / dépendances | uv | Apache-2.0 / MIT |
| Serveurs & client MCP | FastMCP ≥ 2.0 | Apache-2.0 |
| Interface de suivi | Streamlit ≥ 1.36 | Apache-2.0 |
| Appels LLM (mode `ollama`) | httpx ≥ 0.27 vers Ollama (Gemma E4B) | BSD-3-Clause / MIT |
| Configuration | python-dotenv ≥ 1.0 | BSD-3-Clause |
| Lint / tests | Ruff, pytest | MIT |

---

## 6. Décisions

**Décisions figées**

- **Client MCP en mémoire** plutôt que serveurs MCP en sous-processus, **parce que** l'exemple reste
  mono-processus et sans IPC à gérer. *Limite* : pas d'isolation processus entre agents.
- **Cerveau `fake` par défaut** plutôt que LLM, **parce que** c'est reproductible, gratuit et sert de
  référence de test. *Limite* : ne teste pas le raisonnement d'un vrai modèle.
- **Un MCP par agent** plutôt qu'un MCP global, **parce que** cela rend visible la boîte à outils de
  chaque agent. *Limite* : plus de fabriques à écrire.
- **Le déficit de pièces est calculé par l'Assembleur** (il a la recette ET le stock) plutôt que par
  le Chef, **parce que** l'information nécessaire y est locale. *Limite* : le Chef relaie sans recalculer.

**Pistes à trancher / approfondir**

- Ajouter un état `manque_pieces` (machine bloquée sur le stock) entre `en cours` et `fini`, reflété
  dans Streamlit — reco par défaut : oui, bon exercice « état partagé + UI ».
- Brancher `CerveauOllama` et comparer ses décisions à la référence `CerveauFake`.

---

## 7. Roadmap

Ordre de construction (reprend le modèle mental « moteur générique vs exemple métier ») :

0. Moteur générique : boucle ReAct ([`agent.py`](../usine/agent.py)) + trace ([`trace.py`](../usine/trace.py)).
1. État partagé minimal ([`etat.py`](../usine/etat.py)).
2. Un MCP par agent, outils déterministes ([`mcp_servers.py`](../usine/mcp_servers.py)).
3. Politique déterministe par agent (`CerveauFake` dans [`cerveau.py`](../usine/cerveau.py)).
4. Câblage de l'arbre d'agents ([`orchestration.py`](../usine/orchestration.py)).
5. Tests : une politique par agent + un bout-en-bout à graine fixe.
6. (Optionnel) Cerveau LLM `CerveauOllama`, en gardant `fake` comme filet de sécurité.

---

## 8. Stratégie de tests

Un fichier de test par module (voir [`tests/`](../tests)). Les tests figent le comportement et valent
comme **documentation exécutable** :
- une politique par agent (`test_cerveau_fake.py`) ;
- le cerveau Ollama sans serveur, appel réseau simulé (`test_cerveau_ollama.py`) ;
- l'analyse de commande et la configuration (`test_config.py`) ;
- l'état partagé et la trace (`test_etat.py`, `test_trace.py`) ;
- un scénario complet de bout en bout, reproductible via `SEED` (`test_orchestration.py`).

Commande : `uv run pytest` (voir le [README](../README.md) pour la note sur les montages réseau Windows).

---

## 9. Références

- [`architecture.md`](architecture.md) — la spécification complète (agents, MCP, outils, flux, règles).
- [`adapter-a-votre-projet.md`](adapter-a-votre-projet.md) — réutiliser ce squelette sur un autre sujet.
- FastMCP (protocole Model Context Protocol) ; Ollama + modèle Gemma E4B pour le mode LLM.
