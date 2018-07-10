from .conftest import data_paths, load_poyo, load_pyyaml, load_ruamel, load_zyaml


def run(path):
    d1 = load_pyyaml(path)
    d2 = load_ruamel(path)
    d3 = load_zyaml(path)
    assert d1 == d2
    assert d3

    try:
        d4 = load_poyo(path)
        assert d1 == d4

    except Exception:
        pass


def test_data():
    for path in data_paths():
        run(path)
