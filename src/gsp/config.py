"""Caminhos e parâmetros globais do pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
HTTP_CACHE = RAW / "http_cache"

for _d in (RAW, PROCESSED, REPORTS, HTTP_CACHE):
    _d.mkdir(parents=True, exist_ok=True)

# Artefatos de cada etapa
IGDB_GAMES = RAW / "igdb_games.parquet"
IGDB_STEAM = RAW / "igdb_steam_ids.parquet"
WIKIDATA_GAMES = RAW / "wikidata_games.parquet"
WIKIDATA_SCORES = RAW / "wikidata_review_scores.parquet"
DATASET = PROCESSED / "games_scores.parquet"

# Polidez com os servidores: intervalo mínimo entre requisições (segundos)
WIKIDATA_MIN_INTERVAL = float(os.getenv("WIKIDATA_MIN_INTERVAL", "2.0"))

# A política da Wikimedia pede um UA identificável; defina um contato no .env se quiser.
BOT_UA = os.getenv("BOT_USER_AGENT", "games-critic-predict/0.1 (academic research project)")

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
