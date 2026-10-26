import pytest

from gsp.enrich.igdb import _flatten
from gsp.enrich.wikidata import parse_score


@pytest.mark.parametrize("raw,expected", [
    ("64/100", (64.0, "/100")),
    ("22%", (22.0, "%")),
    ("73.33%", (73.33, "%")),
    ("7.3/10", (73.0, "/10")),
    ("16/20", (80.0, "/20")),
    ("4,5/5", (90.0, "/5")),
    ("97", (None, None)),        # sem escala
    ("★★★", (None, None)),
    ("110/100", (None, None)),   # acima do máximo
])
def test_parse_score(raw, expected):
    assert parse_score(raw) == expected


def test_igdb_flatten_separator_and_targets():
    g = {"id": 1, "name": "X", "first_release_date": 1379376000, "aggregated_rating": 88.1,
         "aggregated_rating_count": 27, "game_type": {"type": "Main Game"},
         "platforms": [{"name": "Xbox Series X|S", "abbreviation": "Series X|S"}],
         "franchise": {"name": "GTA"}, "franchises": [{"name": "GTA"}],
         "involved_companies": [{"company": {"name": "Rockstar North"}, "developer": True},
                                {"company": {"name": "Rockstar Games"}, "publisher": True}]}
    row = _flatten(g)
    assert row["platforms"] == "Xbox Series X/S|Series X/S"
    assert row["franchises"] == "GTA"
    assert (row["critic_score"], row["critic_n"], row["game_type"]) == (88.1, 27, "Main Game")
    assert (row["developers"], row["publishers"]) == ("Rockstar North", "Rockstar Games")
