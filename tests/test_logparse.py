import pandas as pd

from x4analyzer import logparse


def log_df(rows):
    df = pd.DataFrame(rows)
    for col in ("time", "category", "title", "text", "money", "component"):
        if col not in df.columns:
            df[col] = pd.NA
    df["category"] = df["category"].fillna("")
    return df


SECTORS = pd.DataFrame({
    "name": ["Grand Exchange IV", "Neptune"],
    "sector.macro": ["cluster_01_sector003_macro", "cluster_110_sector001_macro"],
})


def test_pirate_harassment_real_v9_text():
    # verbatim text shape from a v9.0 savegame
    df = log_df([{
        "time": 25594.6, "category": "", "title": "Pirate Harassment",
        "text": (r"TM-02-Boa FQC-876 in Grand Exchange IV[\012]"
                 r"Accosted by Teladi Company pirate ship[\012]"
                 r"TEL Pillager Minotaur Raider WIG-904.[\012]Response: Wait"),
    }])
    out = logparse.parse_pirates(df, SECTORS)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ship.name"] == "TM-02-Boa"
    assert row["ship.code"] == "FQC-876"
    assert row["sector.name"] == "Grand Exchange IV"
    assert row["sector.macro"] == "cluster_01_sector003_macro"
    assert row["pirate.faction"] == "TEL"
    assert row["pirate.name"] == "Pillager Minotaur Raider"
    assert row["pirate.code"] == "WIG-904"
    assert row["response"] == "Wait"


def test_police_interdiction():
    df = log_df([{
        "time": 10507.4, "category": "", "title": "Police Interdiction",
        "text": (r"RSS-01-Kestrel Sentinel FFN-055 in Neptune[\012]"
                 r"Ordered by Terran Protectorate police to stop for a cargo "
                 r"inspection.[\012]Response: Comply"),
    }])
    out = logparse.parse_police(df, SECTORS,
                                {"Terran Protectorate": "TER"})
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ship.name"] == "RSS-01-Kestrel Sentinel"
    assert row["sector.macro"] == "cluster_110_sector001_macro"
    assert row["police.faction"] == "TER"
    assert row["response"] == "Comply"


def test_ship_construction_sale():
    df = log_df([{
        "time": 100.0, "category": "upkeep", "title": "Ship constructed",
        "money": 1234500.0,
        "text": ("ARG Behemoth Vanguard (ABC-123) finished construction at "
                 "station: My Wharf (XYZ-999). They have paid 12,345 Cr."),
    }])
    out = logparse.parse_ship_services(
        df, "Ship constructed", " finished construction at station: ",
        "Ship construction")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["seller.name"] == "My Wharf"
    assert row["seller.code"] == "XYZ-999"
    assert row["buyer.faction"] == "ARG"
    assert row["buyer.name"] == "Behemoth Vanguard"
    assert row["buyer.code"] == "ABC-123"
    assert row["money"] == 12345
    assert row["commodity"] == "Ship construction"


def test_destroyed():
    df = log_df([{
        "time": 50.0, "category": "upkeep",
        "title": ("Your ship TM-01-Boa in sector Grand Exchange IV was "
                  "destroyed by XEN K."),
    }])
    out = logparse.parse_destroyed(df)
    assert len(out) == 1
    assert out.iloc[0]["object"] == "Your ship TM-01-Boa"
    assert out.iloc[0]["location"] == "Grand Exchange IV"
    assert out.iloc[0]["killer"] == "XEN K"


def test_ship_resupply_v9_details_in_text():
    # real v9 entry (user save): title is bare, details live in the text,
    # and the payment line says "paid the station"
    df = log_df([{
        "time": 1826462.355, "category": "upkeep",
        "title": "Ship resupplied", "money": 42297500.0,
        "text": ("ZYA Representative Envoy (XMI-099) finished resupplying "
                 "at station: ARC Areus Equipment Dock I (OBD-539). They "
                 "have paid the station 422,975 Cr."),
    }])
    out = logparse.parse_ship_services(
        df, "Ship resupplied", " finished resupplying at station: ",
        "Ship resupply")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["seller.name"] == "ARC Areus Equipment Dock I"
    assert row["seller.code"] == "OBD-539"
    assert row["buyer.faction"] == "ZYA"
    assert row["buyer.code"] == "XMI-099"
    assert row["money"] == 422975


def test_ship_resupply_old_details_in_title():
    # pre-v9 style: the details WERE the title
    df = log_df([{
        "time": 100.0, "category": "upkeep", "money": 100000.0,
        "title": ("ARG Ship (AAA-111) finished resupplying at station: "
                  "Depot (BBB-222). They have paid 1,000 Cr."),
    }])
    out = logparse.parse_ship_services(
        df, ("ARG Ship (AAA-111) finished resupplying at station: "
             "Depot (BBB-222). They have paid 1,000 Cr."),
        " finished resupplying at station: ", "Ship resupply")
    assert len(out) == 1
    assert out.iloc[0]["seller.code"] == "BBB-222"


def test_ship_services_unmatched_wording_skips_and_dumps(capsys):
    # title matches but the text wording differs (v9 drift seen in the
    # wild): the split phrase is absent from every row
    df = log_df([{
        "time": 100.0, "category": "upkeep", "title": "Ship constructed",
        "money": 1234500.0,
        "text": "Some different v9 wording without the split phrase.",
    }])
    out = logparse.parse_ship_services(
        df, "Ship constructed", " finished construction at station: ",
        "Ship construction")
    assert out.empty
    err = capsys.readouterr().err
    assert "did not match the expected wording" in err
    assert "different v9 wording" in err  # the raw string is dumped


def test_destroyed_unmatched_wording_skips_and_dumps(capsys):
    df = log_df([{
        "time": 50.0, "category": "upkeep",
        "title": "Your ship was destroyed by something unspeakable",
    }])
    out = logparse.parse_destroyed(df)
    assert out.empty
    assert "unspeakable" in capsys.readouterr().err


def test_pirates_police_unmatched_wording_skips_and_dumps(capsys):
    df = log_df([
        {"time": 1.0, "category": "", "title": "Pirate Harassment",
         "text": "reworded pirate text"},
        {"time": 2.0, "category": "", "title": "Police Interdiction",
         "text": "reworded police text"},
    ])
    assert logparse.parse_pirates(df, SECTORS).empty
    assert logparse.parse_police(df, SECTORS, {}).empty
    err = capsys.readouterr().err
    assert "reworded pirate text" in err
    assert "reworded police text" in err


def test_transfers_unmatched_wording_skips_and_dumps(capsys):
    df = log_df([
        {"time": 1.0, "category": "upkeep",
         "title": "Received surplus of gratitude"},
        {"time": 2.0, "category": "upkeep",
         "title": "Received surplus from beyond"},
    ])
    npcs = pd.DataFrame(columns=["name", "id", "role"])
    stations = pd.DataFrame(
        columns=["id", "manager.id", "code", "name"])
    out = logparse.parse_transfers(df, npcs, stations)
    assert out.empty
    err = capsys.readouterr().err
    assert "surplus of gratitude" in err
    assert "surplus from beyond" in err


def test_empty_log_gives_empty_frames():
    df = log_df([{"time": 1.0, "category": "", "title": "Nothing"}])
    assert logparse.parse_destroyed(df).empty
    assert logparse.parse_pirates(df, SECTORS).empty
    assert logparse.parse_police(df, SECTORS, {}).empty
    assert logparse.parse_ship_services(
        df, "Ship constructed", " finished construction at station: ",
        "Ship construction").empty
