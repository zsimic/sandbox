import collections

from zyaml.stack import *


RESERVED = "@`"
RE_HEADERS = re.compile(r"^(\s*#|\s*%|(---|\.\.\.)(\s|$))")
RE_BLOCK_SEQUENCE = re.compile(r"\s*((-\s+\S)|-\s*$)")
RE_FLOW_SEP = re.compile(r"""(#|\?\s|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{},])\s*(\S?)""")
RE_BLOCK_SEP = re.compile(r"""(#|\?\s|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{}])\s*(\S?)""")
RE_DOUBLE_QUOTE_END = re.compile(r'(^\s*"|[^\\]")\s*(.*?)\s*$')
RE_SINGLE_QUOTE_END = re.compile(r"(^\s*'|[^']'([^']|$))")
RE_CONTENT = re.compile(r"\s*(.*?)\s*$")


def yaml_lines(lines, text=None, indent=None, folded=None, keep=False, continuations=False):
    """
    :param list lines: Lines to concatenate together
    :param str|None text: Initial line (optional)
    :param int|None indent: If not None, we're doing a block scalar
    :param bool folded: If True, we're doing a folded block scalar (marked by `>`)
    :param bool keep: If True, keep trailing newlines
    :param bool continuations: If True, respect end-of-line continuations (marked by `\\`)
    :return str: Concatenated string, with yaml's weird convention
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


class TokenStack(object):
    def __init__(self, scanner):
        self.scanner = scanner
        self.started_doc = False
        self.pending_scalar = None
        self.structures = collections.deque()
        self.nesting_level = None

    def add_structure(self, token):
        self.nesting_level = token.indent
        self.structures.append(token)

    def add_scalar(self, token):
        if self.pending_scalar is None:
            self.pending_scalar = token
        else:
            self.pending_scalar.append_line(token.value)

    def popped_scalar(self):
        s = self.pending_scalar
        self.pending_scalar = None
        return s

    def doc_start(self, token):
        if not self.started_doc:
            self.started_doc = True
            yield DocumentStartToken(self.scanner, token.linenum, token.indent)

    def doc_end(self, token):
        if self.started_doc:
            self.started_doc = False
            linenum = token.linenum
            if not isinstance(token, DocumentEndToken):
                linenum += 1
            while self.structures:
                yield BlockEndToken(self.scanner, token.linenum, self.structures.pop().indent)
            yield DocumentEndToken(self.scanner, linenum, token.indent)

    def pop_until(self, linenum, indent):
        i = self.nesting_level
        while i is not None and i < indent:
            try:
                i = self.structures.pop().indent
                yield BlockEndToken(self.scanner, linenum, i)
            except IndexError:
                i = None
        self.nesting_level = i


class Scanner(object):
    def __init__(self, buffer):
        if hasattr(buffer, "read"):
            self.generator = enumerate(buffer.read().splitlines(), start=1)
        else:
            self.generator = enumerate(buffer.splitlines(), start=1)
        self.simple_key = None  # type: Optional[ScalarToken]
        self.pending_dash = None  # type: Optional[DashToken]
        self.pending_scalar = None  # type: Optional[ScalarToken]
        self.pending_lines = None  # type: Optional[List[str]]
        self.pending_tokens = None  # type: Optional[List[Token]]
        self.line_regex = RE_BLOCK_SEP
        self.flow_ender = None
        self.tokenizer_map = {
            "!": TagToken,
            "&": AnchorToken,
            "*": AliasToken,
            "{": FlowMapToken,
            "}": FlowEndToken,
            "[": FlowSeqToken,
            "]": FlowEndToken,
            ",": CommaToken,
            "?": ExplicitMapToken,
        }

    def __repr__(self):
        return dbg(
            ("flow mode ", self.flow_ender, "block mode "),
            ("K", self.simple_key), ("S", self.pending_scalar), ("L", self.pending_lines),
            ("T", self.pending_tokens), ("-", self.pending_dash)
        )

    def promote_simple_key(self):
        if self.simple_key is not None:
            if self.pending_scalar is None:
                self.pending_scalar = self.simple_key
            elif self.flow_ender is None and self.simple_key.indent == 0 and self.simple_key.indent != self.pending_scalar.indent:
                raise ParseError("Simple key must be indented in order to continue previous line")
            else:
                if self.pending_lines is None:
                    self.pending_lines = []
                self.pending_lines.append(self.simple_key.value)
            self.simple_key = None

    def promote_pending_scalar(self):
        if self.pending_scalar is not None:
            if self.pending_lines is not None:
                self.pending_scalar.value = yaml_lines(self.pending_lines, text=self.pending_scalar.value)
            self.add_pending_token(self.pending_scalar)
            self.pending_scalar = None
            self.pending_lines = None

    def is_dash_meaningful(self, linenum, indent):
        if self.pending_dash is not None:
            return linenum == self.pending_dash.linenum or indent == self.pending_dash.indent
        if self.pending_scalar is not None:
            return indent < self.pending_scalar.indent
        return True

    def add_pending_dash(self, linenum, indent):
        if self.is_dash_meaningful(linenum, indent):
            self.pending_dash = DashToken(self, linenum, indent)
            self.add_pending_token(self.pending_dash)
        else:
            self.add_pending_line("-")

    def add_pending_token(self, token):
        if self.pending_tokens is None:
            self.pending_tokens = []
        self.pending_tokens.append(token)

    def add_pending_line(self, text):
        if self.pending_lines is None:
            self.pending_lines = []
        self.pending_lines.append(text)

    def consumed_pending(self):
        if self.pending_scalar is not None:
            if self.pending_lines is not None:
                self.pending_scalar.value = yaml_lines(self.pending_lines, text=self.pending_scalar.value)
            yield self.pending_scalar
            self.pending_scalar = None
            self.pending_lines = None
        if self.pending_tokens is not None:
            for token in self.pending_tokens:
                yield token
            self.pending_tokens = None

    def push_flow_ender(self, ender):
        if self.flow_ender is None:
            self.flow_ender = collections.deque()
            self.line_regex = RE_FLOW_SEP
        self.flow_ender.append(ender)

    def pop_flow_ender(self, found):
        if self.flow_ender is None:
            raise ParseError("'%s' without corresponding opener" % found)
        expected = self.flow_ender.pop()
        if not self.flow_ender:
            self.flow_ender = None
            self.line_regex = RE_BLOCK_SEP
        if expected != found:
            raise ParseError("Expecting '%s', but found '%s'" % (expected, found))

    @staticmethod
    def _checked_string(linenum, start, end, line_text):
        if start >= end:
            line_text = None
            start = 0
        return linenum, start, end, line_text

    def _double_quoted(self, linenum, start, end, line_text):
        token = ScalarToken(self, linenum, start, "", style='"')
        self.pending_scalar = token
        try:
            if start < end and line_text[start] == '"':  # Empty string
                return self._checked_string(linenum, start + 1, end, line_text)
            lines = None
            m = None
            while m is None:
                m = RE_DOUBLE_QUOTE_END.search(line_text, start)
                if m is not None:
                    text = line_text[start:m.span(1)[1] - 1]
                    if lines is not None:
                        lines.append(text)
                        text = yaml_lines(lines, keep=True, continuations=True)
                    token.value = codecs.decode(text, "unicode_escape")
                    start, end = m.span(2)
                    return self._checked_string(linenum, start, end, line_text)
                if lines is None:
                    lines = [line_text[start:].rstrip()]
                    start = 0
                else:
                    lines.append(line_text.rstrip())
                linenum, line_text = next(self.generator)
                line_text = line_text.strip()
        except StopIteration:
            raise ParseError("Unexpected end, runaway double-quoted string at line %s?" % token.linenum)

    def _single_quoted(self, linenum, start, end, line_text):
        token = ScalarToken(self, linenum, start, "", style="'")
        self.pending_scalar = token
        try:
            if start < end and line_text[start] == "'":  # Empty string
                return self._checked_string(linenum, start + 1, end, line_text)
            lines = None
            m = None
            while m is None:
                m = RE_SINGLE_QUOTE_END.search(line_text, start)
                if m is not None:
                    quote_pos = m.span(1)[0]
                    if line_text[quote_pos] != "'":
                        quote_pos = quote_pos + 1
                    text = line_text[start:quote_pos]
                    if lines is not None:
                        lines.append(text)
                        text = yaml_lines(lines, keep=True)
                    token.value = text.replace("''", "'")
                    m = RE_CONTENT.match(line_text, quote_pos + 1)
                    start, end = m.span(1)
                    return self._checked_string(linenum, start, end, line_text)
                if lines is None:
                    lines = [line_text[start:].rstrip()]
                    start = 0
                else:
                    lines.append(line_text.rstrip())
                linenum, line_text = next(self.generator)
                line_text = line_text.strip()
        except StopIteration:
            raise ParseError("Unexpected end, runaway single-quoted string at line %s?" % token.linenum)

    def _get_literal_styled_token(self, linenum, start, style):
        original = style
        if len(style) > 3:
            raise ParseError("Invalid literal style '%s', should be less than 3 chars" % style, linenum, start)
        keep = None
        if "-" in style:
            style = style.replace("-", "", 1)
            keep = False
        if "+" in style:
            if keep is not None:
                raise ParseError("Ambiguous literal style '%s'" % original, linenum, start)
            keep = True
            style = style.replace("+", "", 1)
        indent = None
        if len(style) == 2:
            indent = style[1]
            style = style[0]
            if not indent.isdigit():
                raise ParseError("Invalid literal style '%s'" % original, linenum, start)
            indent = int(indent)
            if indent < 1:
                raise ParseError("Indent must be between 1 and 9", linenum, start)
        return style == ">", keep, indent, ScalarToken(self, linenum, indent, None, style=original)

    def _consume_literal(self, linenum, start, style):
        folded, keep, indent, token = self._get_literal_styled_token(linenum, start, style)
        self.pending_scalar = token
        lines = []
        while True:
            try:
                linenum, line_text = next(self.generator)
                m = RE_CONTENT.match(line_text)
                start, end = m.span(1)
                if start == end:
                    lines.append(line_text)
                    continue
            except StopIteration:
                line_text = None
                start = end = 0
            if indent is None:
                token.indent = indent = start if start != 0 else 1
            if start < indent:
                if not lines:
                    raise ParseError("Bad literal indentation")
                text = yaml_lines(lines, indent=indent, folded=folded, keep=keep)
                if keep is None:
                    if text:
                        token.value = "%s\n" % text.rstrip()
                    else:
                        token.value = text
                elif keep is False:
                    token.value = text.rstrip()
                else:
                    token.value = "%s\n" % text
                if start >= end:
                    line_text = None
                return linenum, 0, end, line_text
            lines.append(line_text)

    def next_match(self, start, end, line_text):
        rstart = start
        seen_colon = False
        while start < end:
            m = self.line_regex.search(line_text, rstart)
            if m is None:
                break
            mstart, mend = m.span(1)  # span1: what we just matched
            rstart = m.span(2)[0]  # span2: first non-space for the rest of the string
            matched = line_text[mstart]
            if matched == "#":
                if line_text[mstart - 1] in " \t":
                    if start < mstart:
                        yield None, start, line_text[start:mstart].rstrip()
                    return
            else:
                if self.flow_ender is None:
                    if matched == ":":  # ':' only applicable once, either at end of line or followed by a space
                        if seen_colon:
                            actionable = False
                        elif rstart == end or line_text[mstart + 1] in " \t":
                            seen_colon = True
                            actionable = True
                        else:
                            actionable = False
                    else:
                        actionable = start == mstart
                elif matched == ":":
                    actionable = rstart == end or line_text[mstart - 1] == '"' or line_text[mstart + 1] in " \t,"
                else:
                    actionable = start == mstart or matched in "{}[],"
                if actionable:
                    if start < mstart:
                        yield None, start, line_text[start:mstart].rstrip()
                    yield matched, mstart, line_text[mstart:mend]
                    start = rstart
        if start < end:
            yield None, start, line_text[start:end]

    def header_token(self, linenum, start, line_text):
        if start == 0:
            m = RE_HEADERS.match(line_text)
            if m is not None:
                self.promote_pending_scalar()
                start, end = m.span(1)
                matched = line_text[start:end]
                if matched[0] == "-":
                    self.add_pending_token(DocumentStartToken(self, linenum, 0))
                    if matched[-1] == " ":
                        return False, linenum, end, line_text
                    return True, linenum, 0, None
                elif matched[0] == ".":
                    self.add_pending_token(DocumentEndToken(self, linenum, 0))
                    if matched[-1] == " ":
                        return False, linenum, end, line_text
                    return True, linenum, 0, None
                elif matched[-1] == "%":
                    if end != 1:
                        raise ParseError("Directive must not be indented", linenum, end - 1)
                    self.add_pending_token(DirectiveToken(self, linenum, 0, line_text))
                    return True, linenum, 0, None
                return True, linenum, 0, None
        m = RE_BLOCK_SEQUENCE.match(line_text, start)
        if m is None:
            return False, linenum, start, line_text
        start = m.span(1)[0] + 1
        self.add_pending_dash(linenum, start)
        first_non_blank = m.span(2)[1] - 1
        if first_non_blank < 0:
            return True, linenum, 0, None
        if line_text[first_non_blank] == "-":
            return True, linenum, start, line_text
        return False, linenum, first_non_blank, line_text

    def headers(self, linenum, start, line_text):
        tbc = True
        while tbc:
            if line_text is None:
                linenum, line_text = next(self.generator)
                start = 0
            tbc, linenum, start, line_text = self.header_token(linenum, start, line_text)
        m = RE_CONTENT.match(line_text, start)
        start, end = m.span(1)
        if start == end and self.pending_scalar is not None and self.pending_scalar.style is None:
            self.add_pending_line("")
        return linenum, start, end, line_text

    def tokens(self):
        stack = TokenStack(self)
        t1 = StreamStartToken(self, 1, 0)
        yield t1
        for t1 in self.first_pass():
            for t2 in t1.second_pass(stack):
                yield t2
        for t2 in stack.doc_end(t1):
            yield t2
        yield StreamEndToken(self, t1.linenum, 0)

    def first_pass(self):
        """Yield raw tokens as-is, don't try to interpret simple keys, look at indentation etc"""
        start = end = offset = 0
        linenum = 1
        upcoming = None
        try:
            while True:
                self.promote_simple_key()
                if start == 0 or upcoming is None:
                    linenum, start, end, line_text = self.headers(linenum, start, upcoming)
                    if self.pending_tokens is not None:
                        for token in self.consumed_pending():
                            yield token
                else:
                    line_text = upcoming
                    for token in self.consumed_pending():
                        yield token
                upcoming = None
                for matched, offset, text in self.next_match(start, end, line_text):
                    if self.simple_key is None:
                        if matched is None:
                            if text[0] in RESERVED:
                                raise ParseError("Character '%s' is reserved" % text[0], linenum, offset)
                            if self.pending_scalar is None:
                                if text[0] == '"':
                                    linenum, start, end, upcoming = self._double_quoted(linenum, offset + 1, end, line_text)
                                    break
                                if text[0] == "'":
                                    linenum, start, end, upcoming = self._single_quoted(linenum, offset + 1, end, line_text)
                                    break
                                if text[0] in '|>':
                                    linenum, start, end, upcoming = self._consume_literal(linenum, offset, text)
                                    break
                            self.simple_key = ScalarToken(self, linenum, offset, text)
                            continue
                        if matched == ":":
                            yield ColonToken(self, linenum, offset)
                            self.pending_dash = None
                            continue
                        for token in self.consumed_pending():
                            yield token
                        tokenizer = self.tokenizer_map.get(matched)
                        yield tokenizer(self, linenum, offset, text)
                        self.pending_dash = None
                    elif matched == ":":
                        self.pending_dash = None
                        for token in self.consumed_pending():
                            yield token
                        yield self.simple_key
                        self.simple_key = None
                        yield ColonToken(self, linenum, offset)
                    else:
                        self.promote_simple_key()
                        for token in self.consumed_pending():
                            yield token
                        tokenizer = self.tokenizer_map.get(matched)
                        yield tokenizer(self, linenum, offset, text)
        except StopIteration:
            self.promote_simple_key()
            self.promote_pending_scalar()
            last_token = None
            for token in self.consumed_pending():
                last_token = token
                yield token
            if isinstance(last_token, DashToken):
                yield ScalarToken(self, linenum, last_token.indent + 1, None)
        except ParseError as error:
            error.auto_complete(linenum, offset)
            raise

    def deserialized(self, loader, simplified=True):
        token = None
        try:
            for token in self.tokens():
                name = token.__class__.__name__
                func = getattr(loader, name, None)
                if func is not None:
                    func(token)
                # trace("{}: {}", token, loader)
            if simplified:
                if not loader.docs:
                    return None
                if len(loader.docs) == 1:
                    return loader.docs[0]
            return loader.docs
        except ParseError as error:
            error.auto_complete(token)
            raise