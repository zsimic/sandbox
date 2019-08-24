try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import zyaml


def test_scalar():
    assert zyaml.default_marshal(None) is None
    assert zyaml.default_marshal("") == ""
    assert zyaml.default_marshal("\n") == ""
    assert zyaml.default_marshal("\nfoo\n") == "foo"
    assert zyaml.default_marshal("null\n") is None
    assert zyaml.default_marshal("True") is True
    assert zyaml.default_marshal("False\n") is False
    assert zyaml.default_marshal("0") == 0
    assert zyaml.default_marshal("10_000") == 10000
    assert zyaml.default_marshal("0.1") == 0.1
    assert zyaml.default_marshal("0.1.1\n") == "0.1.1"
    assert zyaml.default_marshal("+135.057E+3") == 135057
    assert zyaml.default_marshal("_") == "_"


def test_tokens():
    assert str(zyaml.Token(0, 0)) == "Token[0,1]"
    assert str(zyaml.Token(1, 2)) == "Token[1,3]"
    assert str(zyaml.DirectiveToken(1, 0, "")) == "DirectiveToken[1,1]  "
    assert str(zyaml.DirectiveToken(1, 0, "%foo bar")) == "DirectiveToken[1,1] %foo bar"
    assert str(zyaml.AnchorToken(1, 0, "&foo")) == "AnchorToken[1,1] &foo"
    alias = zyaml.AliasToken(1, 0, "*foo")
    assert str(alias) == "AliasToken[1,1]"
    alias.value = ""
    assert str(alias) == "AliasToken[1,1] *foo"
    assert str(zyaml.ScalarToken(2, 3, "test'ed")) == "ScalarToken[2,4] test'ed"
    assert str(zyaml.ScalarToken(2, 3, "test'ed", style="'")) == "ScalarToken[2,4] 'test''ed'"
    assert str(zyaml.ScalarToken(2, 3, "test'ed", style="|+")) == "ScalarToken[2,4] |+ test'ed"
    assert str(zyaml.ScalarToken(1, 0, 'tested', style='"')) == 'ScalarToken[1,1] "tested"'

    s = zyaml.ScalarToken(1, 0, None)
    assert str(s) == "ScalarToken[1,1]"
    s.append_text("foo")
    assert str(s) == "ScalarToken[1,1] foo"
    s.append_text("foo\n")
    assert str(s) == "ScalarToken[1,1] foo foo\n"
    s.append_text("foo")
    assert str(s) == "ScalarToken[1,1] foo foo\nfoo"

    assert str(zyaml.Token(0, 0).represented_value()) == "None"

    key = zyaml.KeyToken(1, 2)
    assert str(key) == "KeyToken[1,3]"
    assert key.represented_value() == "None"

    s = zyaml.Scanner("")
    assert str(s) == "block mode"
    assert len(list(s)) == 2
    tokens = list(zyaml.Scanner("--"))
    assert len(tokens) == 3
    assert str(tokens[1]) == "ScalarToken[1,1] --"

    assert zyaml.load("--") == "--"
    assert zyaml.load_string("--") == "--"

    s = StringIO()
    s.write("--")
    s.seek(0)
    assert zyaml.load(s) == "--"


def test_decoration():
    root = zyaml.RootNode()
    assert str(root) == "[0,0]  /"


def test_errors():
    e = zyaml.ParseError("testing")
    assert str(e) == "testing"
    e.indent = 1
    assert str(e) == "testing, line None column 2"


def test_comments():
    assert zyaml.de_commented("") == ""
    assert zyaml.de_commented(" ") == " "
    assert zyaml.de_commented("# foo") == "# foo"
    assert zyaml.de_commented(" foo  # bar") == " foo"
    assert zyaml.de_commented(" foo ") == " foo "
    assert zyaml.de_commented("foo#bar") == "foo#bar"
    assert zyaml.de_commented("foo#bar   #baz") == "foo#bar"
    assert zyaml.de_commented("foo#bar   #baz #baz") == "foo#bar"
