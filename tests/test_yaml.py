import zyaml
import zyaml.marshal


def test_scalar():
    assert zyaml.default_marshal(None) is None
    assert zyaml.default_marshal("") == ""
    assert zyaml.default_marshal("foo") == "foo"
    assert zyaml.default_marshal("null") is None
    assert zyaml.default_marshal("True") is True
    assert zyaml.default_marshal("False") is False
    assert zyaml.default_marshal("0") == 0
    assert zyaml.default_marshal("10_000") == 10000
    assert zyaml.default_marshal("0.1") == 0.1
    assert zyaml.default_marshal("0.1.1") == "0.1.1"
    assert zyaml.default_marshal("+135.057E+3") == 135057
    assert zyaml.default_marshal("_") == "_"


def test_errors():
    e = zyaml.ParseError("testing")
    assert str(e) == "testing"
    e.column = 1
    assert str(e) == "testing, column 1"
    e.complete_coordinates(None, 21)
    assert str(e) == "testing, column 1"
    e.column = None
    e.complete_coordinates(5, 2)
    assert str(e) == "testing, line 5 column 2"
