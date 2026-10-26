"""Dump do IGDB (requer TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET).

Baixa o catálogo inteiro paginando por id (keyset) e grava dois artefatos:
- `igdb_games.parquet`: metadados, `hypes` e as notas;
- `igdb_steam_ids.parquet`: app ids da Steam (`external_games`), ponte para os reviews.

Campos que viram target (pós-lançamento, NÃO usar como feature):
- `aggregated_rating` / `aggregated_rating_count`: média de críticos externos (0–100).
  Não é o Metacritic: o GTA V tem 88 aqui e 97 lá, porque o IGDB mistura versões e veículos;
- `rating` / `rating_count`: nota dos usuários do IGDB.

`hypes` é o nº de follows *antes* do lançamento, um sinal de hype pré-lançamento sem o
vazamento temporal das views do YouTube.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import pandas as pd
import requests

from gsp.config import IGDB_GAMES, IGDB_STEAM, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET

log = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API = "https://api.igdb.com/v4"
PAGE = 500
MIN_INTERVAL = 0.3  # limite da API: 4 req/s
STEAM_SOURCE = 1  # external_game_sources: 1 = Steam

FIELDS = ",".join([
    "id", "name", "slug", "first_release_date", "hypes",
    "aggregated_rating", "aggregated_rating_count", "rating", "rating_count",
    "game_type.type", "game_status.status", "parent_game", "version_parent",
    "alternative_names.name", "platforms.name", "platforms.abbreviation",
    "genres.name", "themes.name", "game_modes.name", "player_perspectives.name",
    "franchise.name", "franchises.name", "collections.name", "game_engines.name",
    "involved_companies.company.name", "involved_companies.developer",
    "involved_companies.publisher",
])


def _token() -> str:
    r = requests.post(TOKEN_URL, params={
        "client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _names(items, key="name") -> str | None:
    # "|" é o separador das listas; o IGDB o usa em nomes ("Xbox Series X|S")
    vals = sorted({i[key].replace("|", "/") for i in items or [] if i.get(key)})
    return "|".join(vals) or None


def _flatten(g: dict) -> dict:
    companies = g.get("involved_companies") or []
    franchises = list(g.get("franchises") or []) + ([g["franchise"]] if g.get("franchise") else [])
    return {
        "igdb_id": g["id"],
        "name": g.get("name"),
        "slug": g.get("slug"),
        "first_release_date": pd.to_datetime(g.get("first_release_date"), unit="s"),
        "game_type": (g.get("game_type") or {}).get("type"),
        "game_status": (g.get("game_status") or {}).get("status"),
        "parent_game": g.get("parent_game"),
        "version_parent": g.get("version_parent"),
        "hypes": g.get("hypes"),
        "critic_score": g.get("aggregated_rating"),
        "critic_n": g.get("aggregated_rating_count"),
        "user_score": g.get("rating"),
        "user_n": g.get("rating_count"),
        "alt_names": _names(g.get("alternative_names")),
        # nomes completos + abreviações, para o mapeamento de plataformas
        "platforms": "|".join(filter(None, [_names(g.get("platforms")),
                                            _names(g.get("platforms"), "abbreviation")])) or None,
        "genres": _names(g.get("genres")),
        "themes": _names(g.get("themes")),
        "game_modes": _names(g.get("game_modes")),
        "perspectives": _names(g.get("player_perspectives")),
        "franchises": _names(franchises),
        "collections": _names(g.get("collections")),
        "engines": _names(g.get("game_engines")),
        "developers": _names([c["company"] for c in companies if c.get("developer") and c.get("company")]),
        "publishers": _names([c["company"] for c in companies if c.get("publisher") and c.get("company")]),
    }


def _dump(s: requests.Session, endpoint: str, fields: str, flatten: Callable[[dict], dict],
          where: str | None = None) -> pd.DataFrame:
    rows, last_id = [], 0
    while True:
        cond = f"id > {last_id}" + (f" & {where}" if where else "")
        body = f"fields {fields}; where {cond}; sort id asc; limit {PAGE};"
        for attempt in range(5):
            r = s.post(f"{API}/{endpoint}", data=body, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(2 ** attempt)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        rows += [flatten(x) for x in page]
        last_id = page[-1]["id"]
        if len(rows) % 20000 < PAGE:
            log.info("igdb %s: %d linhas (id até %d)", endpoint, len(rows), last_id)
        time.sleep(MIN_INTERVAL)
    return pd.DataFrame(rows)


def fetch_igdb() -> pd.DataFrame:
    if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
        raise SystemExit("defina TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET no .env (https://api-docs.igdb.com)")
    s = requests.Session()
    s.headers.update({"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {_token()}"})

    games = _dump(s, "games", FIELDS, _flatten)
    games.to_parquet(IGDB_GAMES, index=False)
    log.info("igdb: %d jogos, %d com nota da crítica -> %s",
             len(games), games["critic_score"].notna().sum(), IGDB_GAMES)

    steam = _dump(s, "external_games", "game,uid",
                  lambda x: {"igdb_id": x.get("game"), "steam_appid": x.get("uid")},
                  where=f"external_game_source = {STEAM_SOURCE}")
    # uid é texto; descarta lixo (URLs, vazios) e duplicatas
    steam = steam[steam["steam_appid"].astype(str).str.fullmatch(r"\d+")].dropna()
    steam = steam.astype({"igdb_id": "int64", "steam_appid": "int64"}).drop_duplicates()
    steam.to_parquet(IGDB_STEAM, index=False)
    log.info("igdb: %d pares jogo-Steam -> %s", len(steam), IGDB_STEAM)
    return games
