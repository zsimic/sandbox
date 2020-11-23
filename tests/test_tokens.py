import zyaml


def tokens(text, ignored=None, stringify=str):
    if ignored is None:
        ignored = [zyaml.StreamStartToken, zyaml.DocumentStartToken, zyaml.DocumentEndToken, zyaml.StreamEndToken]

    try:
        tokens = []
        for t in zyaml.Scanner(text).tokens():
            if not ignored or t.__class__ not in ignored:
                if stringify:
                    t = stringify(t)

                tokens.append(t)

        if len(tokens) == 1:
            return tokens[0]

        return tokens

    except Exception as e:
        return str(e)


def test_directives():
    assert tokens("%YAML") == "DirectiveToken[1,1] YAML"
    assert tokens("%YAML   1.2") == "DirectiveToken[1,1] YAML 1.2"
    assert tokens("%TAG") == "DirectiveToken[1,1] TAG"
    assert tokens("%TAG !yaml! tag:yaml.org,2002:") == "DirectiveToken[1,1] TAG !yaml! tag:yaml.org,2002:"
    assert tokens("%FOO bar") == "DirectiveToken[1,1] FOO bar"

    assert tokens(" %YAML") == "Directive must not be indented, line 1 column 1"
    assert tokens("% YAML") == "Invalid directive, line 1 column 1"
    assert tokens("%YAML foo # bar") == "DirectiveToken[1,1] YAML foo"


def test_flow():
    assert tokens("-") == ["BlockSeqToken[1,2]", "DashToken[1,1]", "BlockEndToken[1,2]"]
    assert tokens("a: b") == [
        "BlockMapToken[1,1]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "ScalarToken[1,4] b",
        "BlockEndToken[1,1]",
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

    # Invalid document, but valid tokenization
    assert tokens("[a, -") == [
        'FlowSeqToken[1,1] [',
        'ScalarToken[1,2] a',
        'CommaToken[1,3] ,',
        'ScalarToken[1,5] -',
    ]

    # Including stream/document flow
    assert tokens("", ignored=[]) == [
        "StreamStartToken[1,1]",
        "StreamEndToken[1,1]"
    ]
    assert tokens("foo", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[1,1] foo",
        "DocumentEndToken[2,1]",
        "StreamEndToken[2,1]",
    ]
