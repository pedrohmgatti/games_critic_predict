# Documentação de Projeto: Previsão da Nota da Crítica de Videogames

> Escopo redefinido em 25/10/2026. O escopo anterior (previsão de vendas do primeiro ano com
> VGChartz e YouTube) foi descartado. A análise de "flop" é um projeto futuro e separado.

## 1. Visão Geral do Projeto

O objetivo é construir um modelo de regressão que estime a **nota da crítica** de um jogo
($Y$) **antes do lançamento**, usando apenas **metadados e sinais de hype pré-lançamento** ($X$).

O caso principal é o **GTA VI** (lançamento previsto para 19/11/2026, PS5 e Xbox Series, segundo
o IGDB). O resultado vira um vídeo para o YouTube, contando o experimento com storytelling. A
previsão deve ser registrada publicamente **antes** do lançamento, para que a conferência com a
nota real tenha credibilidade.

---

## 2. Variável Alvo (Target)

$$\text{Target } (Y) = \texttt{igdb\_critic\_score} \in [0, 100]$$

É a média dos críticos que o IGDB agrega (`aggregated_rating`). A coluna `igdb_critic_n` traz
o número de críticos por trás de cada nota e mede a confiabilidade:

| Críticos (`igdb_critic_n`) | Jogos | Correlação com o OpenCritic | Erro absoluto mediano |
|---|---:|---:|---:|
| 1 | 6.403 | 0,57 | 7,0 |
| 2 | 2.865 | 0,79 | 4,5 |
| 3–4 | 2.710 | 0,86 | 3,7 |
| 5–9 | 1.927 | 0,93 | 2,7 |
| 10+ | 829 | 0,95 | 1,8 |

- **Distribuição:** mediana 72,1; P10 50,0; P90 86,0; desvio padrão 16,0.
- **Base da modelagem:** jogos com mais de 3 críticos (`igdb_critic_n >= 4`) lançados depois
  de 2009 (`release_year >= 2010`): 3.157 jogos, correlação de 0,93 com o OpenCritic. Com
  exatamente 3 críticos a correlação é 0,84; com 4, 0,89. O filtro fica no notebook; o
  dataset processado continua com todos os jogos com nota.
- **Escala:** o IGDB não é o Metacritic. O GTA V tem 88 no IGDB, 92 no OpenCritic e 97 no
  Metacritic, porque o IGDB mistura versões e veículos. A previsão do GTA VI sai na escala do
  IGDB, e o vídeo precisa explicar isso.

### Validação do target

Duas colunas do Wikidata servem **só para medir a qualidade do target**, nunca como feature:

- `oc_top_avg`: OpenCritic Top Critic Average (7.519 jogos);
- `mc_score`: Metascore da plataforma com mais críticas (463 jogos).

OpenCritic e Metacritic concordam bem entre si (correlação de 0,88 em 182 jogos).

---

## 3. Arquitetura do Pipeline de Dados

```
┌──────────────────────┐        ┌──────────────────────┐
│       IGDB API       │        │   Wikidata SPARQL    │
│  (chaves Twitch)     │        │     (sem chave)      │
│ catálogo, metadados, │        │ metadados, IDs,      │
│ hypes, TARGET,       │        │ notas OpenCritic e   │
│ app ids da Steam     │        │ Metacritic (P444)    │
└──────────┬───────────┘        └──────────┬───────────┘
           │                               │
           └───────────────┬───────────────┘
                           ▼
            [ Ligação por ID (sem fuzzy) ]
              slug do IGDB (P5794) → 98%
              app id da Steam → fallback
                           │
                           ▼
         [ data/processed/games_scores.parquet ]
                           │
                           ▼
            [ notebooks/: estudo dos modelos ]
```

### Comandos

```bash
.venv/bin/gsp igdb       # ~20 min: 383 mil jogos + 179 mil app ids Steam
.venv/bin/gsp wikidata   # ~10 min na 1ª vez (depois vem do cache)
.venv/bin/gsp build      # dataset + reports/data_coverage.md
```

### Fontes de dados

1. **IGDB API (espinha dorsal, features e target)**
   * Catálogo completo: 383.226 jogos.
   * Metadados: gêneros, temas, modos de jogo, perspectiva, franquia, coleção, engine,
     desenvolvedora, publisher, plataformas, tipo (Main Game, Remake...) e status.
   * `hypes`: número de follows **antes** do lançamento, o sinal de hype pré-lançamento.
   * Target: `aggregated_rating` e `aggregated_rating_count`.
   * 179.427 pares jogo–app id da Steam, usados só como ponte com o Wikidata.
2. **Wikidata SPARQL (metadados complementares e validação)**
   * 180.929 itens: série, ESRB, PEGI, país, IDs externos (IGDB, Steam, OpenCritic...).
   * 30.675 notas de agregadores (P444) em 15.038 jogos, com veículo, método, plataforma,
     número de críticas e data.

### Fontes descartadas

| Fonte | Motivo |
|---|---|
| VGChartz | dados de venda, fora do escopo; as estimativas param em 2018 |
| YouTube Data API | devolve as views *atuais*, não as de antes do lançamento: vazaria o resultado |
| Steam (reviews) | só dá nota de usuários, que não é o target e é pós-lançamento |
| Metacritic (raspagem direta) | os termos de uso proíbem |

---

## 4. O Dataset

`data/processed/games_scores.parquet` (+ `.csv`): **21.936 jogos × 35 colunas**, um jogo por linha.

- **14.734 jogos lançados com target**: a base de treino e validação.
- **7.202 jogos por lançar com hype** (`is_upcoming = True`): os alvos de previsão, como o GTA VI
  (`hypes` = 1.111, o maior do dataset).
- **Tipos incluídos:** Main Game, Remake, Remaster, Expanded Game e Standalone Expansion. DLCs,
  ports, bundles, mods e jogos cancelados ficam de fora.

| Grupo | Colunas |
|---|---|
| Identificação | `igdb_id`, `wd_qid`, `name`, `slug`, `link_method` |
| Tempo e tipo | `first_release_date`, `release_year`, `is_upcoming`, `game_type`, `game_status` |
| **Target** | `igdb_critic_score`, `igdb_critic_n` |
| Validação (não é feature) | `oc_top_avg`, `oc_n`, `mc_score`, `mc_n`, `mc_platform` |
| Features (IGDB) | `hypes`, `platforms`, `genres`, `themes`, `game_modes`, `perspectives`, `franchises`, `collections`, `engines`, `developers`, `publishers`, `parent_game`, `version_parent`, `alt_names` |
| Features (Wikidata) | `wd_series`, `wd_esrb`, `wd_pegi`, `wd_country` |

Listas com vários valores vêm separadas por `|`.

---

## 5. Riscos e Cuidados

1. **Vazamento temporal.** Nenhuma coluna pós-lançamento vira feature. Features derivadas do
   histórico (ex.: nota média da desenvolvedora ou da franquia) devem usar **apenas jogos
   lançados antes** do jogo em questão.
2. **Metadados atuais.** Os metadados do IGDB refletem o estado de hoje. Isso é seguro para
   atributos estáveis (gênero, franquia), mas não para os que mudam depois do lançamento.
3. **Cobertura desigual no tempo.** Até ~2003 há poucos jogos com 3 ou mais críticos; o grosso
   está em 2004–2021.
4. **GTA VI fora da distribuição.** Nenhum jogo do treino tem hype ou orçamento comparáveis.
   O intervalo de incerteza da previsão é parte central da narrativa.
5. **Validação temporal, não aleatória.** Um split aleatório (K-Fold) mistura passado e futuro
   e infla o resultado. O teste deve ser feito em jogos lançados depois do período de treino.

---

## 6. Plano de Implementação

### Etapa 1: Extração e integração de dados ✅
* Dump do IGDB, Wikidata com notas de agregadores, ligação por ID e dataset final.
* Relatório de cobertura em `reports/data_coverage.md`.

### Etapa 2: Análise exploratória (notebook)
* Distribuição do target por ano, gênero, plataforma e número de críticos.
* Escolha do corte mínimo de `igdb_critic_n`.
* Cobertura e cardinalidade das features candidatas.

### Etapa 3: Engenharia de features (notebook → `src/gsp/`)
* Codificação das listas (gêneros, temas, plataformas...).
* Redução de cardinalidade de desenvolvedoras e publishers.
* Histórico sem vazamento: nota média anterior da desenvolvedora, publisher e franquia.
* Tratamento de `hypes` (ausente ≠ zero; transformação log).

### Etapa 4: Modelagem e validação (notebook)
* Baselines: média global e média histórica da franquia ou desenvolvedora.
* Modelos: Ridge/Lasso, Random Forest e LightGBM.
* Validação temporal (ex.: treino até 2019, teste de 2020 em diante).
* Métricas: MAE, RMSE e cobertura dos intervalos de previsão.

### Etapa 5: Previsão do GTA VI e interpretação
* Previsão pontual e intervalo de incerteza.
* Importância das features (SHAP) para o roteiro do vídeo.
* Registro público da previsão antes de 19/11/2026.

---

## 7. Estrutura do Projeto

| Diretório | Conteúdo |
|---|---|
| `src/gsp/` | pacote Python: CLI, configuração, sessão HTTP com cache, montagem do dataset |
| `src/gsp/enrich/` | extração de cada fonte (`igdb.py`, `wikidata.py`) |
| `tests/` | testes do parse de notas, achatamento do IGDB, ligação e seleção de jogos |
| `data/raw/` | dados brutos das fontes e cache HTTP do Wikidata |
| `data/processed/` | dataset final |
| `reports/` | relatório de cobertura |
| `notebooks/` | estudo dos modelos (um notebook por etapa: `01_eda_target.ipynb`, `02_...`) |
| `logs/` | logs das extrações |

---

## 8. Próximos Passos

- [x] Extrair IGDB e Wikidata e montar o dataset com o target.
- [x] Instalar as dependências dos notebooks (`pip install -e ".[notebooks]"`).
- [x] Visualização inicial dos dados (`notebooks/01_eda_target.ipynb`).
- [x] Definição do corte mínimo de críticos (4+) e do recorte temporal (2010+).
- [x] Engenharia de features sem vazamento, primeira versão (`notebooks/02_features.ipynb` →
  `data/processed/features.parquet`).
- [ ] Baselines, modelos e validação temporal.
- [ ] Previsão do GTA VI e registro público antes do lançamento.
