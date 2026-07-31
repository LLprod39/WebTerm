from scripts.env_contract import CATEGORIES, parse_example, render_document, unused_variables


def test_production_environment_example_is_documented_and_used():
    variables = parse_example()
    assert {item.category for item in variables} == set(CATEGORIES)
    assert unused_variables(variables) == []
    rendered = render_document(variables)
    assert "## Required" in rendered
    assert "## Frequently changed" in rendered
    assert "## Expert tuning" in rendered
    assert "`DJANGO_SECRET_KEY`" in rendered
