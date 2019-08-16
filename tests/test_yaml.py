try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import zyaml


def test_scalar():
    assert zyaml.default_marshal(None) is None
    assert zyaml.default_marshal("") == ""
    assert zyaml.default_marshal("null") is None
    assert zyaml.default_marshal("True") is True
    assert zyaml.default_marshal("False") is False
    assert zyaml.default_marshal("0") == 0
    assert zyaml.default_marshal("0.1") == 0.1
    assert zyaml.default_marshal("0.1.1") == "0.1.1"
    assert zyaml.default_marshal("+135.057E+3") == 135057
    assert zyaml.default_marshal([1, 2]) == [1, 2]


def test_tokens():
    assert str(zyaml.Token(0, 0)) == "Token"
    assert str(zyaml.Token(1, 2)) == "Token[1,2]"
    assert str(zyaml.ScalarToken(2, 3, "test'ed")) == "ScalarToken[2,3] test'ed"
    assert str(zyaml.ScalarToken(2, 3, "test'ed", style="'")) == "ScalarToken[2,3] 'test'ed'"  # TODO: fix representation
    assert str(zyaml.ScalarToken(2, 3, "test'ed", style="|+")) == "ScalarToken[2,3] |+ test'ed"

    assert str(zyaml.Token(0, 0).represented_value()) == "None"

    key = zyaml.ScalarToken(1, 2, "test'ed\nsecond line", style='"')
    key.is_key = True
    assert str(key) == 'KeyToken[1,2] "test\'ed\nsecond line"'
    assert key.token_name() == "KeyToken"
    assert key.represented_value() == '"test\'ed\nsecond line"'

    assert len(list(zyaml.scan_tokens(""))) == 2
    tokens = list(zyaml.scan_tokens("--"))
    assert len(tokens) == 3
    assert str(tokens[1]) == "ScalarToken[1,1] --"

    assert zyaml.load("--") == "--"
    assert zyaml.load_string("--") == "--"

    s = StringIO()
    s.write("--")
    s.seek(0)
    assert zyaml.load(s) == "--"


def test_errors():
    e = zyaml.ParseError("testing")
    assert str(e) == "testing"
    e.line = 1
    assert str(e) == "testing, line 1 column None"
