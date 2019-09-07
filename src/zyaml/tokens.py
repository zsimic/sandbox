from zyaml.marshal import *


RE_COMMENT = re.compile(r"\s+#.*$")


class Token(object):
    """Scanned token, visitor pattern is used for parsing"""

    def __init__(self, scanner, linenum, indent, value=None):
        self.scanner = scanner
        self.linenum = linenum
        self.indent = indent
        self.value = value

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

    def second_pass(self, stack):
        """
        :param TokenStack stack: Groom tokens like doc start/end, block start/end, validate indentation etc
        """
        for t in stack.doc_start(self):
            yield t
        yield self


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    pass


class DocumentStartToken(Token):
    def second_pass(self, stack):
        for t in stack.doc_end(self):
            yield t
        for t in stack.doc_start(self):
            yield t


class DocumentEndToken(Token):
    def second_pass(self, stack):
        if not stack.started_doc:
            raise ParseError("Document end without start")
        for t in stack.doc_end(self):
            yield t


class DirectiveToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        m = RE_COMMENT.search(text)
        if m is not None:
            text = text[:m.start()]
        if text.startswith("%YAML"):
            self.name = "%YAML"
            text = text[5:].strip()
        elif text.startswith("%TAG"):
            self.name = "%TAG"
            text = text[4:].strip()
        else:
            self.name, _, text = text.partition(" ")
        super(DirectiveToken, self).__init__(scanner, linenum, indent, text.strip())

    def represented_value(self):
        return "%s %s" % (self.name, self.value)

    def second_pass(self, stack):
        yield self


class FlowMapToken(Token):
    def __init__(self, scanner, linenum, indent, text):
        scanner.push_flow_ender("}")
        super(FlowMapToken, self).__init__(scanner, linenum, indent, text)


class FlowSeqToken(Token):
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
    pass


class BlockMapToken(Token):
    pass


class BlockSeqToken(Token):
    pass


class BlockEndToken(Token):
    pass


class DashToken(Token):
    @property
    def column(self):
        return self.indent

    def second_pass(self, stack):
        for t in stack.doc_start(self):
            yield t
        for t in stack.pop_until(self.linenum, self.indent):
            yield t
        if stack.nesting_level == self.indent:
            yield self
            return
        block = BlockSeqToken(self.scanner, self.linenum, self.indent)
        stack.add_structure(block)
        yield block
        yield self


class ColonToken(Token):
    pass


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

    def represented_value(self):
        return "*%s" % self.anchor

    def resolved_value(self, clean):
        if not clean:
            raise ParseError("Alias should not have any properties")
        return self.value


class ScalarToken(Token):
    def __init__(self, scanner, linenum, indent, text, style=None):
        super(ScalarToken, self).__init__(scanner, linenum, indent, text)
        self.style = style

    def represented_value(self):
        if self.style == "'":
            return "'%s'" % self.value.replace("'", "''").replace("\n", "\\n")
        if self.style is None or self.style == '"':
            return double_quoted(self.value)
        return "%s %s" % (self.style, double_quoted(self.value))

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
            self.value = "%s %s" % (self.value, text)

    def second_pass(self, stack):
        for t in stack.doc_start(self):
            yield t
        stack.add_scalar(self)
        yield self
