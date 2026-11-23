from app import rules


def data(ausserhalb="JA", unterschriften="", names=3, tagegeld="7", aufwand="5"):
    return {
        "tagegeld": {"fields": {"ausserhalb_gemeinde": ausserhalb, "teilnehmer_tagegeld": tagegeld,
                                "teilnehmer_aufwand": aufwand, "unterschriften": unterschriften}},
        "teilnehmer": {"tables": {"teilnehmer": [{"name": f"N{i}", "vorname": "", "wohnort": ""} for i in range(names)]
                                  + [{"name": "", "vorname": "", "wohnort": "Greven"}]}},
    }


def test_signatures_win_over_handwritten_number():
    d = data(unterschriften="4")
    rules.apply_teilnehmeranzahl(d)
    assert d["tagegeld"]["fields"]["teilnehmer_tagegeld"] == "4"
    assert d["tagegeld"]["fields"]["teilnehmer_aufwand"] == ""


def test_teilnehmerliste_when_no_signatures():
    d = data(ausserhalb="nein", unterschriften="0")
    rules.apply_teilnehmeranzahl(d)
    assert d["tagegeld"]["fields"]["teilnehmer_aufwand"] == "3"
    assert d["tagegeld"]["fields"]["teilnehmer_tagegeld"] == ""


def test_unknown_ausserhalb_or_nothing_to_count_leaves_values():
    d = data(ausserhalb="", unterschriften="4")
    rules.apply_teilnehmeranzahl(d)
    assert d["tagegeld"]["fields"]["teilnehmer_tagegeld"] == "7"
    d = data(names=0)
    rules.apply_teilnehmeranzahl(d)
    assert d["tagegeld"]["fields"]["teilnehmer_tagegeld"] == "7"
    rules.apply_teilnehmeranzahl({"teilnehmer": {}})  # no Tagegeld page: nothing happens


def test_only_if_empty_keeps_entered_values():
    d = data(unterschriften="4")
    rules.apply_teilnehmeranzahl(d, only_if_empty=True)
    assert d["tagegeld"]["fields"]["teilnehmer_tagegeld"] == "7"
    d = data(unterschriften="4", tagegeld="", aufwand="")
    rules.apply_teilnehmeranzahl(d, only_if_empty=True)
    assert d["tagegeld"]["fields"]["teilnehmer_tagegeld"] == "4"
