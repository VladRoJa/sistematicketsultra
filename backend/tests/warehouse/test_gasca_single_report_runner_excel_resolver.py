import pytest

from app.warehouse.services import gasca_single_report_runner_impl as runner


class _FakeLocator:
    def __init__(self, nodes):
        self.nodes = nodes

    def count(self):
        return len(self.nodes)

    def locator(self, selector):
        assert selector == runner.DATATABLES_EXCEL_OPTION_SELECTOR
        required_classes = {
            "dt-button",
            "buttons-excel",
            "buttons-html5",
        }
        matches = [
            node
            for node in self.nodes[0]["children"]
            if node["visible"]
            and node["tag"] == "a"
            and node.get("href") == "#"
            and required_classes.issubset(node["classes"])
        ]
        return _FakeLocator(matches)


class _FakePage:
    def __init__(self, children):
        self.menu = _FakeLocator([{"children": children}])

    def wait_for_selector(self, selector, *, state, timeout):
        assert selector == runner.DATATABLES_EXPORT_MENU_SELECTOR
        assert state == "visible"
        assert timeout == 10_000

    def locator(self, selector):
        assert selector == runner.DATATABLES_EXPORT_MENU_SELECTOR
        return self.menu


def _excel_link():
    return {
        "tag": "a",
        "classes": {
            "dt-button",
            "dropdown-item",
            "buttons-excel",
            "buttons-html5",
        },
        "href": "#",
        "text": "Excel",
        "visible": True,
    }


def test_resolver_opcion_excel_datatables_resolves_one_valid_link():
    resolved = runner._resolver_opcion_excel_datatables(
        page=_FakePage([_excel_link()]),
        nombre_reporte="Reporte de prueba",
    )

    assert resolved.count() == 1


def test_resolver_opcion_excel_datatables_fails_closed_with_zero_links():
    with pytest.raises(
        runner.GascaSingleReportRunnerError,
        match="0 candidatos Excel interactivos visibles",
    ):
        runner._resolver_opcion_excel_datatables(
            page=_FakePage([]),
            nombre_reporte="Reporte de prueba",
        )


def test_resolver_opcion_excel_datatables_fails_closed_with_two_links():
    with pytest.raises(
        runner.GascaSingleReportRunnerError,
        match="2 candidatos Excel interactivos visibles",
    ):
        runner._resolver_opcion_excel_datatables(
            page=_FakePage([_excel_link(), _excel_link()]),
            nombre_reporte="Reporte de prueba",
        )


def test_resolver_opcion_excel_datatables_ignores_ancestor_text():
    ancestor_with_excel_text = {
        "tag": "div",
        "classes": {"dropdown-menu"},
        "href": None,
        "text": "PDF Copy Excel CSV",
        "visible": True,
    }

    resolved = runner._resolver_opcion_excel_datatables(
        page=_FakePage([ancestor_with_excel_text, _excel_link()]),
        nombre_reporte="Reporte de prueba",
    )

    assert resolved.count() == 1
    assert resolved.nodes[0]["tag"] == "a"
