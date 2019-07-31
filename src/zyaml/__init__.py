import codecs
import re

try:
    import StringIO

    StringIO = StringIO.StringIO

except ImportError:
    from io import StringIO


NULL = "null"
FALSE = "false"
TRUE = "true"
RE_TYPED = re.compile(r"^(false|true|null|[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$", re.IGNORECASE)


class Token(object):

    value = None
    line = 0
    column = 0

    def __init__(self, line, column, text=None):
        self.line = line
        self.column = column
        self.set_value(text)

    def __repr__(self):
        if self.value is None:
            if self.line:
                return "%s[%s,%s]" % (self.__class__.__name__, self.line, self.column)
            return self.__class__.__name__
        return "%s[%s,%s] %s" % (self.__class__.__name__, self.line, self.column, self.value)

    def set_value(self, value):
        """
        :param str value:
        """
        self.value = value


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    pass


class BlockSequenceStartToken(Token):
    pass


class BlockEndToken(Token):
    pass


class BlockEntryToken(Token):
    pass


class ScalarToken(Token):
    def set_value(self, value):
        """
        :param str value:
        """
        self.value = value and value.strip()
        if not self.value:
            return

        if len(self.value) > 1:
            quote = self.value[0]
            if (quote == '"' or quote == "'") and self.value[-1] == quote:
                self.value = codecs.decode(self.value[1:-1], "unicode_escape")
                return

        m = RE_TYPED.match(self.value)
        if not m:
            return

        self.value = self.value.lower()
        if self.value == NULL:
            self.value = None

        elif self.value == FALSE:
            self.value = False
            return

        elif self.value == TRUE:
            self.value = True

        else:
            try:
                self.value = int(self.value)
                return
            except ValueError:
                pass

            self.value = float(self.value)


class DirectiveToken(Token):
    pass


class CommentToken(Token):
    pass


class KeyToken(ScalarToken):
    pass


class DocumentToken(Token):
    pass


class KeyStack:
    def __init__(self):
        self.items = []
        self.current = None

    def add(self, key):
        """
        :param Key key:
        """
        self.current = key
        self.items.append(key)

    def pop(self):
        if self.items:
            self.items.pop()
        if self.items:
            self.current = self.items[-1]
        else:
            self.current = None


class LexToken:

    __slots__ = ["column", "line", "start", "end", "value"]

    def __init__(self, parent, value=None):
        """
        :param Scanner parent:
        """
        self.column = parent.column
        self.end = None
        self.line = parent.line
        self.start = parent.pos
        self.value = value


class Scanner:

    def scan1(self):
        pos = 0
        buffer = self.buffer
        size = self.size
        column = 1
        line = 1
        while pos < size:
            current = buffer[pos]
            if current == "\n":
                line += 1
                column = 1
            else:
                column += 1
            pos += 1

    def scan2(self):
        while self.pos < self.size:
            self.advance()

    def lexemes(self):
        anchor = 0
        self.skip_whitespace()

        while self.pos < self.size:
            if self.current == "#":
                token = LexToken(self)
                self.find_eol()
                token.end = self.pos
                token.value = self.buffer[token.start:token.end].strip()
                yield token
                self.skip_whitespace()

            elif self.column == 3 and (self.current == "-" or self.current == ".") and self.prev == self.prev2 == self.current:
                # yield DocumentToken(line, column, buffer[start:pos])
                token = LexToken(self)
                anchor = self.pos

            elif self.current == " " or self.current == "\n":
                if self.prev == ":":
                    # yield KeyToken(line, column, buffer[start:pos])
                    anchor = self.pos

                elif self.prev == "-":
                    # yield BlockEntryToken(line, column, buffer[start:pos])
                    anchor = self.pos

            elif self.current == "\n":
                if anchor < self.pos:
                    # yield ScalarToken(line, column, buffer[start:pos])
                    anchor = self.pos

            else:
                self.advance()

    def pop(self, consume_until, buffer, size, start):
        pos = start
        lines = 0
        while pos < size:
            current = buffer[pos]
            pos += 1
            if current == "\n":
                lines += 1
            if current in consume_until:
                break
        return buffer[start:pos], pos, lines

    def next_lexeme(self, buffer, size, start):
        pos = start
        lines = 1
        while pos < size:
            current = buffer[pos]
            pos += 1
            if current == "\n":
                lines += 1
            if current == "#":
                return self.pop("\n", buffer, size, pos)
            if current == "'":
                return self.pop("'\n", buffer, size, pos)
            if current == '"':
                return self.pop('"\n', buffer, size, pos)

    def tokens(self, comments=False):
        if hasattr(self.source, "read"):
            buffer = self.source.read()

        else:
            buffer = self.source

        yield StreamStartToken(1, 1)
        size = len(buffer)
        text, pos, lines = self.next_lexeme(buffer, size, 0)
        while text is not None:
            text, pos, lines = self.next_lexeme(buffer, size, pos)

        start = 0
        pos = -1
        line = 1
        column = 0
        prev2 = prev = None
        skip_to = None

        for current in buffer:
            pos += 1
            if prev == "\n":
                line += 1
                column = 1

            else:
                column += 1

            if skip_to is not None and current != skip_to:
                continue

            if column == 1:
                if current == "#":
                    if start < pos:
                        yield ScalarToken(line, column, buffer[start:pos])
                        start = pos
                    skip_to = "\n"
                    text, pos = self.pop("\n", buffer, pos)
                    # if comments:
                    #     yield CommentToken(line, column, text)

            elif column == 3 and (current == "-" or current == ".") and prev == prev2 == current:
                yield DocumentToken(line, column, buffer[start:pos])
                start = pos

            elif current == " " or current == "\n":
                if prev == ":":
                    yield KeyToken(line, column, buffer[start:pos])
                    start = pos

            elif current == " ":
                if prev == "-":
                    yield BlockEntryToken(line, column, buffer[start:pos])
                    start = pos

            elif self.current == "\n":
                if start < pos:
                    yield ScalarToken(line, column, buffer[start:pos])
                    start = pos

            prev2 = prev
            prev = current

        yield StreamEndToken(line, column)

        if start < pos:
            yield ScalarToken(line, column, buffer[start:pos])


class Parser:
    pass


def load(stream):
    """
    :param open stream: Stream being read
    """
    scanner = Scanner(stream)
    root = {}
    current = root
    tokens = []
    keys = KeyStack()
    for token in scanner.tokens():
        tokens.append(token)
        if isinstance(token, KeyToken):
            while keys.current and token.column <= keys.current.column:
                keys.pop()
            if keys.current:
                if token.column > keys.current.column:
                    target = keys.current.target
                    current = {}
                    if isinstance(target, dict):
                        target[keys.current.value] = current
                    else:
                        target.append(token.value)
            else:
                current = root
            keys.add(token)
            keys.current.target = current
            continue

        if isinstance(token, ScalarToken):
            if keys.current:
                target = keys.current.target
                if isinstance(target, dict):
                    target[keys.current.value] = token.value
                else:
                    target.append(token.value)
            continue

        if isinstance(token, BlockEntryToken):
            if not keys.current:
                continue
            keys.current.target = []

    return root
