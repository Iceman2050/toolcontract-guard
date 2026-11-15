from toolcontract.prose import extract_constraints, prose_says_required


def test_between():
    out = dict((k, v) for k, v, _ in extract_constraints("Must be between 1 and 100."))
    assert out == {"minimum": 1, "maximum": 100}


def test_one_of():
    out = extract_constraints("One of: pending, paid, shipped.")
    assert out[0][0] == "enum" and out[0][1] == ["pending", "paid", "shipped"]


def test_max_characters_phrasing_boundary():
    # "max N characters" alone is outside the recognised families
    # (they require "up to / at most / maximum of N characters"), so
    # nothing is extracted — the documented coverage boundary.
    assert extract_constraints("Search text, max 50 characters.") == []
    out = extract_constraints("Search text, up to 50 characters.")
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
    # Recognised family: "is/are required", "must be provided",
    # "required field". A bare "Required." is outside it.
    assert not prose_says_required("Required. The channel.")
    assert prose_says_required("This field is required for fulfilment.")
    assert prose_says_required("The token must be provided.")
    assert not prose_says_required("Optional filter.")
