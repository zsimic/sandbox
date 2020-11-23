import collections

from zyaml.loader import *
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


class BlockScanner(object):
    def __init__(self, parent):
        self.parent = parent  # type: Scanner
        self.nesting_level = None
        self.structures = collections.deque()

    def __repr__(self):
        structs = " / ".join("%s%s" % (s.mnemonic, s.indent) for s in self.structures)
        return "block nesting: %s - %s" % (self.nesting_level, structs)

    def pass2_structure(self, token, token_type):
        i = self.nesting_level
        while i is not None and i > token.indent:
            try:
                struct = self.structures.pop()
                i = struct.indent
                if i > token.indent:
                    yield struct.terminator(self.parent, token.linenum, i)

                else:
                    self.structures.append(struct)

            except IndexError:
                i = None

        self.nesting_level = i
        if i != token.indent:
            struct = token_type(self.parent, token.linenum, token.indent)
            self.nesting_level = token.indent
            self.structures.append(struct)
            yield struct

    def pass2_pop_structure(self, token):
        i = self.nesting_level
        while i is not None and i < token.indent:
            try:
                i = self.structures.pop().indent
                yield BlockEndToken(self.parent, token.linenum, i)

            except IndexError:
                i = None

        self.nesting_level = i

    def pass2_pop_all(self, token):
        while self.structures:
            yield BlockEndToken(self.parent, token.linenum, self.structures.pop().indent)


class FlowScanner(object):
    def __init__(self, parent):
        self.parent = parent  # type: Scanner

    def __repr__(self):
        return "flow"


class Scanner(object):
    def __init__(self, stream):
        if hasattr(stream, "splitlines"):
            stream = stream.splitlines()

        self.generator = enumerate(stream, start=1)
        self.block_scanner = BlockScanner(self)
        self.flow_scanner = FlowScanner(self)
        self.is_block_mode = True
        self.mode = self.block_scanner
        self.line_regex = RE_BLOCK_SEP
        self.flow_ender = collections.deque()
        self.started_doc = False
        self.simple_key = None
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
            ":": ColonToken,
        }

    def __repr__(self):
        return str(self.mode)

    def add_simple_key(self, token):
        if self.simple_key is None:
            self.simple_key = token

        else:
            self.simple_key.append_line(token.value)

    def popped_simple_key(self):
        s = self.simple_key
        self.simple_key = None
        return s

    def pass2_docstart(self, token, pop_simple_key=True):
        if not self.started_doc:
            self.started_doc = True
            yield DocumentStartToken(self, token.linenum, 0)

        s = self.simple_key
        if s is not None and (pop_simple_key or token.indent < s.indent):
            yield s
            self.simple_key = None

    def pass2_docend(self, token):
        if self.simple_key is not None:
            yield self.simple_key
            self.simple_key = None

        if self.started_doc:
            self.started_doc = False
            for t in self.block_scanner.pass2_pop_all(token):
                yield t

            if not isinstance(token, DocumentEndToken):
                yield DocumentEndToken(self, token.linenum + 1, 0)

    def push_flow_ender(self, ender):
        if self.is_block_mode:
            self.mode = self.flow_scanner
            self.is_block_mode = False
            self.line_regex = RE_FLOW_SEP

        self.flow_ender.append(ender)

    def pop_flow_ender(self, found):
        if self.is_block_mode:
            raise ParseError("'%s' without corresponding opener" % found)

        expected = self.flow_ender.pop()
        if not self.flow_ender:
            self.mode = self.block_scanner
            self.is_block_mode = True
            self.line_regex = RE_BLOCK_SEP

        if expected != found:
            raise ParseError("Expecting '%s', but found '%s'" % (expected, found))

    @staticmethod
    def _checked_string(linenum, start, end, line_text, token):
        if start >= end:
            line_text = None
            start = 0

        return linenum, start, end, line_text, token

    def _double_quoted(self, linenum, start, end, line_text):
        token = ScalarToken(self, linenum, start, "", style='"')
        try:
            if start < end and line_text[start] == '"':  # Empty string
                return self._checked_string(linenum, start + 1, end, line_text, token)

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
                    return self._checked_string(linenum, start, end, line_text, token)

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
        try:
            if start < end and line_text[start] == "'":  # Empty string
                return self._checked_string(linenum, start + 1, end, line_text, token)

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
                    return self._checked_string(linenum, start, end, line_text, token)

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

                return linenum, 0, end, line_text, token

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
                if self.is_block_mode:
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

    def headers(self, linenum, start, end, line_text):
        while True:
            if line_text is None:
                try:
                    linenum, line_text = next(self.generator)
                    start = 0

                except StopIteration:
                    yield None, None
                    return

            m = RE_HEADERS.match(line_text) if start == 0 else None
            if m is None:
                m = RE_BLOCK_SEQUENCE.match(line_text, start)
                while m is not None:
                    start = m.span(1)[0] + 1
                    yield None, DashToken(self, linenum, start)
                    first_non_blank = m.span(2)[1] - 1
                    if first_non_blank > 0 and line_text[first_non_blank] != "-":
                        start = first_non_blank
                        break

                    m = RE_BLOCK_SEQUENCE.match(line_text, start)

                m = RE_CONTENT.match(line_text, start)
                first_non_blank, end = m.span(1)
                if start == 0 and first_non_blank == end and self.simple_key is not None:
                    yield None, ScalarToken(self, linenum, start, "")
                    line_text = None
                    continue

                yield (linenum, first_non_blank, end, line_text), None
                return

            start, end = m.span(1)
            matched = line_text[start:end]
            if matched[0] == "-":
                yield None, DocumentStartToken(self, linenum, 0)
                if matched[-1] == " ":
                    start = end

                else:
                    line_text = None

            elif matched[0] == ".":
                yield None, DocumentEndToken(self, linenum, 0)
                if matched[-1] == " ":
                    start = end

                else:
                    line_text = None

            elif matched[-1] == "%":
                yield None, DirectiveToken(self, linenum, end, line_text)
                line_text = None

            else:
                assert matched[-1] == "#"
                line_text = None

        yield (linenum, start, end, line_text), None

    def tokens(self):
        t2 = StreamStartToken(self, 1, 0)
        yield t2
        for t1 in self.first_pass():
            for t2 in t1.second_pass(self):
                yield t2

        for t2 in self.pass2_docend(t2):
            yield t2

        yield StreamEndToken(self, t2.linenum, 0)

    def first_pass(self):
        """Yield raw tokens as-is, don't try to interpret simple keys, look at indentation etc"""
        start = end = offset = 0
        linenum = 1
        upcoming = None
        try:
            while True:
                for upcoming, token in self.headers(linenum, start, end, upcoming):
                    if token is not None:
                        yield token

                if upcoming is None:
                    return

                linenum, start, end, line_text = upcoming
                upcoming = None
                for matched, offset, text in self.next_match(start, end, line_text):
                    tokenizer = self.tokenizer_map.get(matched)
                    if tokenizer is not None:
                        yield tokenizer(self, linenum, offset, text)

                    else:
                        matched = text[0]
                        if matched in RESERVED:
                            raise ParseError("Character '%s' is reserved" % matched, linenum, offset)

                        elif matched == '"':
                            linenum, start, end, upcoming, token = self._double_quoted(linenum, offset + 1, end, line_text)
                            yield token
                            break

                        elif matched == "'":
                            linenum, start, end, upcoming, token = self._single_quoted(linenum, offset + 1, end, line_text)
                            yield token
                            break

                        elif matched in '|>':
                            linenum, start, end, upcoming, token = self._consume_literal(linenum, offset, text)
                            yield token
                            break

                        else:
                            yield ScalarToken(self, linenum, offset, text)

        except ParseError as error:
            error.auto_complete(linenum, offset)
            raise

    def deserialized(self, loader=SimpleLoader):
        token = None
        try:
            loader = loader(self)
            for token in self.tokens():
                name = token.__class__.__name__
                func = getattr(loader, name, None)
                if func is not None:
                    func(token)

            return loader.docs

        except ParseError as error:
            error.auto_complete(token)
            raise
