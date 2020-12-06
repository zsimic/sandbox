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


class VisitedToken(object):

    value = None

    def resolved_value(self):
        return self.value

    def consume_key(self, visitor, value):
        raise ParseError("Unexpected key '%s' in %s" % (value, self))

    def consume_value(self, visitor, value):
        self.value = value

    def auto_pop(self, visitor, token):
        raise ParseError("Internal error: can't auto-pop '%s' from %s" % (token, self))

    def evaluate(self, visitor):
        raise ParseError("Internal error: can't evaluate '%s'" % self)


class Token(VisitedToken):
    """Represents one scanned token"""

    auto_start_doc = True  # Does this token imply DocumentStartToken?
    has_same_line_text = False  # Used to disambiguate simple keys

    def __init__(self, linenum, indent, text=None, value=None):
        self.linenum = linenum
        self.indent = indent
        self.text = text
        self.value = value

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

    def track_same_line_text(self, token):
        """Used to disambiguate simple keys"""

    def auto_filler(self, scanner):
        for t in scanner.auto_popped_scalar():
            yield t

        yield self


class CommentToken(Token):
    pass


class StreamStartToken(Token):

    auto_start_doc = False

    def evaluate(self, visitor):
        pass


class StreamEndToken(Token):

    auto_start_doc = False

    def evaluate(self, visitor):
        pass


class DocumentStartToken(Token):

    auto_start_doc = False

    def auto_filler(self, scanner):
        for t in scanner.auto_pop_all(self):
            yield t

        scanner.started_doc = True
        yield self

    def auto_pop(self, visitor, token):
        self.value = token.resolved_value()

    def evaluate(self, visitor):
        visitor.push(self)


class DocumentEndToken(Token):

    auto_start_doc = False

    def auto_filler(self, scanner):
        for t in scanner.auto_pop_all(self):
            yield t

        yield self

    def evaluate(self, visitor):
        popped = visitor.pop()
        value = popped.resolved_value()
        visitor.consume_value(value)


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


class StackedValue(Token):

    def evaluate(self, visitor):
        while True:
            popped = visitor.pop()
            self.value = popped.resolved_value()
            visitor.trigger_auto_pop(self)
            if isinstance(popped, StackedValue):
                return


class StackedMap(StackedValue):

    def __init__(self, linenum, indent, text=None):
        super(StackedMap, self).__init__(linenum, indent, text=text, value={})
        self.needs_wrap = False
        self.pending_key = None

    def resolved_value(self):
        if self.needs_wrap:
            self.value[self.pending_key] = None
            self.pending_key = None
            self.needs_wrap = False

        return self.value

    def consume_key(self, visitor, value):
        if self.needs_wrap:
            self.value[self.pending_key] = None

        self.pending_key = value
        self.needs_wrap = True

    def consume_value(self, visitor, value):
        self.value[self.pending_key] = value
        self.pending_key = None
        self.needs_wrap = False

    def auto_pop(self, visitor, token):
        value = token.resolved_value()
        if self.needs_wrap:
            self.value[self.pending_key] = value
            self.needs_wrap = False

        else:
            self.value[value] = None

        self.pending_key = None

    def evaluate(self, visitor):
        visitor.push(self)


class StackedSequence(StackedValue):

    def __init__(self, linenum, indent, text=None):
        super(StackedSequence, self).__init__(linenum, indent, text=text, value=[])
        self.needs_wrap = False

    def consume_key(self, visitor, value):
        if self.needs_wrap:
            self.consume_value(visitor, None)

        self.needs_wrap = (value, None)

    def resolved_value(self):
        if self.needs_wrap is True:
            self.value.append(None)
            self.needs_wrap = False

        elif isinstance(self.needs_wrap, tuple):
            self.value.append(dict(self.needs_wrap))
            self.needs_wrap = False

        return self.value

    def consume_value(self, visitor, value):
        if isinstance(self.needs_wrap, tuple):
            self.value.append({self.needs_wrap[0]: value})

        else:
            self.value.append(value)

        self.needs_wrap = False

    def auto_pop(self, visitor, token):
        self.consume_value(visitor, token.resolved_value())

    def evaluate(self, visitor):
        visitor.push(self)


class FlowMapToken(StackedMap):

    has_same_line_text = True

    def auto_filler(self, scanner):
        for t in scanner.auto_push(self):
            yield t


class FlowSeqToken(StackedSequence):

    has_same_line_text = True

    def auto_filler(self, scanner):
        for t in scanner.auto_push(self):
            yield t

    def evaluate(self, visitor):
        visitor.push(self)


class FlowEndToken(StackedValue):

    def auto_filler(self, scanner):
        for t in scanner.auto_popped_scalar():
            yield t

        try:
            popped = scanner.flow_scanner.stack.pop()
            mismatched = popped.__class__ != scanner.flow_scanner.flow_closers[self.text]

        except (KeyError, IndexError):
            mismatched = True

        if mismatched:
            raise ParseError("Unexpected flow closing character '%s'" % self.text)

        if not scanner.flow_scanner.stack:
            scanner.mode = scanner.block_scanner

        yield self


class CommaToken(Token):
    pass


class BlockMapToken(StackedMap):

    current_line_text = None

    def track_same_line_text(self, token):
        if self.linenum == token.linenum:
            verify_indentation(self, token, over=False)
            self.current_line_text = token

        elif self.current_line_text is not None:
            verify_indentation(self, token)
            self.current_line_text = None


class BlockSeqToken(StackedSequence):

    def track_same_line_text(self, token):
        if token.indent <= self.indent and token.textually_significant:
            raise ParseError("%s under-indented relative to previous sequence" % token.short_name, token=token)


class BlockEndToken(StackedValue):
    pass


class ExplicitMapToken(Token):
    pass


class DashToken(Token):

    def auto_filler(self, scanner):
        for t in scanner.auto_push(self, BlockSeqToken):
            yield t

        yield self

    def evaluate(self, visitor):
        visitor.top.needs_wrap = True


class KeyToken(Token):

    def auto_pop(self, visitor, token):
        visitor.pop()
        visitor.consume_key(token.resolved_value())

    def evaluate(self, visitor):
        visitor.push(self)


class ValueToken(Token):

    def auto_pop(self, visitor, token):
        visitor.pop()
        visitor.consume_value(token.resolved_value())

    def evaluate(self, visitor):
        visitor.push(self)


class ColonToken(Token):

    def auto_filler(self, scanner):
        sk = scanner.simple_key
        scanner.simple_key = None
        if sk is None:
            if scanner.mode is scanner.block_scanner:
                raise ParseError("Incomplete explicit mapping pair", token=self)

            sk = ScalarToken(self.linenum, self.indent, None)

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

    def auto_filler(self, scanner):
        scanner.decorators.appendleft(self)


class AnchorToken(Token):

    def __init__(self, linenum, indent, text):
        super(AnchorToken, self).__init__(linenum, indent, text[1:])

    def represented_text(self):
        return "&%s" % unicode_escaped(self.text)

    def auto_filler(self, scanner):
        scanner.decorators.appendleft(self)


class AliasToken(Token):

    def __init__(self, linenum, indent, text):
        super(AliasToken, self).__init__(linenum, indent)
        self.anchor = text[1:]

    def __repr__(self):
        return "AliasToken[%s,%s] *%s" % (self.linenum, self.column, self.anchor)


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

    def cumulate_scalar(self, other):
        if self.has_comment and other.text:
            raise ParseError("Trailing content after comment", token=other)

        self.has_comment = other.has_comment
        if not self.text:
            self.text = other.text

        elif self.multiline:
            self.multiline.append(other.text)

        else:
            self.multiline = [self.text, other.text]

    def apply_multiline(self):
        if isinstance(self.multiline, list):
            self.text = yaml_lines(self.multiline)
            self.multiline = True

    def auto_filler(self, scanner):
        sk = scanner.simple_key
        significant = self if self.textually_significant else None
        scanner.simple_key = significant
        if sk is not None:
            acc = scanner.accumulated_scalar
            if acc is None:
                scanner.mode.track_same_line_text(sk)
                scanner.accumulated_scalar = sk
                if significant is None:
                    sk.cumulate_scalar(self)

            else:
                acc.cumulate_scalar(sk)

    def evaluate(self, visitor):
        visitor.trigger_auto_pop(self)
