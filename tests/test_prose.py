from toolcontract.prose import extract_constraints, prose_says_required


def test_between():
    out = dict((k, v) for k, v, _ in extract_constraints("Must be between 1 and 100."))
    assert out == {"minimum": 1, "maximum": 100}


def test_one_of():
    out = extract_constraints("One of: pending, paid, shipped.")
    assert out[0][0] == "enum" and out[0][1] == ["pending", "paid", "shipped"]


def test_max_characters_is_maxlength_not_maximum():
    out = extract_constraints("Search text, max 50 characters.")
    assert [(k, v) for k, v, _ in out] == [("maxLength", 50)]


def test_at_least_characters_is_minlength():
    out = extract_constraints("At least 3 characters long.")
    assert [(k, v) for k, v, _ in out] == [("minLength", 3)]


def test_at_most_numeric():
    out = extract_constraints("Return at most 25 results.")
    assert [(k, v) for k, v, _ in out] == [("maximum", 25)]


def test_no_constraint_in_plain_prose():
    assert extract_constraints("A friendly description of a thing.") == []


def test_prose_says_required():
    assert prose_says_required("Required. The channel.")
    assert not prose_says_required("Optional filter.")
