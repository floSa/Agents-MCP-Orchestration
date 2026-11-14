# MCP-Orchestration — Usine d'agents

Tutoriel d'orchestration multi-agents + MCP sur un fil rouge concret : une usine qui fabrique
des machines a la commande. On y voit, sur un seul exemple, les cas de figure de l'orchestration :
orchestrateur, sous-agents, boucles, reutilisation d'agents, profondeur (un agent qui appelle un
agent), etat partage, et outils exposes via MCP (FastMCP).

A lire d'abord : [`docs/architecture.md`](docs/architecture.md) (avec le schema). C'est la
specification complete.

---

## Ce que ca fait

On passe une commande (ex. `2 motos + 2 voitures`). Le Chef d'usine (orchestrateur) :

1. demande a l'Assembleur d'assembler chaque machine ;
2. si des pieces manquent, demande au Fabricant de les produire ;
3. le Fabricant commande au Fournisseur (qui livre 1 a 5 pieces au hasard), et recommande
   jusqu'a obtenir la quantite voulue, puis met le stock a jour ;
4. le Chef relance l'Assembleur, qui assemble et livre.

Chaque action (quel agent, quel outil, quels arguments, quel resultat, a quelle profondeur) est
journalisee et affichee dans une interface Streamlit pour se balader dans l'arbre d'agents.

---

## Arborescence

```
MCP-Orchestration/
├── README.md
├── docs/
│   ├── architecture.md        <- LA spec (agents, MCP, outils, flux, regles)
│   └── schema_architecture.svg
├── usine/                     <- le package Python
│   ├── config.py              <- recettes + configuration LLM
│   ├── etat.py                <- etat partage : stock + suivi_commande
│   ├── trace.py               <- journal d'evenements (pour Streamlit)
│   ├── cerveau.py             <- le "cerveau" : mode fake (deterministe) ou llm (service LLM central)
│   ├── agent.py               <- classe Agent + boucle ReAct generique
│   ├── mcp_servers.py         <- les MCP (FastMCP) : atelier, fabrication, fournisseur
│   ├── orchestration.py       <- assemble les agents et lance une commande
│   ├── main.py                <- lancement en ligne de commande
│   └── streamlit_app.py       <- interface de suivi
├── pyproject.toml             <- dependances (uv)
├── Dockerfile
├── docker-compose.yml         <- l'app Streamlit (branchee sur le service LLM central)
└── .env.example               <- variables de configuration
```

---

## Lancer en local (sans Docker)

Prerequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # cree l'env et installe les dependances

# 1) Demo en ligne de commande, SANS LLM (cerveau deterministe) :
uv run python -m usine.main "2 motos + 2 voitures"

# 2) Interface de suivi :
uv run streamlit run usine/streamlit_app.py
```

Par defaut, `LLM_PROVIDER=fake` : tout tourne sans modele, de facon deterministe — pratique pour
explorer l'architecture. Pour brancher le cerveau sur le service LLM central
(repo `LLM-Service`, API compatible OpenAI, modele `chat`) :

```bash
cp .env.example .env     # puis LLM_PROVIDER=llm
# Cle propre de l'application (jamais la cle maitresse de LLM-Service), ecrite dans le .env :
~/mes_projets/Projet-IA/LLM-Service/scripts/cle.sh creer agents-mcp-orchestration \
  --dans "$PWD/.env" --noms LLM_BASE_URL,LLM_API_KEY --hote
uv run python -m usine.main "2 motos + 2 voitures"
```

`LLM_PROVIDER` doit valoir `llm` pour appeler le vrai modele (avec `fake`, la cle n'est pas
utilisee). `--hote` ecrit l'adresse `http://127.0.0.1:8080/v1` ; en conteneur, le compose force
`http://llm-central:8080/v1`. Procedure complete : `LLM-Service/docs/brancher-une-application.md`.
Revocation : `scripts/cle.sh revoquer agents-mcp-orchestration` ; consommation :
`scripts/cle.sh consommation` (depuis le depot LLM-Service).

Essai reel du 14/11/2026, cle propre `agents-mcp-orchestration`, `LLM_PROVIDER=llm` :
`uv run python -m usine.main "2 motos + 2 voitures"` -> statut `commande_livrée`, 4 machines
livrees ; 119 requetes et 81 663 jetons comptes sur la cle.

Adresse depuis l'hote : `http://127.0.0.1:8080/v1` (`LLM_BASE_URL`). Le service doit etre demarre
(`curl -H "Authorization: Bearer <cle>" http://127.0.0.1:8080/v1/models` doit lister `chat`).
La cle reste dans le `.env` local, jamais dans git. La reflexion du modele est coupee par requete
(`LLM_THINKING=1` pour l'activer). Contexte : 16 384 jetons par requete.

---

## Lancer avec Docker

```bash
docker compose up --build
```

- `app` : l'interface Streamlit, exposee sur http://localhost:8501. Elle rejoint le reseau externe
  `llm-net` (cree par LLM-Service) et joint le service central sur `http://llm-central:8080/v1`.
- Prerequis : LLM-Service demarre ; `LLM_API_KEY` renseignee dans le `.env`. Rien a telecharger.
- L'ancien service `ollama` embarque a ete retire du compose (reste dans l'historique git).

---

## Modes du "cerveau"

| `LLM_PROVIDER` | Effet |
|---|---|
| `fake` (defaut) | Cerveau deterministe qui applique les regles. Aucune dependance, reproductible — pratique pour comprendre et tester l'arbre d'agents. |
| `llm` | Les agents decident via le modele `chat` du service LLM central (`ollama` accepte comme ancien alias). |

Les outils sont des stubs (ils renvoient un jeton), sauf `fournir_pieces` qui tire un nombre
aleatoire entre 1 et 5 — c'est ce qui cree la boucle du Fabricant.
