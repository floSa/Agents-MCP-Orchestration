# Adapter ce squelette à VOTRE projet

Ce dépôt est volontairement un **exemple** (une usine qui fabrique des machines), mais il est
conçu pour servir de **base réutilisable**. Ce guide explique ce qu'on garde tel quel, ce qu'on
réécrit, et dans quel ordre s'y prendre.

À lire avant : [`architecture.md`](architecture.md) (la spec) et le code de [`usine/`](../usine).

---

## 1. Le modèle mental : moteur générique vs exemple métier

La clé du dépôt tient en une phrase :

> **Le moteur fait boucler des agents ; le « cerveau » décide ; les outils (MCP) agissent.**
> Le moteur est générique ; le cerveau et les outils sont VOTRE métier.

Chaque fichier porte un repère en tête de son docstring (`MOTEUR GÉNÉRIQUE`, `EXEMPLE MÉTIER`,
`MIXTE`, `CÂBLAGE`). Récapitulatif :

| Fichier | Catégorie | À faire pour votre projet |
|---|---|---|
| [`usine/agent.py`](../usine/agent.py) | MOTEUR GÉNÉRIQUE | Réutiliser tel quel (la boucle ReAct, les délégations, la trace). |
| [`usine/trace.py`](../usine/trace.py) | MOTEUR GÉNÉRIQUE | Réutiliser tel quel. |
| [`usine/cerveau.py`](../usine/cerveau.py) | MIXTE | Garder l'interface + `CerveauOllama` ; **réécrire `CerveauFake`** (votre politique). |
| [`usine/etat.py`](../usine/etat.py) | EXEMPLE MÉTIER | Remplacer par l'état partagé de votre domaine. |
| [`usine/config.py`](../usine/config.py) | EXEMPLE MÉTIER | Remplacer recettes + analyse de commande ; garder le patron `Config`. |
| [`usine/mcp_servers.py`](../usine/mcp_servers.py) | EXEMPLE MÉTIER | Remplacer les outils ; garder le patron « un MCP par agent ». |
| [`usine/orchestration.py`](../usine/orchestration.py) | CÂBLAGE | Recopier le patron, recâbler vos agents/délégations. |
| [`usine/main.py`](../usine/main.py), [`usine/streamlit_app.py`](../usine/streamlit_app.py) | EXEMPLE MÉTIER | Adapter l'affichage (souvent peu de changements). |

---

## 2. La règle d'or (à ne pas oublier)

> On ne met un **agent** (donc un LLM, donc du coût et de l'incertitude) **que là où il y a une
> vraie décision ou une itération**. Tout le reste reste du **code déterministe** : un outil MCP.

Concrètement, avant de créer un agent, demandez-vous : « est-ce qu'il y a un choix à faire, ou une
boucle dont je ne connais pas la longueur d'avance ? » Si non → c'est un simple outil.

Dans l'exemple : le Fabricant est un agent **parce qu'il boucle** (le Fournisseur renvoie 1 à 5
pièces au hasard, il faut recommander jusqu'à avoir assez). Si le Fournisseur livrait toujours la
quantité demandée, le Fabricant pourrait n'être qu'un outil.

---

## 3. La méthode, étape par étape

1. **Dessinez l'arbre d'agents.** Qui orchestre ? Quels sous-agents ? Où est la profondeur (un
   sous-agent qui en appelle un autre) ? Où sont les boucles ? Reprenez le schéma de
   [`architecture.md`](architecture.md) comme gabarit.

2. **Définissez l'état partagé** ([`etat.py`](../usine/etat.py)). La mémoire commune : que lisent
   et écrivent les agents ? (ici : `stock` + `suivi`.)

3. **Listez les outils, un MCP par agent** ([`mcp_servers.py`](../usine/mcp_servers.py)). Chaque
   outil est une fonction. Déterministe par défaut ; il n'a besoin d'un LLM que s'il prend une
   décision floue. Gardez la fabrique qui « capture » l'état.

4. **Écrivez la politique** ([`CerveauFake`](../usine/cerveau.py)). Pour chaque agent, une méthode
   qui, à partir de `(objectif, historique, etat)`, renvoie la prochaine `Action`
   (`outil` | `deleguer` | `terminer`). Commencez TOUJOURS par le mode déterministe : c'est votre
   référence, gratuite et reproductible.

5. **Câblez** ([`orchestration.py`](../usine/orchestration.py)). Créez les MCP, un client par
   serveur, les agents avec leurs outils et leurs délégations (`async (args, profondeur) -> ...`).

6. **Testez** (dossier [`tests/`](../tests)). Reprenez la structure : un test par politique
   d'agent + un test de bout en bout à graine fixe. Les tests figent le comportement et servent de
   doc exécutable.

7. **(Optionnel) Branchez un LLM.** `CerveauOllama` montre le patron : décrire les actions
   possibles (catalogue), imposer un JSON strict, extraire robustement, relancer si besoin. Gardez
   le mode `fake` comme filet de sécurité et référence de test.

---

## 4. Anatomie d'un agent (le contrat à respecter)

Un agent reçoit toujours les mêmes briques (voir [`Agent.__init__`](../usine/agent.py)) :

- `clients_par_outil` : `{nom_outil: client_MCP}` — sa boîte à outils ;
- `delegations` : `{nom: async (args, profondeur) -> résultat}` — ses sous-agents ;
- `cerveau`, `trace`, `etat` : partagés par tous les agents ;
- `catalogue` : descriptions d'outils (utile seulement au cerveau LLM).

La boucle (générique, dans `agent.py`) appelle `cerveau.decider(...)` puis exécute l'`Action`
renvoyée, jusqu'à `terminer`. **Vous n'avez pas à toucher cette boucle** : vous écrivez seulement
les outils (MCP) et la politique (cerveau).

---

## 5. Checklist de portage

- [ ] J'ai dessiné l'arbre d'agents (orchestrateur, sous-agents, profondeur, boucles).
- [ ] Chaque « agent » correspond à une vraie décision ou itération (sinon : un outil).
- [ ] L'état partagé est défini et minimal.
- [ ] Un MCP par agent, outils déterministes par défaut.
- [ ] `CerveauFake` réécrit : une politique déterministe par agent.
- [ ] Câblage à jour dans `orchestration.py`.
- [ ] Tests : une politique par agent + un e2e reproductible à graine fixe.
- [ ] `uv run pytest` est vert.

---

## 6. Pour aller plus loin (exercices)

- Enrichir `suivi_commande` avec un vrai cycle de vie
  (`a_faire → manque_pieces → reappro_ok → livrée`) et le refléter dans Streamlit.
- Ajouter un type de machine (ex. `vélo`) : une ligne dans `RECETTES`, un test, et c'est tout.
- Brancher `CerveauOllama` et comparer ses décisions à la référence `CerveauFake`.
- Ajouter un quatrième niveau de profondeur (un sous-sous-agent) pour voir l'arbre grandir.
