"""Metadados e notas de jogos via SPARQL do Wikidata (público, sem chave de API).

Além de gênero/plataforma/empresas/série/modo de jogo/classificação etária, o Wikidata
traz IDs externos (IGDB, Steam, GOG, Metacritic, OpenCritic), que servem de ponte exata
com o IGDB e a Steam, e as notas de agregadores (P444, "review score"). Cada declaração
de nota tem qualificadores: quem deu (P447), método (P459, ex.: "OpenCritic Top Critic
Average"), plataforma (P400), nº de críticas (P7887) e data (P585). Elas vão para uma
tabela longa à parte, uma linha por declaração.

Robustez:
- cada propriedade é uma consulta simples (jogo, valor); os labels dos valores vêm
  depois, em lotes com VALUES. Consultas com OPTIONAL+label sobre 170k itens estouram
  o timeout de 60 s e o endpoint devolve CSV *truncado com status 200*;
- respostas que terminam com exceção do servidor não são cacheadas e são refeitas;
- desde 2024 muitos itens só têm label no código genérico "mul": buscamos "en" e "mul"
  em consultas separadas e preferimos "en".
"""

from __future__ import annotations

import io
import logging
import re

import pandas as pd

from gsp.config import BOT_UA, WIKIDATA_GAMES, WIKIDATA_MIN_INTERVAL, WIKIDATA_SCORES
from gsp.http import PoliteSession

log = logging.getLogger(__name__)

ENDPOINT = "https://query.wikidata.org/sparql"
ENTITY = "http://www.wikidata.org/entity/"
# Além de "video game", inclui subclasses que costumam receber nota própria
# (compilações, expansões, edições). Projetos e jogos cancelados ficam de fora.
GAME_CLASSES = {
    "Q7889": "video game",
    "Q16070115": "compilation",
    "Q209163": "expansion",
    "Q60997816": "edition",
}
GAME = f"VALUES ?cls {{ {' '.join('wd:' + q for q in GAME_CLASSES)} }} ?g wdt:P31 ?cls ."
LABEL_BATCH = 2000  # QIDs por consulta VALUES (POST)

# coluna -> propriedade cujo valor é uma entidade (guardamos o label)
ENTITY_PROPS = {
    "genres": "P136",
    "platforms": "P400",
    "developers": "P178",
    "publishers": "P123",
    "series": "P179",
    "game_modes": "P404",
    "esrb": "P852",
    "pegi": "P908",
    "country": "P495",
    "engine": "P408",
}
# coluna -> propriedade cujo valor é um identificador literal
ID_PROPS = {
    "igdb_slug": "P5794",
    "steam_appid": "P1733",
    "gog_id": "P2725",
    "metacritic_id": "P1712",
    "opencritic_id": "P2864",
}

# Uma linha por (declaração, plataforma, ...); o agrupamento por ?st vem depois.
REVIEW_QUERY = (
    f"SELECT ?g ?st ?score ?by ?method ?plat ?n ?date WHERE {{ {GAME} "
    "?g p:P444 ?st . ?st ps:P444 ?score ; pq:P447 ?by . "
    "OPTIONAL { ?st pq:P459 ?method } OPTIONAL { ?st pq:P400 ?plat } "
    "OPTIONAL { ?st pq:P7887 ?n } OPTIONAL { ?st pq:P585 ?date } }"
)
_SCORE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:/\s*(\d+(?:[.,]\d+)?)|(%))?\s*$")


def _complete(text: str) -> bool:
    """Timeout no meio do streaming = CSV + stack trace Java, ainda com status 200.

    As linhas do CSV do endpoint terminam em CRLF; o stack trace, em LF.
    """
    return text.endswith("\r\n") and "\tat java." not in text[-20000:]


def _query(sess: PoliteSession, sparql: str) -> pd.DataFrame:
    text = sess.get_text(ENDPOINT, headers={"Accept": "text/csv"}, data={"query": sparql},
                         validate=_complete)
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    for c in df.columns:
        df[c] = df[c].str.removeprefix(ENTITY)
    return df


def _names_for(sess: PoliteSession, qids: list[str], pred: str = "rdfs:label") -> pd.DataFrame:
    """Labels/aliases en+mul de uma lista de QIDs, em lotes (VALUES via POST).

    Consultas pequenas por lote em vez de uma consulta global: a versão global
    (170k jogos x labels) estoura o timeout quando o endpoint está carregado.
    """
    parts = []
    for i in range(0, len(qids), LABEL_BATCH):
        batch = " ".join(f"wd:{q}" for q in qids[i : i + LABEL_BATCH])
        parts.append(_query(sess, f'SELECT ?v ?name (LANG(?name) AS ?lang) WHERE {{ '
                                  f'VALUES ?v {{ {batch} }} ?v {pred} ?name . '
                                  f'FILTER(LANG(?name) IN ("en", "mul")) }}'))
    return pd.concat(parts, ignore_index=True)


def _prefer_en(df: pd.DataFrame) -> pd.Series:
    df = df.assign(_o=(df["lang"] != "en").astype(int)).sort_values("_o").drop_duplicates("v")
    return df.set_index("v")["name"]


def _joined(df: pd.DataFrame, col: str) -> pd.Series:
    return (df[df[col] != ""].drop_duplicates()
            .groupby("g")[col].agg(lambda s: "|".join(sorted(set(s)))))


def parse_score(raw: str) -> tuple[float | None, str | None]:
    """"64/100" -> (64, "/100"); "22%" -> (22, "%"); "7.3/10" -> (73, "/10").

    Formatos sem escala ("97") ou com letras ("A-") ficam sem valor.
    """
    m = _SCORE_RE.match(str(raw))
    if not m:
        return None, None
    value = float(m[1].replace(",", "."))
    if m[3]:
        return value, "%"
    if not m[2]:
        return None, None
    den = float(m[2].replace(",", "."))
    if den <= 0 or value > den:
        return None, None
    return round(100 * value / den, 2), f"/{m[2]}"


def _first(s: pd.Series):
    s = s[s != ""]
    return s.iloc[0] if len(s) else None


def fetch_review_scores(sess: PoliteSession) -> pd.DataFrame:
    raw = _query(sess, REVIEW_QUERY)
    qids = sorted({v for c in ("by", "method", "plat") for v in raw[c] if v.startswith("Q")})
    names = _prefer_en(_names_for(sess, qids)).to_dict()
    for c in ("by", "method", "plat"):
        raw[c + "_label"] = raw[c].map(names).fillna(raw[c])

    out = raw.groupby("st").agg(
        wd_qid=("g", "first"), score_raw=("score", "first"),
        reviewer=("by_label", "first"), reviewer_qid=("by", "first"),
        method=("method_label", _first), n_reviews=("n", _first), date=("date", _first),
        platforms=("plat_label", lambda s: "|".join(sorted(set(s[s != ""]))) or None),
    ).reset_index().rename(columns={"st": "statement"})
    parsed = out["score_raw"].map(parse_score)
    out["score_100"] = parsed.str[0]
    out["scale"] = parsed.str[1]
    out["n_reviews"] = pd.to_numeric(out["n_reviews"], errors="coerce")
    out["date"] = pd.to_datetime(out["date"].str[:10], errors="coerce", format="%Y-%m-%d")
    out.to_parquet(WIKIDATA_SCORES, index=False)
    log.info("wikidata: %d notas (P444) em %d jogos -> %s",
             len(out), out["wd_qid"].nunique(), WIKIDATA_SCORES)
    return out


def fetch_wikidata() -> pd.DataFrame:
    sess = PoliteSession(BOT_UA, WIKIDATA_MIN_INTERVAL, namespace="wikidata", timeout=90)

    classes = _query(sess, f"SELECT ?g ?cls WHERE {{ {GAME} }}")
    games = sorted(set(classes["g"]))
    labels = _prefer_en(_names_for(sess, games)).rename("label")
    aliases = _names_for(sess, games, "skos:altLabel").rename(columns={"v": "g", "name": "alias"})
    dates = _query(sess, f"SELECT ?g (MIN(?d) AS ?pub_date) WHERE {{ {GAME} ?g wdt:P577 ?d . }} "
                         f"GROUP BY ?g")
    log.info("wikidata: %d jogos, %d labels, %d aliases, %d datas",
             len(games), len(labels), len(aliases), len(dates))

    out = labels.rename_axis("g").to_frame()
    out["item_type"] = _joined(classes.assign(item_type=classes["cls"].map(GAME_CLASSES)), "item_type")
    out["aliases"] = _joined(aliases[["g", "alias"]], "alias")
    out["pub_date"] = pd.to_datetime(dates.set_index("g")["pub_date"].str[:10],
                                     errors="coerce", format="%Y-%m-%d")

    pairs = {col: _query(sess, f"SELECT ?g ?v WHERE {{ {GAME} ?g wdt:{prop} ?v . }}")
             for col, prop in ENTITY_PROPS.items()}
    qids = sorted({v for df in pairs.values() for v in df["v"] if v.startswith("Q")})
    names = _prefer_en(_names_for(sess, qids)).to_dict()
    log.info("wikidata: %d labels de valores para %d QIDs distintos", len(names), len(qids))
    for col, df in pairs.items():
        df[col] = df["v"].map(names).fillna(df["v"])  # sem label -> mantém o QID
        out[col] = _joined(df[["g", col]], col)
        log.info("wikidata %s (%s): %d itens", col, ENTITY_PROPS[col], out[col].notna().sum())

    for col, prop in ID_PROPS.items():
        df = _query(sess, f"SELECT ?g ?{col} WHERE {{ {GAME} ?g wdt:{prop} ?{col} . }}")
        out[col] = _joined(df, col)
        log.info("wikidata %s (%s): %d itens", col, prop, out[col].notna().sum())

    out = out.reset_index().rename(columns={"g": "wd_qid"})
    out.to_parquet(WIKIDATA_GAMES, index=False)
    log.info("wikidata: %d jogos -> %s", len(out), WIKIDATA_GAMES)

    fetch_review_scores(sess)
    return out
