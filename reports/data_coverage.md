# Cobertura do dataset de notas

- Jogos no dataset: **21,936** (14,734 lançados com target, 7,202 por lançar com hype)
- Ligados ao Wikidata: 16,814 (slug 16,420, Steam 394)

## Target: `igdb_critic_score`

Mediana 72.1 · P10 50.0 · P90 86.0 · desvio padrão 16.0

## Qualidade do target por nº de críticos

Comparação com o OpenCritic Top Critic Average nos jogos que têm as duas notas.

| Críticos (`igdb_critic_n`) | Jogos | Com OpenCritic | Correlação | Erro absoluto mediano | Desvio padrão do target |
|---|---:|---:|---:|---:|---:|
| 1 | 6,403 | 1,615 | 0.57 | 7.0 | 19.0 |
| 2 | 2,865 | 1,007 | 0.79 | 4.5 | 14.0 |
| 3–4 | 2,710 | 1,254 | 0.86 | 3.7 | 12.7 |
| 5–9 | 1,927 | 1,187 | 0.93 | 2.7 | 11.4 |
| 10+ | 829 | 687 | 0.95 | 1.8 | 9.4 |

OpenCritic × Metacritic: 182 jogos, correlação 0.88.

## Por ano de lançamento

| Ano | Jogos com target | Com ≥ 3 críticos | Com OpenCritic |
|---|---:|---:|---:|
| 1995 | 132 | 3 | 0 |
| 1996 | 109 | 4 | 1 |
| 1997 | 71 | 4 | 4 |
| 1998 | 59 | 0 | 2 |
| 1999 | 123 | 4 | 2 |
| 2000 | 130 | 7 | 2 |
| 2001 | 189 | 17 | 7 |
| 2002 | 282 | 31 | 3 |
| 2003 | 360 | 68 | 6 |
| 2004 | 346 | 106 | 7 |
| 2005 | 448 | 146 | 10 |
| 2006 | 534 | 203 | 5 |
| 2007 | 571 | 209 | 6 |
| 2008 | 600 | 227 | 9 |
| 2009 | 569 | 219 | 8 |
| 2010 | 417 | 188 | 19 |
| 2011 | 474 | 216 | 20 |
| 2012 | 505 | 262 | 48 |
| 2013 | 548 | 290 | 143 |
| 2014 | 615 | 298 | 322 |
| 2015 | 750 | 376 | 461 |
| 2016 | 921 | 444 | 570 |
| 2017 | 817 | 377 | 550 |
| 2018 | 709 | 296 | 509 |
| 2019 | 615 | 281 | 448 |
| 2020 | 567 | 255 | 439 |
| 2021 | 569 | 224 | 388 |
| 2022 | 488 | 158 | 386 |
| 2023 | 534 | 176 | 439 |
| 2024 | 521 | 170 | 408 |
| 2025 | 459 | 117 | 339 |
| 2026 | 322 | 70 | 183 |
