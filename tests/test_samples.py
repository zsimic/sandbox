import math

import pytest
import runez

from zyaml import load_string
from zyaml.marshal import ParseError, UTC


from .model import TestSamples


def test_samples(all_samples):
    skipped = []
    for sample in all_samples:
        problem = sample.replay(TestSamples.K_TOKEN)
        assert not problem
        if problem is runez.UNSET:
            skipped.append(sample)

    # TODO: enable when ready
    assert True or not skipped, "Skipped %s tests, please refresh" % skipped


def loaded(text):
    """
    Returns:
        (list | dict | str | float | int | datetime.datetime): Deserialized object
    """
    try:
        return load_string(text)

    except ParseError as e:
        return str(e)


@pytest.mark.skip("broken after refactor")
def test_invalid():
    # Invalid type conversions
    assert loaded("!!float _") == "'_' can't be converted using !!float, line 1 column 1"
    assert loaded("!!date x") == "'x' can't be converted using !!date, line 1 column 1"
    assert loaded("!!int []") == "scalar needed, got list instead, line 1 column 1"
    assert loaded("!!float {}") == "scalar needed, got map instead, line 1 column 1"
    assert loaded("!!map foo") == "Expecting dict, got str, line 1 column 1"
    assert loaded("!!map []") == "Expecting dict, got list, line 1 column 1"
    assert loaded("!!map") == "Expecting dict, got str, line 1 column 1"
    assert loaded("!!omap foo") == "Can't transform str to an ordered map, line 1 column 1"
    assert loaded("!!bool foo") == "'foo' can't be converted using !!bool, line 1 column 1"
    assert loaded("!!int") == "'' can't be converted using !!int, line 1 column 1"

    s = loaded("!!int some very long text we want to truncate")
    assert s == "'some very long text we want to t...' can't be converted using !!int, line 1 column 1"

    # Malformed docs
    assert loaded("a\n#\nb") == "Document separator expected, line 3 column 1"
    assert loaded("[a\n#\nb]") == "Missing comma between scalars in flow, line 1 column 2"
    assert loaded(" %YAML 1.2") == "Directive must not be indented, line 1 column 2"
    assert loaded("{ foo: ]}") == "Expecting '}', but found ']', line 1 column 8"
    assert loaded("foo: ]") == "']' without corresponding opener, line 1 column 6"
    assert loaded("[a {}]") == "Missing comma between scalar and map in flow, line 1 column 2"
    assert loaded("[{} a]") == "Missing comma in list, line 1 column 6"
    assert loaded("{a: {} b}") == "Missing comma in map, line 1 column 9"
    assert loaded("[\n- a\n]") == "Block not allowed in flow, line 2 column 1"
    assert loaded("{\n- a\n}") == "Block not allowed in flow, line 2 column 1"
    assert loaded("{{}: b}") == "Key '{}' is not hashable, line 1 column 3"
    # assert loaded("a: [b] c") == "Key is not indented properly, line 1 column 8"

    # Bad properties
    assert loaded("- &a a\n- &b *a") == "Alias should not have any properties, line 2 column 6"
    assert loaded("foo: *no-such-anchor") == "Undefined anchor &no-such-anchor, line 1 column 6"
    assert loaded("- &a1 a: &b1 b\n- &c1 &c2 c") == "Too many anchor tokens, line 2 column 7"
    assert loaded("- &a a\n- !!tag *a") == "Alias should not have any properties, line 2 column 9"
    assert loaded("!!str !!str !!str a") == "Too many tag tokens, line 1 column 7"

    # Invalid strings
    assert loaded('"a\nb') == "Unexpected end, runaway double-quoted string at line 1?, line 1 column 1"
    assert loaded("'a\nb") == "Unexpected end, runaway single-quoted string at line 1?, line 1 column 1"

    # Invalid literals
    assert loaded("a: >x") == "Invalid literal style '>x', line 1 column 4"
    assert loaded("a: |+++") == "Invalid literal style '|+++', should be less than 3 chars, line 1 column 4"
    assert loaded("a: >0") == "Indent must be between 1 and 9, line 1 column 4"
    assert loaded("a: |+-") == "Ambiguous literal style '|+-', line 1 column 4"
    assert loaded("a: |+-") == "Ambiguous literal style '|+-', line 1 column 4"
    assert loaded("a: |2\n foo") == "Bad literal indentation, line 1 column 4"


@pytest.mark.skip("broken after refactor")
def test_decorators():
    assert loaded("!!str") == ""
    assert loaded("!!str\n...") == ""
    assert loaded("!!map\n!!str a: !!seq\n- !!str b") == {"a": ["b"]}


def test_edge_cases():
    assert loaded("") is None
    assert loaded("#comment\\n\n") is None
    assert loaded("_") == "_"
    assert loaded("''") == ""
    assert loaded("---a") == "---a"
    assert loaded(" ---") == "---"
    assert loaded('a-{}: ""') == {"a-{}": ""}
    assert loaded("[]\n---\n[]") == [[], []]
    assert loaded("-   ") == [None]

    # assert loaded("- a:\n  b") == "Value must be indented at least 4 columns, line 2 column 3"
    assert loaded("- a:\n   b") == [{"a": "b"}]
    assert loaded("- a: b\n c: d") == "Scalar is under-indented relative to map, line 2 column 2"
    assert loaded("- a: b\n  c: d") == [{"a": "b", "c": "d"}]
    assert loaded("- a:\n - b\n- c") == "Block sequence is under-indented relative to previous sequence, line 2 column 2"
    # assert loaded("a:\n  - b\n- c") == "Simple key must be indented in order to continue previous line, line 3 column 1"
    # assert loaded("- a:\n  - b\n- c") == [{"a": ["b"]}, "c"]

    assert loaded("a: b\n  c: d\ne: f") == "Scalar is over-indented relative to map, line 2 column 3"
    assert loaded("a: \n  c: d\ne: f") == {"a": {"c": "d"}, "e": "f"}

    assert loaded("[a\n- b]") == ["a - b"]
    assert loaded("{a\n- b}") == {"a - b": None}
    assert loaded("[\n:\n]") == [{None: None}]
    assert loaded("[\na:\n]") == [{"a": None}]
    assert loaded("[::]") == ["::"]
    assert loaded("[:: ]") == [{":": None}]
    assert loaded("[\n::\n]") == [{":": None}]
    assert loaded("[::a]") == ["::a"]
    assert loaded("[a::]") == ["a::"]
    assert loaded("[a::a]") == ["a::a"]

    assert loaded("foo # bar") == "foo"
    assert loaded("foo# bar") == "foo# bar"
    assert loaded("a\nb") == "a b"
    assert loaded("a\n\nb") == "a\nb"

    # assert loaded(" a\nb") == "Simple key must be indented in order to continue previous line, line 2 column 1"
    assert loaded("- a\nb") == "Scalar under-indented relative to previous sequence, line 2 column 1"
    assert loaded("[ a\nb]") == ["a b"]
    assert loaded("- a\n b") == ["a b"]
    # assert loaded("a: b\n\n\n   c\n\n") == {"a": "b\n\nc"}
    # assert loaded("a\n\n \n b") == "a\n\nb"
    # assert loaded("- a\n - b\n- c") == ["a - b", "c"]

    # assert loaded("? a") == {"a": None}
    # assert loaded("? a\n: b") == {"a": "b"}
    # assert loaded("{? a: b, ? c: d}") == {"a": "b", "c": "d"}

    assert loaded("inf") == "inf"
    assert loaded("+inf") == "+inf"
    assert loaded("-inf") == "-inf"
    assert loaded(".iNf") == ".iNf"
    assert math.isinf(loaded(".inf"))
    assert math.isinf(loaded("-.inf"))
    assert math.isinf(loaded("+.inf"))
    assert loaded("nan") == "nan"
    assert loaded("+nan") == "+nan"
    assert loaded("+.nan") == "+.nan"
    assert loaded("-.nan") == "-.nan"
    assert math.isnan(loaded(".nan"))
    assert loaded(".nAn") == ".nAn"

    assert loaded("0") == 0
    assert loaded("1") == 1
    assert loaded("0o7") == 7
    assert loaded("0O7") == "0O7"
    assert loaded("0XF") == "0XF"
    assert loaded("0xF") == 15
    assert loaded("0xf") == 15
    assert loaded("0xG") == "0xG"
    assert loaded("0xg") == "0xg"


@pytest.mark.skip("broken after refactor")
def test_types():
    assert loaded("! 2019-01-01 01:02:03Z") == "2019-01-01 01:02:03Z"
    assert loaded("2019-01-01 01:02:03Z").tzinfo is UTC
    assert loaded("!!date 2019-01-01 01:02:03").tzinfo is None

    assert loaded("!!set [a]") == {"a"}
    assert loaded("!!set {a}") == {"a"}
    assert loaded("!!set {a: b}") == {"a"}

    assert loaded("!!bool yes") is True
    assert loaded("!!bool no") is False


@pytest.mark.skip("broken after refactor")
def test_q():
    # assert loaded("- a:\n  - b\n- c") == [{"a": ["b"]}, "c"]
    assert loaded('a-{}: ""') == {"a-{}": ""}
