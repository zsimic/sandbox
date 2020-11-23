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


def test_anchors():
    assert tokens("*foo") == "AliasToken[1,1] *foo"
    assert tokens("&foo") == "AnchorToken[1,1] &foo"
    assert tokens("!foo") == "TagToken[1,1] !foo"


def test_directives():
    assert tokens("%YAML") == "DirectiveToken[1,1] YAML"
    assert tokens("%YAML   1.2") == "DirectiveToken[1,1] YAML 1.2"
    assert tokens("%TAG") == "DirectiveToken[1,1] TAG"
    assert tokens("%TAG !yaml! tag:yaml.org,2002:") == "DirectiveToken[1,1] TAG !yaml! tag:yaml.org,2002:"
    assert tokens("%FOO bar") == "DirectiveToken[1,1] FOO bar"

    assert tokens(" %YAML") == "Directive must not be indented, line 1 column 1"
    assert tokens("% YAML") == "Invalid directive, line 1 column 1"
    assert tokens("%YAML foo # bar") == "DirectiveToken[1,1] YAML foo"


def test_document_markers():
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
        "DocumentEndToken[3,1]",
        "StreamEndToken[3,1]",
    ]
    assert tokens("foo\n...\n---\nbar", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[1,1] foo",
        "DocumentEndToken[2,1]",
        "DocumentStartToken[3,1]",
        "ScalarToken[4,1] bar",
        "DocumentEndToken[4,1]",
        "StreamEndToken[4,1]",
    ]
    assert tokens("---\nfoo\n...", ignored=[]) == [
        "StreamStartToken[1,1]",
        "DocumentStartToken[1,1]",
        "ScalarToken[2,1] foo",
        "DocumentEndToken[3,1]",
        "StreamEndToken[3,1]",
    ]


def test_flow_tokens():
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


def test_invalid():
    assert tokens(":") == "Incomplete explicit mapping pair"
    assert tokens(": foo") == "Incomplete explicit mapping pair"
    assert tokens("...") == "Document end without start"


def test_partial():
    assert tokens(",") == "ScalarToken[1,1] ,"
    assert tokens("'foo'") == "ScalarToken[1,2] 'foo'"
    assert tokens("a:") == [
        "BlockMapToken[1,1]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "BlockEndToken[1,1]"
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
    # Invalid document, but valid tokenization
    assert tokens("[a, -") == [
        'FlowSeqToken[1,1] [',
        'ScalarToken[1,2] a',
        'CommaToken[1,3] ,',
        'ScalarToken[1,5] -',
    ]
