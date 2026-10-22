import json
from pathlib import Path

import pytest

from brotato_bot import cli
from brotato_bot.knowledge import cache, wiki


def _src(slug="stats", ref="Stats"):
    return {"slug": slug, "kind": "wiki", "ref": ref}


def test_refresh_writes_front_matter(tmp_path):
    results = cache.refresh([_src()], tmp_path, lambda source: "hello")
    text = (tmp_path / "stats.md").read_text(encoding="utf-8")
    assert text.startswith("---\nsource: Stats\nfetched_at: ")
    meta, body = cache.split_front_matter(text)
    assert meta["source"] == "Stats"
    assert "T" in meta["fetched_at"]
    assert body.strip() == "hello"
    assert [(r.slug, r.ok, r.error) for r in results] == [("stats", True, None)]
    assert not list(tmp_path.glob("*.tmp"))


def test_fetch_failure_keeps_old_cache(tmp_path):
    target = tmp_path / "stats.md"
    old = b"---\nsource: Stats\nfetched_at: 2026-01-01T00:00:00+00:00\n---\nold body\n"
    target.write_bytes(old)

    def boom(source):
        raise OSError("network down")

    results = cache.refresh([_src()], tmp_path, boom)
    assert target.read_bytes() == old
    assert len(results) == 1 and not results[0].ok
    assert "network down" in results[0].error
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stats.md"]


def test_fetch_failure_without_old_cache_writes_nothing(tmp_path):
    def boom(source):
        raise OSError("network down")

    results = cache.refresh([_src()], tmp_path, boom)
    assert results[0].error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("empty", ["", "   \n\t"])
def test_empty_fetch_is_an_error_and_keeps_old_cache(tmp_path, empty):
    target = tmp_path / "stats.md"
    old = b"---\nsource: Stats\nfetched_at: x\n---\nold body\n"
    target.write_bytes(old)
    results = cache.refresh([_src()], tmp_path, lambda source: empty)
    assert target.read_bytes() == old
    assert not results[0].ok and "empty" in results[0].error
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stats.md"]


def test_one_failure_does_not_stop_other_sources(tmp_path):
    def fetch(source):
        if source["slug"] == "bad":
            raise OSError("nope")
        return "good text"

    results = cache.refresh([_src("bad", "Bad"), _src("good", "Good")], tmp_path, fetch)
    assert [(r.slug, r.ok) for r in results] == [("bad", False), ("good", True)]
    assert (tmp_path / "good.md").exists() and not (tmp_path / "bad.md").exists()


def test_load_all_keys_by_slug(tmp_path):
    cache.refresh([_src("a", "A"), _src("b", "B")], tmp_path, lambda s: "body " + s["ref"])
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    loaded = cache.load_all(tmp_path)
    assert sorted(loaded) == ["a", "b"]
    assert "body A" in loaded["a"]
    assert cache.load_all(tmp_path / "missing") == {}


def test_excerpt_selects_paragraphs_with_terms():
    text = (
        "---\nsource: X\nfetched_at: t\n---\n"
        "Intro about nothing.\n\n"
        "Harvesting gives materials each wave.\n\n"
        "Unrelated paragraph.\n\n"
        "Ranged damage scales guns.\nSecond line.\n\n"
        "More harvesting talk."
    )
    out = cache.excerpt(text, ["HARVESTING", "ranged damage"])
    assert out == (
        "Harvesting gives materials each wave.\n\n"
        "Ranged damage scales guns.\nSecond line.\n\n"
        "More harvesting talk."
    )
    assert "source:" not in cache.excerpt(text, ["source"])
    assert cache.excerpt(text, ["absent"]) == ""
    assert cache.excerpt(text, []) == ""
    short = cache.excerpt(text, ["harvesting"], max_chars=20)
    assert len(short) <= 20 and short.startswith("Harvesting")


def test_fetch_page_builds_api_url_and_returns_wikitext():
    seen = []

    def fake(url):
        seen.append(url)
        return json.dumps({"parse": {"title": "Well Rounded", "wikitext": {"*": "WT"}}}).encode()

    assert wiki.fetch_page("Well Rounded", fetch=fake) == "WT"
    assert seen[0].startswith(
        wiki.BASE_URL + "/api.php?action=parse&page=Well%20Rounded&prop=wikitext&format=json"
    )


def test_fetch_page_raises_on_api_error():
    def fake(url):
        return json.dumps({"error": {"code": "missingtitle", "info": "no page"}}).encode()

    with pytest.raises(wiki.WikiError, match="missingtitle"):
        wiki.fetch_page("Nope", fetch=fake)


def test_character_sources_from_dataset():
    dataset = {
        "characters": [
            {"id": "character_well_rounded", "name": "Well Rounded"},
            {"id": "character_one_arm", "name": "One Arm", "dlc": None},
        ]
    }
    assert cache.character_sources(dataset) == [
        {"slug": "character-well-rounded", "kind": "wiki", "ref": "Well Rounded"},
        {"slug": "character-one-arm", "kind": "wiki", "ref": "One Armed"},
    ]


def test_merge_sources_dedupes_by_slug():
    base = [{"slug": "a", "kind": "wiki", "ref": "A"}]
    extra = [
        {"slug": "a", "kind": "wiki", "ref": "Other"},
        {"slug": "b", "kind": "wiki", "ref": "B"},
    ]
    assert cache.merge_sources(base, extra) == [base[0], extra[1]]


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "knowledge").mkdir(parents=True)
    monkeypatch.setenv("BROTATO_BOT_PROJECT_ROOT", str(root))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    for name in ("KNOWLEDGE_DIR", "KNOWLEDGE_CACHE", "DATA_DIR"):
        monkeypatch.delenv("BROTATO_BOT_" + name, raising=False)
    sources = [_src("stats", "Stats"), _src("waves", "Waves")]
    (root / "knowledge" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    calls = []

    def fake_fetch(source):
        calls.append(source["slug"])
        return "text for " + source["ref"]

    monkeypatch.setattr("brotato_bot.knowledge.command.default_fetch", fake_fetch)
    return root, calls


def test_cli_fetch_only(project):
    root, calls = project
    assert cli.main(["knowledge", "fetch", "--only", "waves"]) == 0
    assert calls == ["waves"]
    assert (root / "knowledge" / "cache" / "waves.md").exists()
    assert cli.main(["knowledge", "fetch", "--only", "nope"]) == 1


def test_cli_characters_appends_sources(project):
    root, calls = project
    data = root / "data"
    data.mkdir()
    (data / "brotato.json").write_text(
        json.dumps({"characters": [{"id": "character_bull", "name": "Bull"}]}), encoding="utf-8"
    )
    assert cli.main(["knowledge", "fetch", "--characters"]) == 0
    saved = json.loads((root / "knowledge" / "sources.json").read_text(encoding="utf-8"))
    assert [s["slug"] for s in saved] == ["stats", "waves", "character-bull"]
    assert calls == ["stats", "waves", "character-bull"]
    # Idempotent: a second run does not duplicate the entry.
    assert cli.main(["knowledge", "fetch", "--characters", "--only", "stats"]) == 0
    saved = json.loads((root / "knowledge" / "sources.json").read_text(encoding="utf-8"))
    assert [s["slug"] for s in saved] == ["stats", "waves", "character-bull"]


def test_cli_characters_without_dataset(project, capsys):
    _root, calls = project
    assert cli.main(["knowledge", "fetch", "--characters", "--only", "stats"]) == 0
    assert "brotato.json" in capsys.readouterr().out
    assert calls == ["stats"]


def test_cli_fetch_failure_returns_nonzero(project, monkeypatch):
    def boom(source):
        raise OSError("down")

    monkeypatch.setattr("brotato_bot.knowledge.command.default_fetch", boom)
    assert cli.main(["knowledge", "fetch"]) == 1


def test_committed_sources_and_guides_are_well_formed():
    root = Path(__file__).resolve().parents[2]
    sources = json.loads((root / "knowledge" / "sources.json").read_text(encoding="utf-8"))
    slugs = [s["slug"] for s in sources]
    assert len(slugs) == len(set(slugs))
    refs = {s["ref"] for s in sources if s["kind"] == "wiki"}
    assert {"Stats", "Characters", "Weapons", "Items", "Danger Levels", "Waves", "Enemies"} <= refs
    for name in ("botato-character-profiles.md", "botato-shop-guides.md"):
        meta, body = cache.split_front_matter(
            (root / "knowledge" / "cache" / name).read_text(encoding="utf-8")
        )
        assert meta["source"] == "github.com/boardengineer/botato"
        assert meta["fetched_at"] and body.strip()
