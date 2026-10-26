# games_critic_predict

Previsão da **nota da crítica de um jogo antes do lançamento**, com foco no **GTA VI**,
para conteúdo no YouTube.

A extração dos dados e o dataset com o target estão prontos. A modelagem vai ser estudada em
notebooks, em `notebooks/`. Escopo, riscos e plano de etapas estão em
[.claude/documenta_o_do_projeto.md](.claude/documenta_o_do_projeto.md).

## Pipeline

```
IGDB API (chaves Twitch) ──► catálogo + metadados + hypes + nota da crítica (target) ──┐
Wikidata SPARQL (sem chave) ──► metadados + IDs + notas OpenCritic/Metacritic (P444) ──┴─► build ──► data/processed/games_scores.parquet
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  # pipeline, testes e notebooks
cp .env.example .env     # preencha TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET (https://api-docs.igdb.com)

.venv/bin/gsp igdb       # ~20 min: 383 mil jogos + 179 mil app ids Steam
.venv/bin/gsp wikidata   # ~10 min na 1ª vez (depois vem do cache)
.venv/bin/gsp build      # dataset + reports/data_coverage.md
.venv/bin/pytest

.venv/bin/jupyter lab notebooks/
```

`data/` e `logs/` não vão para o git: os dados se regeneram com os comandos acima.
As respostas do Wikidata ficam em cache em `data/raw/http_cache/`. Interromper e rodar de
novo continua de onde parou.

## Target

**`igdb_critic_score`**: média dos críticos que o IGDB agrega (0–100). `igdb_critic_n` é o
número de críticos por trás da nota e mede a confiabilidade:

| Críticos | Jogos | Correlação com o OpenCritic |
|---|---:|---:|
| 1 | 6.403 | 0,57 |
| 2 | 2.865 | 0,79 |
| 3–4 | 2.710 | 0,86 |
| 5+ | 2.756 | 0,93–0,95 |

O dataset guarda todos os jogos com nota. O corte mínimo de críticos é decisão da modelagem.

**Validação do target**: `oc_top_avg` (OpenCritic Top Critic Average) e `mc_score`
(Metascore da plataforma com mais críticas), ambos do Wikidata. Servem só para medir a
qualidade do target, nunca como feature.

## Fontes e o que cada uma dá

| Fonte | Features (pré-lançamento) | Pós-lançamento |
|---|---|---|
| IGDB | gêneros, temas, modos, perspectiva, franquia, coleção, engine, dev/publisher, plataformas, tipo, `hypes` | **target** |
| Wikidata | série, ESRB, PEGI, país | validação (OpenCritic, Metacritic) |

## Estrutura

| Diretório | Conteúdo |
|---|---|
| `src/gsp/` | pacote Python: CLI (`cli.py`), caminhos e parâmetros (`config.py`), sessão HTTP com cache e retry (`http.py`), montagem do dataset (`dataset.py`) |
| `src/gsp/enrich/` | extração de cada fonte: `igdb.py`, `wikidata.py` |
| `tests/` | testes do parse de notas, achatamento do IGDB, ligação entre fontes e seleção de jogos |
| `data/raw/` | dados brutos das fontes e `http_cache/` do Wikidata |
| `data/processed/` | dataset final |
| `reports/` | relatório de cobertura |
| `notebooks/` | estudo dos modelos, um notebook numerado por etapa (`01_eda_target.ipynb`, ...), lendo de `data/processed/` |
| `logs/` | logs das extrações |

## Saídas

| Arquivo | Conteúdo |
|---|---|
| `data/raw/igdb_games.parquet` | um jogo do IGDB por linha (todos os tipos) |
| `data/raw/igdb_steam_ids.parquet` | `igdb_id, steam_appid`, ponte alternativa com o Wikidata |
| `data/raw/wikidata_games.parquet` | ~181 mil itens: metadados e IDs externos |
| `data/raw/wikidata_review_scores.parquet` | uma declaração de nota (P444) por linha: veículo, método, plataforma, nº de críticas, data, nota em 0–100 |
| `data/processed/games_scores.parquet` (+ `.csv`) | **dataset**: um jogo por linha, target + validação + features |
| `data/processed/features.parquet` | matriz de features da base da modelagem e dos jogos por lançar, gerada por `notebooks/02_features.ipynb` |
| `reports/data_coverage.md` | distribuição do target, qualidade por nº de críticos, cobertura por ano |

### Quem entra no dataset

Jogos do IGDB dos tipos Main Game, Remake, Remaster, Expanded Game e Standalone Expansion
**com target**, mais os **ainda não lançados com hype** (`is_upcoming`), que são os alvos de
previsão, como o GTA VI. DLCs, ports, bundles e mods ficam de fora.

### Ligação entre fontes

Toda por ID, sem fuzzy: Wikidata → IGDB pelo slug do IGDB no Wikidata (P5794) e, se não
houver, pelo app id da Steam. A ligação é um para um (`link_method` diz qual foi usada). O
slug sozinho liga 98% dos jogos com nota no Wikidata.

## Decisões e ressalvas

- **O IGDB não é o Metacritic.** O GTA V tem 88 no IGDB, 92 no OpenCritic e 97 no
  Metacritic: o IGDB mistura versões e veículos. Na escala da audiência, o número mais
  conhecido é o Metacritic.
- **Cobertura por época.** Até ~2003 há poucos jogos com 3 ou mais críticos; o grosso está
  em 2004–2021. O OpenCritic, usado na validação, nasceu em 2015 e cobre pouco antes de 2013.
- **Vazamento.** O target e as notas de validação nunca viram feature. `hypes` é contado
  antes do lançamento; o resto dos metadados do IGDB é o estado atual (ex.: franquia), o que
  é seguro para atributos estáveis.
- **YouTube fica de fora**: a API devolve as views *atuais*, o que vaza o resultado.
- **Metacritic direto** não é raspado: os termos de uso proíbem.
