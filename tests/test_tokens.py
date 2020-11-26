try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import zyaml


def tokens(text, ignored=None, stringify=str):
    if ignored is None:
        ignored = [zyaml.StreamStartToken, zyaml.DocumentStartToken, zyaml.DocumentEndToken, zyaml.StreamEndToken]

    try:
        tokens = []
        for t in zyaml.tokens_from_string(text):
            if not ignored or t.__class__ not in ignored:
                if stringify:
                    t = stringify(t)

                tokens.append(t)

        if len(tokens) == 1:
            return tokens[0]

        return tokens

    except Exception as e:
        return str(e)


def test_anchors():
    assert tokens("*foo") == "AliasToken[1,1] *foo"
    assert tokens("&foo") == "AnchorToken[1,1] &foo"
    assert tokens("!foo") == "TagToken[1,1] !foo"


def test_directives():
    assert tokens("%YAML") == "DirectiveToken[1,1] YAML"
    assert tokens("%  YAML   1.2") == "DirectiveToken[1,1] YAML 1.2"
    assert tokens("%TAG") == "DirectiveToken[1,1] TAG"
    assert tokens("%TAG !yaml! tag:yaml.org,2002:") == "DirectiveToken[1,1] TAG !yaml! tag:yaml.org,2002:"
    assert tokens("%FOO bar") == "DirectiveToken[1,1] FOO bar"

    assert tokens(" %YAML") == "ScalarToken[1,2] %YAML"  # Not a directive, lines doesn't start with %
    assert tokens("% YAML") == "DirectiveToken[1,1] YAML"
    assert tokens("% YAML   foo  #  bar") == "DirectiveToken[1,1] YAML foo"


def test_document_markers():
    assert tokens("...\nfoo") == "ScalarToken[2,1] foo"
    assert tokens("---\n...", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "DocumentEndToken[2,1]",
        "StreamEndToken[2,1]",
    ]
    assert tokens("foo", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[1,1] foo",
        "DocumentEndToken[2,1]",
        "StreamEndToken[2,1]",
    ]
    assert tokens("foo\n---\nbar", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[1,1] foo",
        "DocumentEndToken[3,1]",
        "DocumentStartToken[2,1]",
        "ScalarToken[3,1] bar",
        "DocumentEndToken[4,1]",
        "StreamEndToken[4,1]",
    ]
    assert tokens("foo\n...\n---\nbar", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[1,1] foo",
        "DocumentEndToken[2,1]",
        "DocumentStartToken[3,1]",
        "ScalarToken[4,1] bar",
        "DocumentEndToken[5,1]",
        "StreamEndToken[5,1]",
    ]
    assert tokens("---\nfoo\n...", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[2,1] foo",
        "DocumentEndToken[3,1]",
        "StreamEndToken[3,1]",
    ]


def test_edge_cases():
    assert tokens(":") == [
        "BlockMapToken[1,1]",
        "ValueToken[1,1]",
        "BlockEndToken[1,1]",
    ]
    assert tokens(": foo") == [
        "BlockMapToken[1,1]",
        "ValueToken[1,1]",
        "ScalarToken[1,3] foo",
        "BlockEndToken[1,1]",
    ]
    assert tokens("a\n#\nb") == [
        "ScalarToken[1,1] a",
        "ScalarToken[3,1] b",
    ]
    assert tokens("a: {\n - b: c}") == [
        "BlockMapToken[1,2]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "FlowMapToken[1,4] {",
        "KeyToken[2,2]",
        "ScalarToken[2,2] - b",
        "ValueToken[2,5]",
        "ScalarToken[2,7] c",
        "FlowEndToken[2,8] }",
        "BlockEndToken[2,2]",
    ]


def test_flow_tokens():
    assert tokens("-") == [
        "BlockSeqToken[1,2]",
        "DashToken[1,1]",
        "BlockEndToken[1,2]"
    ]
    assert tokens("a: b") == [
        "BlockMapToken[1,2]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "ScalarToken[1,4] b",
        "BlockEndToken[1,2]",
    ]
    assert tokens("{a: b}") == [
        "FlowMapToken[1,1] {",
        "KeyToken[1,2]",
        "ScalarToken[1,2] a",
        "ValueToken[1,3]",
        "ScalarToken[1,5] b",
        "FlowEndToken[1,6] }",
    ]
    assert tokens("[a, b]") == [
        'FlowSeqToken[1,1] [',
        'ScalarToken[1,2] a',
        'CommaToken[1,3] ,',
        'ScalarToken[1,5] b',
        'FlowEndToken[1,6] ]',
    ]
    assert tokens("[a, {b: c}, d]") == [
        "FlowSeqToken[1,1] [",
        "ScalarToken[1,2] a",
        "CommaToken[1,3] ,",
        "FlowMapToken[1,5] {",
        "KeyToken[1,6]",
        "ScalarToken[1,6] b",
        "ValueToken[1,7]",
        "ScalarToken[1,9] c",
        "FlowEndToken[1,10] }",
        "CommaToken[1,11] ,",
        "ScalarToken[1,13] d",
        "FlowEndToken[1,14] ]",
    ]


def test_invalid():
    assert tokens("[a, -") == "Expected flow map end, line 1 column 5"


def test_partial():
    assert tokens(",") == "ScalarToken[1,1] ,"
    assert tokens("'foo'") == "ScalarToken[1,2] 'foo'"
    assert tokens("a:") == [
        "BlockMapToken[1,2]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "BlockEndToken[1,2]"
    ]
    assert tokens("[,]") == [
        "FlowSeqToken[1,1] [",
        "CommaToken[1,2] ,",
        "FlowEndToken[1,3] ]",
    ]
    assert tokens("", ignored=[]) == [
        "StreamStartToken[1,1]",
        "StreamEndToken[1,1]"
    ]
    assert tokens("# Comment only", ignored=[]) == [
        "StreamStartToken[1,1]",
        "StreamEndToken[1,1]"
    ]


def test_stream():
    s = StringIO()
    s.write("--")
    s.seek(0)
    x = list(zyaml.tokens_from_stream(s))
    assert len(x) == 5
    assert str(x[2]) == "ScalarToken[1,1] --"
