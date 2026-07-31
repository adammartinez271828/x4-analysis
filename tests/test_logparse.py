import pandas as pd

from x4analyzer.save import logparse


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


def test_destroyed_v9_wording():
    # verbatim v9 shapes from the reference playthrough's archived
    # history: plain, with a Commander line, and killer-less
    df = log_df([
        {"time": 50.0, "category": "upkeep",
         "title": "RS-PE (GDV-373) was destroyed.",
         "text": (r"Location: Litany of Fury IX[\012]"
                  r"Destroyed by: XEN Raiding Party F (GZM-478)")},
        {"time": 60.0, "category": "upkeep",
         "title": "PE (NOZ-570) was destroyed.",
         "text": (r"Location: Matrix #598[\012]Commander: PE (JVC-254)"
                  r"[\012]Destroyed by: XEN Raiding Party F (BRK-198)")},
        {"time": 70.0, "category": "upkeep",
         "title": "Buzzard Sentinel (JQX-111) was destroyed.",
         "text": "Location: Getsu Fune"},
    ])
    out = logparse.parse_destroyed(df)
    assert len(out) == 3
    assert list(out["object"]) == ["RS-PE (GDV-373)", "PE (NOZ-570)",
                                   "Buzzard Sentinel (JQX-111)"]
    assert list(out["location"]) == ["Litany of Fury IX", "Matrix #598",
                                     "Getsu Fune"]
    assert out.iloc[0]["killer"] == "XEN Raiding Party F (GZM-478)"
    # the Commander line must not be mistaken for the killer
    assert out.iloc[1]["killer"] == "XEN Raiding Party F (BRK-198)"
    assert pd.isna(out.iloc[2]["killer"])


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
        "title": "Doomed Ship (AAA-000) was destroyed.",
        "text": "Somewhere unspeakable, no Location line",
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


def test_combat_rewards_v9_wording():
    # verbatim v9 shapes from the reference playthrough's merged history:
    # single ship, two ships sharing one reward, a station credit with a
    # role-suffixed paying station, and a reward with no bounty at all
    df = log_df([
        {"time": 4646.1, "category": "", "title": "Combat Reward",
         "money": 2653090.0,
         "text": (r"Faction: Antigone Republic[\012]"
                  r"Station: ANT Turret Component Factory I (TLT-325)[\012]"
                  r"Sector: The Void[\012]"
                  r"Credited To: Ships: D-01-Phoenix E (PIE-222)[\012]"
                  r"Bounty: 26,530 Cr[\012]Reputation: +2")},
        {"time": 5476.9, "category": "", "title": "Combat Reward",
         "money": 3441242.0,
         "text": (r"Faction: Antigone Republic[\012]"
                  r"Station: ANT Engine Part Factory I (KYY-940)[\012]"
                  r"Sector: The Void[\012]"
                  r"Credited To: Ships: 00-Honshu (GCG-310), "
                  r"D-01-Phoenix E (PIE-222)[\012]"
                  r"Bounty: 34,412 Cr[\012]Reputation: +2")},
        {"time": 6000.0, "category": "", "title": "Combat Reward",
         "money": 4745870.0,
         "text": (r"Faction: Holy Order of the Pontifex[\012]"
                  r"Station: HOP Paranid Wharf (THO-697) "
                  r"(Police Representative)[\012]"
                  r"Sector: Holy Vision[\012]"
                  r"Credited To: Stations: Holy Vision Defense Platform "
                  r"(TXG-185)[\012]Bounty: 47,458 Cr")},
        {"time": 7000.0, "category": "", "title": "Combat Reward",
         "text": (r"Faction: Argon Federation[\012]"
                  r"Station: ARG Argon Trading Station (GMJ-316)[\012]"
                  r"Sector: Silent Witness I[\012]"
                  r"Credited To: Ships: 03-Hyperion (LRY-339)[\012]"
                  r"Reputation: +<1")},
    ])
    out = logparse.parse_combat_rewards(df)
    # one row per credited ship: the shared reward yields two
    assert len(out) == 5
    assert out["reward"].nunique() == 4

    first = out.iloc[0]
    assert first["faction"] == "Antigone Republic"
    assert first["station"] == "ANT Turret Component Factory I (TLT-325)"
    assert first["sector"] == "The Void"
    assert first["kind"] == "ship"
    assert first["ship.name"] == "D-01-Phoenix E"
    assert first["ship.code"] == "PIE-222"
    assert first["bounty_cr"] == 26530.90   # money is cents, like elsewhere
    assert first["reputation"] == 2.0

    shared = out[out["reward"] == 1]
    assert list(shared["ship.name"]) == ["00-Honshu", "D-01-Phoenix E"]
    assert list(shared["ship.code"]) == ["GCG-310", "PIE-222"]
    # the payout repeats on every credited row (documented double-count)
    assert list(shared["bounty_cr"]) == [34412.42, 34412.42]

    # station credit: the paying station's role suffix must not be
    # mistaken for the credited party
    station = out[out["kind"] == "station"].iloc[0]
    assert station["ship.name"] == "Holy Vision Defense Platform"
    assert station["ship.code"] == "TXG-185"
    assert station["station"] == ("HOP Paranid Wharf (THO-697) "
                                  "(Police Representative)")
    assert pd.isna(station["reputation"])   # no Reputation line

    # no Bounty line at all -> no money on the entry either
    norep = out.iloc[-1]
    assert pd.isna(norep["bounty_cr"])
    assert norep["reputation"] == 0.5       # "+<1" placeholder


def test_combat_rewards_unmatched_wording_skips_and_dumps(capsys):
    df = log_df([{"time": 1.0, "category": "", "title": "Combat Reward",
                  "text": "reworded reward text"}])
    assert logparse.parse_combat_rewards(df).empty
    assert "reworded reward text" in capsys.readouterr().err


def test_ship_claims_v9_wording():
    df = log_df([
        {"time": 4712.2, "category": "", "title": "Found Abandoned Ship",
         "text": (r"RS-PE JVC-254 in Antigone Memorial[\012]"
                  r"Found abandoned ship B IAY-307.[\012]"
                  r"Response: Claim if possible")},
        {"time": 6273.9, "category": "", "title": "Found Abandoned Ship",
         "text": (r"02-Hyperion LRY-339 in Silent Witness XII[\012]"
                  r"Found abandoned ship Falcon Vanguard XER-389.[\012]"
                  r"Response: Claim if possible")},
    ])
    out = logparse.parse_ship_claims(df)
    assert len(out) == 2
    assert list(out["finder"]) == ["RS-PE", "02-Hyperion"]
    assert list(out["finder.code"]) == ["JVC-254", "LRY-339"]
    assert list(out["sector"]) == ["Antigone Memorial", "Silent Witness XII"]
    assert list(out["claimed"]) == ["B", "Falcon Vanguard"]
    assert list(out["claimed.code"]) == ["IAY-307", "XER-389"]


def test_ship_claims_unmatched_wording_skips_and_dumps(capsys):
    df = log_df([{"time": 1.0, "category": "", "title": "Found Abandoned Ship",
                  "text": "reworded claim text"}])
    assert logparse.parse_ship_claims(df).empty
    assert "reworded claim text" in capsys.readouterr().err


def test_pilot_bails_v9_wording():
    # the whole record is in the title and the category is upkeep
    df = log_df([
        {"time": 2257.6, "category": "upkeep",
         "title": "Forced pilot to leave ship XEN Raiding Party PE in "
                  "sector The Void."},
        {"time": 4958.4, "category": "upkeep",
         "title": "Forced pilot to leave ship BUC Recon Fighter Pegasus "
                  "Vanguard in sector Trinity Sanctum III."},
    ])
    out = logparse.parse_pilot_bails(df)
    assert len(out) == 2
    assert list(out["ship"]) == ["XEN Raiding Party PE",
                                 "BUC Recon Fighter Pegasus Vanguard"]
    assert list(out["sector"]) == ["The Void", "Trinity Sanctum III"]


def test_pilot_bails_unmatched_wording_skips_and_dumps(capsys):
    df = log_df([{"time": 1.0, "category": "upkeep",
                  "title": "Forced pilot to leave ship somewhere odd"}])
    assert logparse.parse_pilot_bails(df).empty
    assert "somewhere odd" in capsys.readouterr().err


def test_empty_log_gives_empty_frames():
    df = log_df([{"time": 1.0, "category": "", "title": "Nothing"}])
    assert logparse.parse_destroyed(df).empty
    assert logparse.parse_pirates(df, SECTORS).empty
    assert logparse.parse_police(df, SECTORS, {}).empty
    assert logparse.parse_combat_rewards(df).empty
    assert logparse.parse_ship_claims(df).empty
    assert logparse.parse_pilot_bails(df).empty
    assert logparse.parse_ship_services(
        df, "Ship constructed", " finished construction at station: ",
        "Ship construction").empty
