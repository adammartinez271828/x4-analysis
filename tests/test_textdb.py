from x4analyzer.gamedata.textdb import TextDB


def make_db() -> TextDB:
    db = TextDB()
    db.load_xml(b"""<?xml version="1.0"?>
<language id="44">
  <page id="20101">
    <t id="1">Behemoth</t>
    <t id="2">{20101,1} Vanguard</t>
    <t id="3">Nividium(a precious metal)</t>
    <t id="4">Ship \\(damaged\\)</t>
  </page>
</language>""")
    return db


def test_plain_lookup():
    assert make_db().resolve("{20101,1}") == "Behemoth"


def test_nested_reference():
    assert make_db().resolve("{20101,2}") == "Behemoth Vanguard"


def test_comment_stripped():
    assert make_db().resolve("{20101,3}") == "Nividium"


def test_escaped_parens_kept():
    assert make_db().resolve("{20101,4}") == "Ship (damaged)"


def test_unknown_ref_left_visible():
    assert make_db().resolve("{99999,1}") == "{99999,1}"


def test_diff_form_merges():
    db = make_db()
    db.load_xml(b"""<diff><add sel="/language">
      <page id="20101"><t id="1">Overridden</t></page>
    </add></diff>""")
    assert db.resolve("{20101,1}") == "Overridden"


def test_csv_roundtrip(tmp_path):
    db = make_db()
    path = tmp_path / "textdb.csv.gz"
    n = db.dump_csv(path)
    assert n == 4
    db2 = TextDB.from_csv(path)
    assert db2.resolve("{20101,2}") == "Behemoth Vanguard"
