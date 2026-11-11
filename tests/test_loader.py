from toolcontract.loader import load_spec


def test_yaml_subset_spec_loads_and_lints(tmp_path):
    p = tmp_path / "mini.yaml"
    p.write_text(
        "openapi: 3.0.3\n"
        "info:\n"
        "  title: Mini\n"
        "  version: '1.0'\n"
        "paths:\n"
        "  /things:\n"
        "    get:\n"
        "      parameters:\n"
        "        - name: limit\n"
        "          in: query\n"
        "          description: Must be between 1 and 10.\n"
        "          schema:\n"
        "            type: integer\n"
        "      responses:\n"
        "        '200':\n"
        "          description: OK\n"
        "          content:\n"
        "            application/json:\n"
        "              schema:\n"
        "                type: object\n"
        "        '400':\n"
        "          description: Bad request\n",
        encoding="utf-8")
    spec = load_spec(p)
    assert spec["info"]["title"] == "Mini"
    from toolcontract.core import lint_spec
    codes = {(f.code, f.missing_keyword) for f in lint_spec(spec)}
    assert ("TCG001", "maximum") in codes
