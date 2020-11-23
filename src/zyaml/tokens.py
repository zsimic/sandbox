from zyaml.marshal import *


RE_COMMENT = re.compile(r"\s+#.*$")


class Token(object):
    """Represents one scanned token"""

    def __init__(self, scanner, linenum, indent, value=None):
        self.linenum = linenum
        self.indent = indent
        self.value = value
        self.stacked_cell = None

    def __repr__(self):
        result = "%s[%s,%s]" % (self.__class__.__name__, self.linenum, self.column)
        if self.value is not None:
            result = "%s %s" % (result, self.represented_value())

        return result

    @property
    def column(self):
        return self.indent + 1

    def represented_value(self):
        return str(self.value)

    def second_pass(self, scanner):
        """
        Args:
            scanner (zyaml.Scanner): Groom tokens like doc start/end, block start/end, validate indentation etc
        """
        for t in scanner.pass2_docstart(self):
            yield t

        yield self


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    pass


class DocumentStartToken(Token):
    def second_pass(self, scanner):
        for t in scanner.pass2_docend(self):
            yield t

        for t in scanner.pass2_docstart(self):
            yield t


class DocumentEndToken(Token):
    def second_pass(self, scanner):
        if not scanner.started_doc:
            raise ParseError("Document end without start")

        for t in scanner.pass2_docend(self):
            yield t


class DirectiveToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        if indent != 1:
            raise ParseError("Directive must not be indented")

        text = text[1:]
        m = RE_COMMENT.search(text)
        if m is not None:
            text = text[:m.start()]

        self.name, _, text = text.partition(" ")
        if not self.name:
            raise ParseError("Invalid directive")

        super(DirectiveToken, self).__init__(scanner, linenum, 0, text.strip())

    def represented_value(self):
        if self.value:
            return "%s %s" % (self.name, self.value)

        return self.name

    def second_pass(self, scanner):
        if scanner.started_doc:
            raise ParseError("Directives allowed only at document start")

        if self.name == "YAML":
            if scanner.yaml_directive:
                raise ParseError("Only one YAML directive is allowed")

            scanner.yaml_directive = self

        yield self


class FlowMapToken(Token):
    mnemonic = "{"

    def __init__(self, scanner, linenum, indent, text):
        scanner.push_flow_ender("}")
        super(FlowMapToken, self).__init__(scanner, linenum, indent, text)


class FlowSeqToken(Token):
    mnemonic = "["

    def __init__(self, scanner, linenum, indent, text):
        scanner.push_flow_ender("]")
        super(FlowSeqToken, self).__init__(scanner, linenum, indent, text)


class FlowEndToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        scanner.pop_flow_ender(text)
        super(FlowEndToken, self).__init__(scanner, linenum, indent, text)


class CommaToken(Token):
    pass


class ExplicitMapToken(Token):
    def second_pass(self, scanner):
        for t in scanner.pass2_docstart(self):
            yield t

        for t in scanner.mode.pass2_structure(self, BlockSeqToken):
            yield t

        yield KeyToken(scanner, self.linenum, self.indent)


class BlockEndToken(Token):
    pass


class BlockMapToken(Token):
    terminator = BlockEndToken
    mnemonic = ":"


class BlockSeqToken(Token):
    terminator = BlockEndToken
    mnemonic = "-"


class DashToken(Token):
    @property
    def column(self):
        return self.indent

    def second_pass(self, scanner):
        for t in scanner.pass2_docstart(self, pop_simple_key=True):
            yield t

        for t in scanner.mode.pass2_structure(self, BlockSeqToken):
            yield t

        yield self


class KeyToken(Token):
    pass


class ValueToken(Token):
    pass


class ColonToken(Token):
    def second_pass(self, scanner):
        for t in scanner.pass2_docstart(self, pop_simple_key=False):
            yield t

        cs = scanner.popped_simple_key()
        if scanner.is_block_mode:
            if cs is None:
                raise ParseError("Incomplete explicit mapping pair")

            for t in scanner.mode.pass2_structure(cs, BlockMapToken):
                yield t

        if cs is not None:
            yield KeyToken(scanner, cs.linenum, cs.indent)
            yield cs

        yield ValueToken(scanner, self.linenum, self.indent)


class TagToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        super(TagToken, self).__init__(scanner, linenum, indent, text)
        self.marshaller = Marshallers.get_marshaller(text)

    def marshalled(self, value):
        if self.marshaller is None:
            return value

        try:
            return self.marshaller(value)

        except ParseError as e:
            e.auto_complete(self)
            raise

        except ValueError:
            raise ParseError("'%s' can't be converted using %s" % (shortened(value), self.value), self)


class AnchorToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        super(AnchorToken, self).__init__(scanner, linenum, indent, text[1:])

    def represented_value(self):
        return "&%s" % self.value


class AliasToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        super(AliasToken, self).__init__(scanner, linenum, indent)
        self.anchor = text[1:]

    def __repr__(self):
        return "AliasToken[%s,%s] *%s" % (self.linenum, self.column, self.anchor)

    def resolved_value(self, clean):
        if not clean:
            raise ParseError("Alias should not have any properties")

        return self.value


class ScalarToken(Token):
    def __init__(self, scanner, linenum, indent, text, style=None):
        super(ScalarToken, self).__init__(scanner, linenum, indent, text)
        self.style = style
        self.multiline = False

    def represented_value(self):
        return represented_scalar(self.style, self.value)

    def resolved_value(self, clean):
        value = self.value
        if self.style is None and value is not None:
            value = value.strip()

        if clean and self.style is None:
            value = default_marshal(value)

        return value

    def append_line(self, text):
        if not self.value:
            self.value = text

        elif text:
            self.multiline = True
            self.value = "%s %s" % (self.value, text)

    def second_pass(self, scanner):
        for t in scanner.pass2_docstart(self, pop_simple_key=self.style is not None):
            yield t

        scanner.add_simple_key(self)
