from zyaml import tokens_from_string
from zyaml.scanner import Scanner
from zyaml.tokens import DocumentEndToken, DocumentStartToken, StreamEndToken, StreamStartToken


def tokens(content=None, ignored=None, stringify=str, generator=None):
    if ignored is None:
        ignored = [StreamStartToken, DocumentStartToken, DocumentEndToken, StreamEndToken]

    try:
        tokens = []
        if generator is None:
            generator = tokens_from_string(content)

        for t in generator:
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


def test_block_tokens():
    # TODO: remove, only for debugging
    x = tokens("foo.bar:\n- a: x\n  b:\n   b2: y\n\n\n  c:\n   c2: z")
    assert isinstance(x, list)


def test_decorators():
    assert tokens("!!str a: b") == [
        "BlockMapToken[1,7]",
        "KeyToken[1,7]",
        "TagToken[1,1] !!str",
        "ScalarToken[1,7] a",
        "ValueToken[1,8]",
        "ScalarToken[1,10] b",
        "BlockEndToken[1,7]",
    ]


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
    assert tokens("''") == "ScalarToken[1,2] ''"
    assert tokens("a{x") == "ScalarToken[1,1] a{x"
    assert tokens("\n\na::#b") == "ScalarToken[3,1] a::#b"
    assert tokens("--- a") == "ScalarToken[1,5] a"
    assert tokens("...\ta") == "ScalarToken[1,5] a"
    assert tokens("---a") == "ScalarToken[1,1] ---a"
    assert tokens("...a") == "ScalarToken[1,1] ...a"
    assert tokens("-  a\n b") == [
        "BlockSeqToken[1,1]",
        "DashToken[1,1]",
        "ScalarToken[1,4] a b",
        "BlockEndToken[2,1]",
    ]
    assert tokens("- a: b\n\n#") == [
        "BlockSeqToken[1,1]",
        "DashToken[1,1]",
        "BlockMapToken[1,3]",
        "KeyToken[1,3]",
        "ScalarToken[1,3] a",
        "ValueToken[1,4]",
        "ScalarToken[1,6] b",
        "BlockEndToken[2,3]",
        "BlockEndToken[2,1]",
    ]
    assert tokens("a:  b\n c\nx: y") == [
        "BlockMapToken[1,1]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "ScalarToken[1,5] b c",
        "KeyToken[3,1]",
        "ScalarToken[3,1] x",
        "ValueToken[3,2]",
        "ScalarToken[3,4] y",
        "BlockEndToken[3,1]",
    ]
    assert tokens("a: {\n - b: c}") == [
        "BlockMapToken[1,1]",
        "KeyToken[1,1]",
        "ScalarToken[1,1] a",
        "ValueToken[1,2]",
        "FlowMapToken[1,4] {",
        "KeyToken[2,2]",
        "ScalarToken[2,2] - b",
        "ValueToken[2,5]",
        "ScalarToken[2,7] c",
        "FlowEndToken[2,8] }",
        "BlockEndToken[2,1]",
    ]

    s = Scanner(["a # commented item", "# comment line"], comments=True)
    assert str(s) == "block - "
    assert str(s.flow_scanner) == "flow - "
    assert tokens(generator=s.tokens()) == [
        "CommentToken[1,1] a # commented item",
        "CommentToken[2,1] # comment line",
    ]


def test_flow_tokens():
    assert tokens("-") == ["BlockSeqToken[1,1]", "DashToken[1,1]", "BlockEndToken[1,1]"]
    assert tokens(" a: b") == [
        "BlockMapToken[1,2]",
        "KeyToken[1,2]",
        "ScalarToken[1,2] a",
        "ValueToken[1,3]",
        "ScalarToken[1,5] b",
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
        "FlowSeqToken[1,1] [",
        "ScalarToken[1,2] a",
        "CommaToken[1,3] ,",
        "ScalarToken[1,5] b",
        "FlowEndToken[1,6] ]",
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
    assert tokens(":") == "Incomplete explicit mapping pair, line 1 column 1"
    assert tokens(": foo") == "Incomplete explicit mapping pair, line 1 column 1"
    assert tokens("foo: @b") == "Character '@' is reserved, line 1 column 6"
    assert tokens("a: : b") == "Nested mappings are not allowed in compact mappings, line 1 column 4"
    assert tokens("a\n#\nb") == "Trailing content after comment, line 3 column 1"
    assert tokens("- a\nb") == "Scalar under-indented relative to previous sequence, line 2 column 1"
    assert tokens("-  a: x\n b: y") == "Scalar is under-indented relative to map, line 2 column 2"
    assert tokens("a: b\n c: d") == "Scalar is over-indented relative to map, line 2 column 2"
    assert tokens("a: b\n cc: d") == "Scalar is over-indented relative to map, line 2 column 2"
    assert tokens("  a: b\n c: d") == "Document contains trailing content, line 2 column 2"
    assert tokens("[a, -") == "Expected flow map end, line 1 column 5"
    assert tokens("a: [}") == "Unexpected flow closing character '}', line 1 column 5"


def test_partial():
    assert tokens(",") == "ScalarToken[1,1] ,"
    assert tokens("'foo'") == "ScalarToken[1,2] 'foo'"
    assert tokens("a:") == ["BlockMapToken[1,1]", "KeyToken[1,1]", "ScalarToken[1,1] a", "ValueToken[1,2]", "BlockEndToken[1,1]"]
    assert tokens("[,]") == [
        "FlowSeqToken[1,1] [",
        "CommaToken[1,2] ,",
        "FlowEndToken[1,3] ]",
    ]
    assert tokens("", ignored=[]) == ["StreamStartToken[1,1]", "StreamEndToken[1,1]"]
    assert tokens("# Comment only", ignored=[]) == ["StreamStartToken[1,1]", "StreamEndToken[1,1]"]
