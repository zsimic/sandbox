import json

import zyaml

from .conftest import json_sanitized, ZyamlImplementation


def test_samples(all_samples):
    skipped = 0
    impl = ZyamlImplementation()
    for sample in all_samples:
        result = impl.load(sample, stacktrace=False)
        payload = result.json_payload()
        expected = sample.expected
        payload = json_sanitized(payload)
        expected = json_sanitized(expected)
        if expected is None:
            skipped += 1
            continue
        # jsonify to avoid diffs on inf/nan floats
        jpayload = json.dumps(payload, sort_keys=True, indent=2)
        jexpected = json.dumps(expected, sort_keys=True, indent=2)
        assert jpayload == jexpected, "Failed sample %s" % sample

    assert skipped == 0, "Skipped %s tests, please refresh" % skipped


def loaded(text):
    try:
        return zyaml.load_string(text)
    except zyaml.ParseError as e:
        return str(e)


def test_invalid():
    # Invalid type conversions
    assert loaded("!!float _") == "'_' can't be converted using !!float, line 1 column 1"
    assert loaded("!!date x") == "'x' can't be converted using !!date, line 1 column 1"

    # Invalid docs
    assert loaded("a\n#\nb") == "Document separator expected, line 3 column 1"

    # Bad properties
    assert loaded("- &a a\n- &b *a") == "Alias should not have any properties, line 2 column 6"
    assert loaded("foo: *no-such-anchor") == "Undefined anchor &no-such-anchor, line 1 column 6"
    assert loaded("- &a1 a: &b1 b\n- &c1 &c2 c") == "Too many anchor tokens, line 2 column 7"
    assert loaded("- &a a\n- !!tag *a") == "Alias should not have any properties, line 2 column 9"
    assert loaded("!!str !!str !!str a") == "Too many tag tokens, line 1 column 7"

    # Malformed docs
    assert loaded(" %YAML 1.2") == "Directive must not be indented, line 1 column 1"
    assert loaded("{ foo: ]}") == "Expecting ']', but found '}', line 1 column 8"
    assert loaded("foo: ]") == "']' without corresponding opener, line 1 column 6"
    assert loaded("[a {}]") == "Missing comma between scalar and entry in flow, line 1 column 2"

    # assert loaded("") == ""


def test_edge_cases():
    assert loaded("_") == "_"
