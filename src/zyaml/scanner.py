import collections

from zyaml.loader import *
from zyaml.tokens import *


RESERVED = "@`"
RE_HEADERS = re.compile(r"^(\s*#|%|(---|\.\.\.)(\s|$))")
RE_BLOCK_SEQUENCE = re.compile(r"\s*((-\s+\S)|-\s*$)")
RE_DOUBLE_QUOTE_END = re.compile(r'(^\s*"|[^\\]")\s*(.*?)\s*$')
RE_SINGLE_QUOTE_END = re.compile(r"(^\s*'|[^']'([^']|$))")
RE_CONTENT = re.compile(r"\s*(.*?)\s*$")


def _get_literal_styled_token(linenum, start, style):
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

    return style == ">", keep, indent, ScalarToken(linenum, indent, None, style=original)


def _consume_literal(generator, linenum, start, style):
    folded, keep, indent, token = _get_literal_styled_token(linenum, start, style)
    lines = []
    while True:
        try:
            linenum, line_text = next(generator)
            line_text = line_text.rstrip("\r\n")
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

            return linenum, 0, end, line_text, token

        lines.append(line_text)


def _checked_string(linenum, start, end, line_text, token):
    if start >= end:
        line_text = None
        start = 0

    return linenum, start, end, line_text, token


def _double_quoted(generator, linenum, start, end, line_text):
    token = ScalarToken(linenum, start, "", style='"')
    try:
        if start < end and line_text[start] == '"':  # Empty string
            return _checked_string(linenum, start + 1, end, line_text, token)

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
                return _checked_string(linenum, start, end, line_text, token)

            if lines is None:
                lines = [line_text[start:].rstrip()]
                start = 0

            else:
                lines.append(line_text.rstrip())

            linenum, line_text = next(generator)
            line_text = line_text.strip()

    except StopIteration:
        raise ParseError("Unexpected end, runaway double-quoted string at line %s?" % token.linenum)


def _single_quoted(generator, linenum, start, end, line_text):
    token = ScalarToken(linenum, start, "", style="'")
    try:
        if start < end and line_text[start] == "'":  # Empty string
            return _checked_string(linenum, start + 1, end, line_text, token)

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
                    token.multiline = True

                token.value = text.replace("''", "'")
                m = RE_CONTENT.match(line_text, quote_pos + 1)
                start, end = m.span(1)
                return _checked_string(linenum, start, end, line_text, token)

            if lines is None:
                lines = [line_text[start:].rstrip()]
                start = 0

            else:
                lines.append(line_text.rstrip())

            linenum, line_text = next(generator)
            line_text = line_text.strip()

    except StopIteration:
        raise ParseError("Unexpected end, runaway single-quoted string at line %s?" % token.linenum)


class ModalScanner(object):
    """Ancestor to block and flow modal scanners"""

    line_regex = None  # type: re.Pattern

    def __init__(self, scanner):
        self.scanner = scanner
        self.stack = collections.deque()

    def __repr__(self):
        stacks = " / ".join("%s%s" % (s.value, s.indent) for s in self.stack)
        return "%s - %s" % (self.mode_name.lower(), stacks)

    @property
    def mode_name(self):
        return self.__class__.__name__.replace("Scanner", "")

    @property
    def current_type(self):
        """Current underlying type of token at top of stack"""
        name = self.mode_name
        if self.stack:
            name = self.stack[-1].__class__.__name__.replace("Token", "").replace(name, "")

        return name.lower().replace("seq", "list")

    def auto_push(self, token, block):
        """
        Args:
            token (Token): Token that is requesting the push
            block (type | None): Block mode to start when applicable
        """

    def auto_pop(self, token):
        """
        Args:
            token (Token): Token that is requesting the pop
        """

    def auto_pop_all(self, token):
        """
        Args:
            token (Token): Token that is requesting the pop
        """


class BlockScanner(ModalScanner):
    """Scan tokens for block mode (default, exclusive with flow mode started by '[' or '{')"""

    nesting_level = None  # type: int
    line_regex = re.compile(r"""(#|\?\s|[!&*][^\s:\[\]{}]+|[:\[\]{}])\s*(\S?)""")

    def auto_push(self, token, block):
        if block is None:
            raise ParseError("Internal error: flow pushed onto block")

        i = self.nesting_level
        while i is not None and i > token.indent:
            try:
                struct = self.stack.pop()
                i = struct.indent
                if i > token.indent:
                    yield BlockEndToken(token.linenum, i)

                else:
                    self.stack.append(struct)

            except IndexError:
                i = None

        self.nesting_level = i
        ti = token.indent
        if i != ti:
            struct = block(token.linenum, ti)
            self.nesting_level = ti
            self.stack.append(struct)
            yield struct

    def auto_pop(self, token):
        i = self.nesting_level
        while i is not None and i < token.indent:
            try:
                i = self.stack.pop().indent
                yield BlockEndToken(token.linenum, i)

            except IndexError:
                i = None

        self.nesting_level = i

    def auto_pop_all(self, token):
        while self.stack:
            yield BlockEndToken(token.linenum, self.stack.pop().indent)


class FlowScanner(ModalScanner):
    """Scan tokens for flow mode (started by '[' or '{', exclusive with block mode)"""

    line_regex = re.compile(r"""(#|[!&*][^\s:,\[\]{}]+|[:,\[\]{}])\s*(\S?)""")
    flow_closers = {"]": FlowSeqToken, "}": FlowMapToken}

    def auto_push(self, token, block):
        if block is None and token is not None:
            self.stack.append(token)
            yield token

    def auto_pop(self, token):
        try:
            popped = self.stack.pop()
            mismatched = popped.__class__ != self.flow_closers[token.value]

        except (KeyError, IndexError):
            mismatched = True

        if mismatched:
            raise ParseError("Unexpected flow closing character '%s'" % token.value)

        yield token

    def auto_pop_all(self, token):
        raise ParseError("Expected flow map end", token.linenum, token.column)


class Scanner(object):
    def __init__(self, stream, comments=False):
        self.generator = enumerate(stream, start=1)
        self.comments = comments
        self.block_scanner = BlockScanner(self)
        self.flow_scanner = FlowScanner(self)
        self.mode = self.block_scanner
        self.yaml_directive = None
        self.directives = None
        self.started_doc = None
        self.simple_key = None  # type: Optional[ScalarToken]
        self.pending_value = False
        self.tokenizer_map = {
            "!": TagToken,
            "&": AnchorToken,
            "*": AliasToken,
            "{": FlowMapToken,
            "}": FlowEndToken,
            "[": FlowSeqToken,
            "]": FlowEndToken,
            ",": CommaToken,  # only in flows
            "?": ExplicitMapToken,  # only in blocks
            ":": ColonToken,
        }

    def __repr__(self):
        return str(self.mode)

    def check_indentation(self, token):
        if self.mode is self.block_scanner:
            mi = self.block_scanner.nesting_level
            if mi is not None and token.indent < mi:
                raise ParseError("Misaligned indentation")

    def top_modal_token(self):
        try:
            return self.mode.stack[-1]

        except IndexError:
            return None

    def popped_simple_key(self):
        sk = self.simple_key
        if sk is not None:
            sk.apply_multiline()
            self.pending_value = False
            self.simple_key = None

        return sk

    def auto_push(self, token, block=None):
        if block is None and self.mode is self.block_scanner:
            # Pushing a flow opener: '{' or '[' character, automatically switch to flow mode
            self.mode = self.flow_scanner

        for t in self.mode.auto_push(token, block):
            yield t

    def auto_pop(self, token):
        for t in self.mode.auto_pop(token):
            yield t

        if self.mode is self.flow_scanner and not self.mode.stack:
            self.mode = self.block_scanner

    def auto_pop_all(self, token):
        sk = self.popped_simple_key()
        if sk is not None:
            yield sk

        for t in self.mode.auto_pop_all(token):
            yield t

        if self.started_doc:
            self.started_doc = False
            if not isinstance(token, DocumentEndToken):
                yield DocumentEndToken(token.linenum + 1, 0)

    def next_match(self, linenum, start, end, line_text):
        rstart = start
        seen_colon = False
        while start < end:
            m = self.mode.line_regex.search(line_text, rstart)
            if m is None:
                break

            mstart, mend = m.span(1)  # span1: what we just matched
            rstart = m.span(2)[0]  # span2: first non-space for the rest of the string
            matched = line_text[mstart]
            if matched == "#":
                if line_text[mstart - 1] not in " \t":
                    continue

                sk = self.simple_key
                if sk is not None:
                    sk.has_comment = True  # Mark simple key as interrupted by comment

                if self.comments:
                    yield CommentToken(linenum, start, line_text[start:]), None, None

                return

            if matched == ":":  # ':' only applicable once, either at end of line or followed by a space
                if rstart == end:
                    actionable = True

                elif self.mode is self.block_scanner:
                    actionable = line_text[mstart + 1] in " \t"

                else:
                    actionable = line_text[mstart - 1] in '"\'' or line_text[mstart + 1] in " \t,"

                if actionable:
                    if seen_colon:
                        raise ParseError("Nested mappings are not allowed in compact mappings")

                    seen_colon = True

            elif start == mstart:
                actionable = True

            elif self.mode is self.flow_scanner:
                actionable = matched in "{}[],"

            else:
                actionable = False

            if actionable:
                if start < mstart:
                    yield None, start, line_text[start:mstart].rstrip()

                tokenizer = self.tokenizer_map.get(matched)
                if tokenizer is not None:
                    yield tokenizer(linenum, mstart, line_text[mstart:mend]), None, None

                else:
                    yield None, mstart, line_text[mstart:mend]

                start = rstart

        if start < end:
            yield None, start, line_text[start:end]

    def headers(self, linenum, start, line_text):
        while True:
            if line_text is None:
                try:
                    linenum, line_text = next(self.generator)
                    line_text = line_text.rstrip("\r\n")
                    start = 0

                except StopIteration:
                    yield None, None
                    return

            m = None
            if start == 0 and self.mode is self.block_scanner:
                m = RE_HEADERS.match(line_text)

            if m is None:
                if self.mode is self.block_scanner:
                    m = RE_BLOCK_SEQUENCE.match(line_text, start)

                while m is not None:
                    start = m.span(1)[0] + 1
                    yield None, DashToken(linenum, start)
                    first_non_blank = m.span(2)[1] - 1
                    if first_non_blank > 0 and line_text[first_non_blank] != "-":
                        start = first_non_blank
                        break

                    m = RE_BLOCK_SEQUENCE.match(line_text, start)

                m = RE_CONTENT.match(line_text, start)
                first_non_blank, end = m.span(1)
                if start == 0 and first_non_blank == end and self.simple_key is not None:
                    yield None, ScalarToken(linenum, start, "")
                    line_text = None
                    continue

                yield (linenum, first_non_blank, end, line_text), None
                return

            start, end = m.span(1)
            matched = line_text[start:end]
            if matched[0] == "-":
                yield None, DocumentStartToken(linenum, 0)
                if matched[-1] == " ":
                    start = end

                else:
                    line_text = None

            elif matched[0] == ".":
                yield None, DocumentEndToken(linenum, 0)
                if matched[-1] == " ":
                    start = end

                else:
                    line_text = None

            elif matched[-1] == "%":
                yield None, DirectiveToken(linenum, end, line_text)
                line_text = None

            elif matched[-1] == "#":
                sk = self.simple_key
                if sk is not None:
                    sk.has_comment = True  # Mark simple key as interrupted by comment

                if self.comments:
                    yield None, CommentToken(linenum, start, line_text[start:])

                line_text = None

            else:
                raise ParseError("Unexpected character '%s'" % matched)

        yield (linenum, start, end, line_text), None

    # noinspection PyAssignmentToLoopOrWithParameter
    def tokens(self):
        token = StreamStartToken(1, 0)
        yield token
        try:
            for token in self._raw_tokens():
                if token.auto_start_doc and not self.started_doc:
                    self.started_doc = True
                    yield DocumentStartToken(token.linenum, 0)

                if token.pop_simple_key:
                    sk = self.popped_simple_key()
                    if sk is not None:
                        yield sk

                if token.auto_filler is not None:
                    for token in token.auto_filler(self):
                        yield token

                else:
                    yield token

            for token in self.auto_pop_all(token):
                yield token

            yield StreamEndToken(token.linenum, 0)

        except ParseError as error:
            error.complete_coordinates(token.linenum, token.column)
            raise

    def _raw_tokens(self):
        """Pass 1: yield raw tokens as-is, don't try to interpret simple keys, nor look at indentation etc"""
        start = 0
        linenum = 1
        upcoming = None
        while True:
            for upcoming, token in self.headers(linenum, start, upcoming):
                if token is not None:
                    yield token

            if upcoming is None:
                return

            linenum, start, end, line_text = upcoming
            upcoming = None
            for token, offset, text in self.next_match(linenum, start, end, line_text):
                if token is not None:
                    yield token
                    continue

                first_char = text[0]
                if first_char in RESERVED:
                    raise ParseError("Character '%s' is reserved" % first_char, linenum, offset)

                if first_char == '"':
                    linenum, start, end, upcoming, token = _double_quoted(self.generator, linenum, offset + 1, end, line_text)
                    yield token
                    break

                if first_char == "'":
                    linenum, start, end, upcoming, token = _single_quoted(self.generator, linenum, offset + 1, end, line_text)
                    yield token
                    break

                if first_char in '|>':
                    linenum, start, end, upcoming, token = _consume_literal(self.generator, linenum, offset, text)
                    yield token
                    break

                yield ScalarToken(linenum, offset, text)

    def deserialized(self, loader=SimpleLoader):
        loader = loader(self)
        for token in self.tokens():
            func = getattr(loader, token.__class__.__name__, None)
            if func is not None:
                func(token)

        return loader.docs
