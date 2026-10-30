import pandas as pd

from gsp.dataset import (METACRITIC, OPENCRITIC, history_pool, link_wikidata_igdb, select_games,
                         wikidata_validation)


def _ig(rows):
    cols = ["igdb_id", "slug", "game_type", "game_status", "first_release_date", "hypes", "critic_score"]
    return pd.DataFrame(rows, columns=cols)


def test_link_prefers_slug_and_is_one_to_one():
    ig = _ig([(1, "gta-v", "Main Game", None, None, None, None),
              (2, "gta-v-premium", "Main Game", None, None, None, None),
              (3, "doom", "Main Game", None, None, None, None)])
    ig_steam = pd.DataFrame({"igdb_id": [2, 3, 1], "steam_appid": [271590, 379720, 271590]})
    wd = pd.DataFrame({
        "wd_qid": ["Q1", "Q2", "Q3"],
        "igdb_slug": ["gta-v", None, None],
        "steam_appid": ["271590", "379720|999", "271590"],
    })
    links = link_wikidata_igdb(wd, ig, ig_steam).set_index("wd_qid")
    assert links.loc["Q1", "igdb_id"] == 1 and links.loc["Q1", "link_method"] == "slug"
    assert links.loc["Q2", "igdb_id"] == 3 and links.loc["Q2", "link_method"] == "steam"
    # Q3 disputa o jogo 1 com o Q1 (que tem slug) e perde: fica sem ligação
    assert "Q3" not in links.index
    assert links["igdb_id"].is_unique


def _score(qid, by, method, raw, value, scale, n=None, date=None, plats=None):
    return dict(wd_qid=qid, reviewer_qid=by, method=method, score_raw=raw, score_100=value,
                scale=scale, n_reviews=n, date=pd.Timestamp(date) if date else pd.NaT, platforms=plats)


def test_validation_latest_opencritic_average_and_main_metacritic_platform():
    scores = pd.DataFrame([
        _score("Q1", OPENCRITIC, "OpenCritic Top Critic Average", "80/100", 80, "/100", 100, "2021-01-01"),
        _score("Q1", OPENCRITIC, "OpenCritic Top Critic Average", "76/100", 76, "/100", 220, "2025-06-26"),
        _score("Q1", OPENCRITIC, None, "66%", 66, "%", 225, "2025-06-30"),  # recomendação, não média
        _score("Q1", METACRITIC, None, "86/100", 86, "/100", 92, plats="PC"),
        _score("Q1", METACRITIC, None, "57/100", 57, "/100", 38, plats="PS4"),
        _score("Q1", METACRITIC, None, "7.3/10", 73, "/10", 5000, plats="PC"),  # usuários
    ])
    v = wikidata_validation(scores).set_index("wd_qid").loc["Q1"]
    assert (v["oc_top_avg"], v["oc_n"]) == (76, 220)
    assert (v["mc_score"], v["mc_n"], v["mc_platform"]) == (86, 92, "PC")


def test_select_games_keeps_target_and_upcoming_with_hype():
    today = pd.Timestamp("2026-10-25")
    ig = _ig([
        (1, "a", "Main Game", None, pd.Timestamp("2020-01-01"), None, 80.0),   # com target
        (2, "b", "Main Game", None, pd.Timestamp("2020-01-01"), None, None),   # sem target
        (3, "c", "Main Game", None, pd.Timestamp("2026-11-19"), 1111, None),   # GTA VI
        (4, "d", "Main Game", "Cancelled", pd.NaT, 50, None),
        (5, "e", "DLC", None, pd.Timestamp("2020-01-01"), None, 90.0),
        (6, "f", "Main Game", None, pd.Timestamp("2027-01-01"), None, None),   # sem hype
    ])
    g = select_games(ig, today=today).set_index("igdb_id")
    assert sorted(g.index) == [1, 3]
    assert g.loc[3, "is_upcoming"] and not g.loc[1, "is_upcoming"]


def test_history_pool_keeps_released_games_with_any_critic_score():
    today = pd.Timestamp("2026-10-25")
    ig = _ig([
        (1, "a", "Main Game", None, pd.Timestamp("2020-01-01"), None, 80.0),   # nota IGDB
        (2, "oot", "Main Game", None, pd.Timestamp("1998-11-21"), None, None),  # só Metacritic
        (3, "c", "Main Game", None, pd.Timestamp("2020-01-01"), None, None),   # sem nota nenhuma
        (4, "gta-vi", "Main Game", None, pd.Timestamp("2026-11-19"), 1111, None),  # não lançado
        (5, "e", "DLC", None, pd.Timestamp("2020-01-01"), None, 90.0),
    ]).assign(critic_n=[5, None, None, None, 3], name=list("abcde"), developers=None, publishers=None,
              franchises=None, collections=None)
    val = pd.DataFrame({"igdb_id": [2, 4], "oc_top_avg": [None, None], "mc_score": [99.0, 97.0],
                        "wd_series": ["Zelda", "GTA"]})
    pool = history_pool(ig, val, today=today).set_index("igdb_id")
    assert list(pool.index) == [2, 1]  # ordenado por data
    assert pool.loc[2, "mc_score"] == 99 and pool.loc[2, "wd_series"] == "Zelda"
    assert pool.loc[1, "igdb_critic_score"] == 80
