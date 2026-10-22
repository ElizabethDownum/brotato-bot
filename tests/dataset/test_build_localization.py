# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.localization import parse_translations_csv, resolve_text

CSV = ('keys,en,fr\n'
       'WEAPON_SHREDDER,Shredder,Broyeur\n'
       'WEAPON_SHREDDER_DESC,"Chance to explode, hitting nearby enemies",Explose\n'
       ',skipme,\n')


def test_parse_translations_picks_locale_column():
    tr = parse_translations_csv(CSV)
    assert tr["WEAPON_SHREDDER"] == "Shredder"
    tr_fr = parse_translations_csv(CSV, locale="fr")
    assert tr_fr["WEAPON_SHREDDER"] == "Broyeur"


def test_parse_translations_handles_quoted_commas():
    tr = parse_translations_csv(CSV)
    assert tr["WEAPON_SHREDDER_DESC"] == "Chance to explode, hitting nearby enemies"


def test_parse_translations_skips_blank_keys_and_unknown_locale():
    assert "" not in parse_translations_csv(CSV)
    assert parse_translations_csv(CSV, locale="xx") == {}


def test_resolve_text_falls_back():
    tr = {"WEAPON_SHREDDER": "Shredder"}
    assert resolve_text(tr, "WEAPON_SHREDDER", "slug") == "Shredder"
    assert resolve_text(tr, "MISSING_KEY", "slug") == "slug"
    assert resolve_text(None, "WEAPON_SHREDDER", "slug") == "slug"
    assert resolve_text(tr, None) == ""


def test_resolve_text_falls_back_on_empty_translation_value():
    # A key that exists but is empty for the locale is unresolved, not blank.
    assert resolve_text({"WEAPON_SHREDDER": ""}, "WEAPON_SHREDDER", "slug") == "slug"
