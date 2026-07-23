from scripts.check_architecture_no_regression import compare, parse_import_edges


def test_parse_import_edges_ignores_line_number_drift():
    output = """
-   core_ui.services.operator_loop -> servers.models (l.338, l.349)
-   core_ui.services.operator_tools -> servers.views.server_helpers (l.155)
"""
    assert parse_import_edges(output) == {
        "core_ui.services.operator_loop -> servers.models",
        "core_ui.services.operator_tools -> servers.views.server_helpers",
    }


def test_compare_allows_reduction_but_rejects_new_or_grown_debt():
    baseline = {
        "architecture": {
            "sizeViolations": {"legacy.py": 600},
            "importEdges": ["old.source -> old.target"],
        }
    }
    reduced = {"sizeViolations": {"legacy.py": 550}, "importEdges": []}
    assert compare(baseline, reduced) == []

    regressed = {
        "sizeViolations": {"legacy.py": 601, "new.py": 501},
        "importEdges": ["new.source -> new.target"],
    }
    assert compare(baseline, regressed) == [
        "legacy size violation grew: legacy.py 600 -> 601",
        "new size violation: new.py (501 lines)",
        "new forbidden import edge: new.source -> new.target",
    ]
