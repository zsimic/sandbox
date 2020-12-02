import re

from .marshal import default_marshal, Marshallers, ParseError, represented_scalar, unicode_escaped


RE_COMMENT = re.compile(r"\s+#.*$")


def verify_indentation(reference, token, over=True, under=True):
    if reference is not None and token is not None:
        if under and token.indent < reference.indent and token.textually_significant:
            raise ParseError("%s is under-indented relative to %s" % (token.short_name, reference.short_name.lower()), token=token)

        if over and token.indent > reference.indent and token.textually_significant:
            raise ParseError("%s is over-indented relative to %s" % (token.short_name, reference.short_name.lower()), token=token)


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
    has_same_line_text = False  # Used to disambiguate simple keys

    def __init__(self, linenum, indent, text=None):
        self.linenum = linenum
        self.indent = indent
        self.text = text

    def __repr__(self):
        result = "%s[%s,%s]" % (self.__class__.__name__, self.linenum, self.column)
        if self.text is not None:
            result = "%s %s" % (result, self.represented_text())

        return result

    @property
    def column(self):
        return self.indent + 1

    @property
    def short_name(self):
        return self.__class__.__name__.replace("Token", "").replace("Block", "").replace("Flow", "").replace("Sequence", "List")

    @property
    def textually_significant(self):
        return False

    def represented_text(self):
        return unicode_escaped(self.text)

    def auto_injected(self, scanner):
        """Optional token to automatically inject"""
        return scanner.popped_scalar()

    def track_same_line_text(self, token):
        """Used to disambiguate simple keys"""

    def evaluate(self, visitor):
        pass


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

    def evaluate(self, visitor):
        visitor.push(self)


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
            raise ParseError("Directive must not be indented", token=self)

        text = text[1:]
        m = RE_COMMENT.search(text)
        if m is not None:
            text = text[:m.start()]

        self.name, _, text = text.strip().partition(" ")
        if not self.name:
            raise ParseError("Invalid directive", token=self)

        super(DirectiveToken, self).__init__(linenum, 0, text.strip())

    def represented_text(self):
        if self.text:
            return "%s %s" % (self.name, unicode_escaped(self.text))

        return self.name

    def auto_filler(self, scanner):
        if scanner.started_doc:
            raise ParseError("Directives allowed only at document start", token=self)

        if self.name == "YAML":
            if scanner.yaml_directive:
                raise ParseError("Only one YAML directive is allowed", token=self)

            scanner.yaml_directive = self

        yield self


class FlowMapToken(Token):

    has_same_line_text = True

    def auto_filler(self, scanner):
        for t in scanner.auto_push(self):
            yield t


class FlowSeqToken(Token):

    has_same_line_text = True

    def auto_filler(self, scanner):
        for t in scanner.auto_push(self):
            yield t


class FlowEndToken(Token):
    def auto_filler(self, scanner):
        for t in scanner.auto_pop(self):
            yield t


class CommaToken(Token):
    pass


class BlockMapToken(Token):

    current_line_text = None

    def track_same_line_text(self, token):
        if self.linenum == token.linenum:
            verify_indentation(self, token, over=False)
            self.current_line_text = token

        elif self.current_line_text is not None:
            verify_indentation(self, token)
            self.current_line_text = None


class BlockSeqToken(Token):
    def track_same_line_text(self, token):
        if token.indent <= self.indent and token.textually_significant:
            raise ParseError("%s under-indented relative to previous sequence" % token.short_name, token=token)


class BlockEndToken(Token):
    pass


class ExplicitMapToken(Token):
    def auto_injected(self, scanner):
        return None

    def auto_filler(self, scanner):
        sk = scanner.popped_scalar()
        if sk is not None:
            decorators = scanner.extracted_decorators(sk)
            if decorators is not None:
                for t in decorators:
                    yield t

            yield sk

        for t in scanner.auto_push(self, BlockMapToken):
            yield t

        yield KeyToken(self.linenum, self.indent)


class DashToken(Token):
    def auto_filler(self, scanner):
        for t in scanner.auto_push(self, BlockSeqToken):
            yield t

        yield self


class KeyToken(Token):
    pass


class ValueToken(Token):
    pass


class ColonToken(Token):
    def auto_injected(self, scanner):
        return None

    def auto_filler(self, scanner):
        sk = scanner.popped_scalar(with_simple_key=False)
        if sk is not None:
            decorators = scanner.extracted_decorators(sk)
            if decorators is not None:
                for t in decorators:
                    yield t

            yield sk

        sk = scanner.popped_scalar()
        if sk is None:
            if scanner.mode is scanner.block_scanner:
                raise ParseError("Incomplete explicit mapping pair", token=self)

        else:
            if sk.multiline and sk.style is None:
                raise ParseError("Mapping keys must be on a single line", token=self)

            decorators = scanner.extracted_decorators(sk)
            for t in scanner.auto_push(sk, BlockMapToken):
                yield t

            yield KeyToken(sk.linenum, sk.indent)
            if decorators is not None:
                for t in decorators:
                    yield t

            yield sk

        yield ValueToken(self.linenum, self.indent)


class TagToken(Token):
    def __init__(self, linenum, indent, text):
        super(TagToken, self).__init__(linenum, indent, text)
        self.marshaller = Marshallers.get_marshaller(text)

    def auto_injected(self, scanner):
        scanner.decorators.appendleft(self)
        return True


class AnchorToken(Token):
    def __init__(self, linenum, indent, text):
        super(AnchorToken, self).__init__(linenum, indent, text[1:])

    def represented_text(self):
        return "&%s" % unicode_escaped(self.text)

    def auto_injected(self, scanner):
        scanner.decorators.appendleft(self)
        return True


class AliasToken(Token):
    def __init__(self, linenum, indent, text):
        super(AliasToken, self).__init__(linenum, indent)
        self.anchor = text[1:]

    def __repr__(self):
        return "AliasToken[%s,%s] *%s" % (self.linenum, self.column, self.anchor)

    def resolved_value(self):
        return self.text


class ScalarToken(Token):

    has_same_line_text = True

    def __init__(self, linenum, indent, text, style=None):
        super(ScalarToken, self).__init__(linenum, indent, text)
        self.style = style
        self.multiline = None
        self.has_comment = False

    @property
    def textually_significant(self):
        return self.text or self.style

    def represented_text(self):
        return represented_scalar(self.style, self.text)

    def resolved_value(self):
        text = self.text
        if self.style is None:
            text = default_marshal(text)

        return text

    def add_line(self, text):
        if not self.text:
            self.text = text

        elif self.multiline:
            self.multiline.append(text)

        else:
            self.multiline = [self.text, text]

    def apply_multiline(self):
        if isinstance(self.multiline, list):
            self.text = yaml_lines(self.multiline)
            self.multiline = True

    def auto_injected(self, scanner):
        scanner.accumulate_scalar(self)
        return True
