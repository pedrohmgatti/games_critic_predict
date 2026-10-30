"""CLI do pipeline. Cada etapa lê o artefato da anterior e grava o seu em data/.

    gsp igdb         # 1. IGDB: catálogo, target (nota da crítica), hypes e app ids da Steam
    gsp wikidata     # 2. Wikidata: metadados, IDs e notas de agregadores (sem chave)
    gsp build        # 3. junta tudo -> data/processed/games_scores.parquet, history_pool.parquet + relatório
    gsp all          # tudo em sequência
"""

from __future__ import annotations

import argparse
import logging


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="gsp", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["igdb", "wikidata", "build", "all"])
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.step in ("igdb", "all"):
        from gsp.enrich.igdb import fetch_igdb
        fetch_igdb()
    if args.step in ("wikidata", "all"):
        from gsp.enrich.wikidata import fetch_wikidata
        fetch_wikidata()
    if args.step in ("build", "all"):
        from gsp.dataset import build
        build()


if __name__ == "__main__":
    main()
