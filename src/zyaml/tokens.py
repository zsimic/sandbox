from zyaml.marshal import *


RE_COMMENT = re.compile(r"\s+#.*$")


def yaml_lines(lines, text=None, indent=None, folded=None, keep=False, continuations=False):
    """
    Args:
        lines (list): Lines to concatenate together
        text (str | None): Initial line (optional)
        indent (int | None): If not None, we're doing a block scalar
        folded (bool): If True, we're doing a folded block scalar (marked by `>`)
        keep (bool): If True, keep trailing newlines
        continuations (bool): If True, respect end-of-line continuations (marked by `\\`)

    Returns:
        (str): Concatenated string, with yaml's weird convention
    """
    empty = 0
    was_over_indented = False
    for line in lines:
        if indent is not None:
            line = line[indent:]
            if folded is True and line:
                if line[0] in " \t":
                    if not was_over_indented:
                        empty = empty + 1
                        was_over_indented = True

                elif was_over_indented:
                    was_over_indented = False

        if text is None:
            text = line

        elif folded is not None and not text:
            text = "\n%s" % line

        elif not line:
            empty = empty + 1

        elif continuations and text[-1:] == "\\" and text[-2:] != "\\\\":
            text = "".join((text[:-1], "\n" * empty, line))
            empty = 0

        elif empty > 0:
            text = "".join((text, "\n" * empty, "\n" if folded is False else "", line))
            empty = 1 if was_over_indented else 0

        else:
            text = "".join((text, "\n" if folded is False else " ", line))

    if empty and keep:
        if indent is None:
            if empty == 1:
                text = "%s " % text

        if was_over_indented or continuations or indent is None:
            empty = empty - 1

        text = "".join((text, "\n" * empty))

    return text


class Token(object):
    """Represents one scanned token"""

    auto_start_doc = True  # Does this token imply DocumentStartToken?
    auto_filler = None  # Optional auto-filler (generator called with one argument: the current scanner)
    pop_simple_key = True  # Should pending simple_key be auto-popped by this token?

    def __init__(self, linenum, indent, value=None):
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
        return unicode_escaped(self.value)


class CommentToken(Token):
    pass


class StreamStartToken(Token):

    auto_start_doc = False


class StreamEndToken(Token):

    auto_start_doc = False


class DocumentStartToken(Token):

    auto_start_doc = False

    def auto_filler(self, scanner):
        for t in scanner.auto_pop_all(self):
            yield t

        scanner.started_doc = True
        yield self


class DocumentEndToken(Token):

    auto_start_doc = False

    def auto_filler(self, scanner):
        for t in scanner.auto_pop_all(self):
            yield t

        yield self


class DirectiveToken(Token):

    auto_start_doc = False

    def __init__(self, linenum, indent, text):
        if indent != 1:
            raise ParseError("Directive must not be indented")

        text = text[1:]
        m = RE_COMMENT.search(text)
        if m is not None:
            text = text[:m.start()]

        self.name, _, text = text.strip().partition(" ")
        if not self.name:
            raise ParseError("Invalid directive")

        super(DirectiveToken, self).__init__(linenum, 0, text.strip())

    def represented_value(self):
        if self.value:
            return "%s %s" % (self.name, unicode_escaped(self.value))

        return self.name

    def auto_filler(self, scanner):
        if scanner.started_doc:
            raise ParseError("Directives allowed only at document start")

        if self.name == "YAML":
            if scanner.yaml_directive:
                raise ParseError("Only one YAML directive is allowed")

            scanner.yaml_directive = self

        yield self


class FlowMapToken(Token):

    def auto_filler(self, scanner):
        for t in scanner.auto_push_flow(self):
            yield t


class FlowSeqToken(Token):

    def auto_filler(self, scanner):
        for t in scanner.auto_push_flow(self):
            yield t


class FlowEndToken(Token):

    def auto_filler(self, scanner):
        for t in scanner.auto_pop(self):
            yield t


class CommaToken(Token):

    pop_simple_key = False

    def auto_filler(self, scanner):
        sk = scanner.popped_simple_key()
        if sk is not None:
            yield sk

        yield self


class BlockMapToken(Token):
    pass


class BlockSeqToken(Token):
    pass


class BlockEndToken(Token):
    pass


class ExplicitMapToken(Token):

    def auto_filler(self, scanner):
        for t in scanner.auto_push_block(self, BlockMapToken):
            yield t

        yield KeyToken(self.linenum, self.indent)


class DashToken(Token):

    @property
    def column(self):
        return self.indent

    def auto_filler(self, scanner):
        for t in scanner.auto_push_block(self, BlockSeqToken):
            yield t

        yield self


class KeyToken(Token):
    pass


class ValueToken(Token):
    pass


class ColonToken(Token):

    pop_simple_key = False

    def auto_filler(self, scanner):
        if not scanner.is_within_map_block():
            if scanner.mode is scanner.block_scanner:
                for t in scanner.auto_push_block(self, BlockMapToken):
                    yield t

        sk = scanner.popped_simple_key()
        if sk is not None:
            if sk.multiline and sk.style is None:
                raise ParseError("Simple keys must be single line")

            yield KeyToken(sk.linenum, sk.indent)
            yield sk

        yield ValueToken(self.linenum, self.indent)


class TagToken(Token):
    def __init__(self, linenum, indent, text):
        super(TagToken, self).__init__(linenum, indent, text)
        self.marshaller = Marshallers.get_marshaller(text)

    def marshalled(self, value):
        if self.marshaller is None:
            return value

        try:
            return self.marshaller(value)

        except ValueError:
            raise ParseError("'%s' can't be converted using %s" % (shortened(value), self.value))


class AnchorToken(Token):
    def __init__(self, linenum, indent, text):
        super(AnchorToken, self).__init__(linenum, indent, text[1:])

    def represented_value(self):
        return "&%s" % unicode_escaped(self.value)


class AliasToken(Token):
    def __init__(self, linenum, indent, text):
        super(AliasToken, self).__init__(linenum, indent)
        self.anchor = text[1:]

    def __repr__(self):
        return "AliasToken[%s,%s] *%s" % (self.linenum, self.column, self.anchor)

    def resolved_value(self, clean):
        if not clean:
            raise ParseError("Alias should not have any properties")

        return self.value


class ScalarToken(Token):

    pop_simple_key = False

    def __init__(self, linenum, indent, text, style=None):
        super(ScalarToken, self).__init__(linenum, indent, text)
        self.style = style
        self.multiline = None
        self.has_comment = False

    @property
    def has_value(self):
        return self.value or self.multiline

    def represented_value(self):
        return represented_scalar(self.style, self.value)

    def resolved_value(self, clean):
        value = self.value
        if self.style is None and value is not None:
            value = value.strip()

        if clean and self.style is None:
            value = default_marshal(value)

        return value

    def add_line(self, text):
        if not self.value:
            self.value = text

        elif self.multiline:
            self.multiline.append(text)

        else:
            self.multiline = [self.value, text]

    def apply_multiline(self):
        if isinstance(self.multiline, list):
            self.value = yaml_lines(self.multiline)
            self.multiline = True

    def auto_filler(self, scanner):
        sk = scanner.simple_key
        if sk is None:
            scanner.simple_key = self

        elif self.indent < sk.indent or sk.has_comment:
            sk.apply_multiline()
            yield sk
            scanner.simple_key = self

        else:
            sk.add_line(self.value)
