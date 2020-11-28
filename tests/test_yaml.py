from zyaml.marshal import default_marshal, ParseError
from zyaml.tokens import yaml_lines


def test_errors():
    e = ParseError("testing")
    assert str(e) == "testing"
    e.column = 1
    assert str(e) == "testing, column 1"
    e.complete_coordinates(None, 21)
    assert str(e) == "testing, column 1"
    e.column = None
    e.complete_coordinates(5, 2)
    assert str(e) == "testing, line 5 column 2"


def test_lines():
    assert yaml_lines(["a", "b"]) == "a b"
    assert yaml_lines(["a", "", "b"]) == "a\nb"
    assert yaml_lines(["a", "", "", "b"]) == "a\n\nb"


def test_scalar():
    assert default_marshal(None) is None
    assert default_marshal("") == ""
    assert default_marshal("foo") == "foo"
    assert default_marshal("null") is None
    assert default_marshal("True") is True
    assert default_marshal("False") is False
    assert default_marshal("0") == 0
    assert default_marshal("10_000") == 10000
    assert default_marshal("0.1") == 0.1
    assert default_marshal("0.1.1") == "0.1.1"
    assert default_marshal("+135.057E+3") == 135057
    assert default_marshal("_") == "_"
