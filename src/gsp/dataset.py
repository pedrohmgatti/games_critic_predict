"""Monta o dataset de notas: um jogo do IGDB por linha, com o target e as features.

Target (pós-lançamento; NÃO usar como feature):
- `igdb_critic_score`: média de críticos do IGDB (0–100), e `igdb_critic_n`, o nº de
  críticos. Com 1 crítico a nota é ruidosa (correlação 0,57 com o OpenCritic); com 3 ou
  mais passa de 0,86. O corte mínimo fica para a modelagem.

Validação do target (também pós-lançamento): `oc_top_avg` (OpenCritic Top Critic Average)
e `mc_score` (Metascore da plataforma com mais críticas), ambos do Wikidata. Servem para
medir a qualidade do target, não para treinar.

Ligação Wikidata -> IGDB (por ID, sem fuzzy): slug do IGDB no Wikidata (P5794) e, se não
houver, app id da Steam (P1733) contra os `external_games` do IGDB.
"""

from __future__ import annotations

import logging

import pandas as pd

from gsp import config

log = logging.getLogger(__name__)

# Tipos do IGDB que recebem nota como jogo próprio. Ficam de fora DLC, bundle, episódio,
# temporada, mod, update, pack e fork. Port também, porque herda a nota do original.
GAME_TYPES = {"Main Game", "Remake", "Remaster", "Expanded Game", "Standalone Expansion"}
OPENCRITIC = "Q21039459"
METACRITIC = "Q150248"


def _explode_ids(s: pd.Series) -> pd.Series:
    return s.dropna().astype(str).str.split("|").explode()


def link_wikidata_igdb(wd: pd.DataFrame, ig: pd.DataFrame, ig_steam: pd.DataFrame) -> pd.DataFrame:
    """Pares (wd_qid, igdb_id) um para um. Slug ganha da Steam; em empate, o menor id."""
    slug_to_id = ig.set_index("slug")["igdb_id"]
    by_slug = (_explode_ids(wd.set_index("wd_qid")["igdb_slug"]).rename("slug").reset_index()
               .merge(slug_to_id.reset_index(), on="slug")[["wd_qid", "igdb_id"]]
               .assign(link_method="slug", _p=0))
    steam = (_explode_ids(wd.set_index("wd_qid")["steam_appid"]).rename("steam_appid").reset_index())
    steam["steam_appid"] = pd.to_numeric(steam["steam_appid"], errors="coerce")
    by_steam = (steam.dropna().astype({"steam_appid": "int64"})
                .merge(ig_steam, on="steam_appid")[["wd_qid", "igdb_id"]]
                .assign(link_method="steam", _p=1))
    pairs = (pd.concat([by_slug, by_steam]).drop_duplicates(["wd_qid", "igdb_id"])
             .sort_values(["_p", "igdb_id", "wd_qid"]))
    pairs = pairs.drop_duplicates("wd_qid").drop_duplicates("igdb_id")
    return pairs.drop(columns="_p").reset_index(drop=True)


def wikidata_validation(scores: pd.DataFrame) -> pd.DataFrame:
    """Notas OpenCritic e Metacritic por item Wikidata, para validar o target."""
    s = scores.dropna(subset=["score_100"]).sort_values("date", na_position="first")
    oc = s[s["reviewer_qid"] == OPENCRITIC]
    # Sem método declarado, a escala diz qual é: /100 = média (% = recomendação, que fica de fora)
    avg = oc[oc["method"].str.contains("Average", na=False) | (oc["method"].isna() & (oc["scale"] == "/100"))]
    avg = avg.drop_duplicates("wd_qid", keep="last").set_index("wd_qid")  # a mais recente

    # Metacritic: só o Metascore (/100); /10 é a nota dos usuários.
    mc = s[(s["reviewer_qid"] == METACRITIC) & (s["scale"] == "/100")]
    mc = (mc.sort_values(["n_reviews", "date"], na_position="first")
          .drop_duplicates("wd_qid", keep="last").set_index("wd_qid"))

    out = pd.DataFrame({
        "oc_top_avg": avg["score_100"], "oc_n": avg["n_reviews"],
        "mc_score": mc["score_100"], "mc_n": mc["n_reviews"], "mc_platform": mc["platforms"],
    })
    return out.rename_axis("wd_qid").reset_index()


def select_games(ig: pd.DataFrame, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """Jogos com target, mais os ainda não lançados com hype (alvos de previsão)."""
    today = today or pd.Timestamp.today().normalize()
    g = ig[ig["game_type"].isin(GAME_TYPES)].copy()
    g["is_upcoming"] = (g["first_release_date"].isna() | (g["first_release_date"] > today)) & (
        g["game_status"].fillna("") != "Cancelled")
    keep = g["critic_score"].notna() | (g["is_upcoming"] & (g["hypes"].fillna(0) > 0))
    return g[keep]


def build() -> pd.DataFrame:
    ig = pd.read_parquet(config.IGDB_GAMES)
    wd = pd.read_parquet(config.WIKIDATA_GAMES)
    links = link_wikidata_igdb(wd, ig, pd.read_parquet(config.IGDB_STEAM))
    val = wikidata_validation(pd.read_parquet(config.WIKIDATA_SCORES))
    games = select_games(ig)

    wd_cols = wd[["wd_qid", "series", "esrb", "pegi", "country"]].add_prefix("wd_").rename(
        columns={"wd_wd_qid": "wd_qid"})
    df = (games.drop(columns=["user_score", "user_n"])
          .rename(columns={"critic_score": "igdb_critic_score", "critic_n": "igdb_critic_n"})
          .merge(links, on="igdb_id", how="left")
          .merge(wd_cols, on="wd_qid", how="left")
          .merge(val, on="wd_qid", how="left"))
    df["release_year"] = df["first_release_date"].dt.year.astype("Int64")
    df = df[_column_order(df)].sort_values("first_release_date").reset_index(drop=True)

    df.to_parquet(config.DATASET, index=False)
    df.to_csv(config.DATASET.with_suffix(".csv"), index=False)
    log.info("dataset: %d jogos -> %s", len(df), config.DATASET)
    (config.REPORTS / "data_coverage.md").write_text(coverage_report(df), encoding="utf-8")
    return df


def _column_order(df: pd.DataFrame) -> list[str]:
    first = [
        "igdb_id", "wd_qid", "name", "slug", "first_release_date", "release_year",
        "is_upcoming", "game_type", "game_status",
        "igdb_critic_score", "igdb_critic_n",          # target
        "oc_top_avg", "oc_n", "mc_score", "mc_n", "mc_platform",  # validação do target
    ]
    return first + [c for c in df.columns if c not in first]


def coverage_report(df: pd.DataFrame) -> str:
    released = df[~df["is_upcoming"]]
    y = released["igdb_critic_score"]
    lines = ["# Cobertura do dataset de notas", "",
             f"- Jogos no dataset: **{len(df):,}** ({len(released):,} lançados com target, "
             f"{df['is_upcoming'].sum():,} por lançar com hype)",
             f"- Ligados ao Wikidata: {df['wd_qid'].notna().sum():,} "
             f"(slug {(df['link_method'] == 'slug').sum():,}, Steam {(df['link_method'] == 'steam').sum():,})",
             "", "## Target: `igdb_critic_score`", "",
             f"Mediana {y.median():.1f} · P10 {y.quantile(.1):.1f} · P90 {y.quantile(.9):.1f} · "
             f"desvio padrão {y.std():.1f}", "",
             "## Qualidade do target por nº de críticos", "",
             "Comparação com o OpenCritic Top Critic Average nos jogos que têm as duas notas.", "",
             "| Críticos (`igdb_critic_n`) | Jogos | Com OpenCritic | Correlação | Erro absoluto mediano | Desvio padrão do target |",
             "|---|---:|---:|---:|---:|---:|"]
    bins = pd.cut(released["igdb_critic_n"], [-1, 1, 2, 4, 9, 10**6], labels=["1", "2", "3–4", "5–9", "10+"])
    for b, g in released.groupby(bins, observed=True):
        p = g[["igdb_critic_score", "oc_top_avg"]].dropna()
        lines.append(f"| {b} | {len(g):,} | {len(p):,} | {p.iloc[:, 0].corr(p.iloc[:, 1]):.2f} | "
                     f"{(p.iloc[:, 0] - p.iloc[:, 1]).abs().median():.1f} | {g['igdb_critic_score'].std():.1f} |")

    p = released[["oc_top_avg", "mc_score"]].dropna()
    lines += ["", f"OpenCritic × Metacritic: {len(p):,} jogos, correlação {p.iloc[:, 0].corr(p.iloc[:, 1]):.2f}.", ""]

    by_year = released.groupby("release_year").agg(
        jogos=("igdb_id", "size"), n3=("igdb_critic_n", lambda s: (s >= 3).sum()),
        oc=("oc_top_avg", "count"))
    lines += ["## Por ano de lançamento", "",
              "| Ano | Jogos com target | Com ≥ 3 críticos | Com OpenCritic |", "|---|---:|---:|---:|"]
    for yr, r in by_year[by_year.index >= 1995].iterrows():
        lines.append(f"| {yr} | {r.jogos:,} | {r.n3:,} | {r.oc:,} |")
    return "\n".join(lines) + "\n"
