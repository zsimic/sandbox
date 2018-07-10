import codecs
from io import StringIO


class Token(object):
    text = None

    def __init__(self, line, column):
        self.line = line
        self.column = column

    def __repr__(self):
        if self.text is None:
            return "[%s,%s]" % (self.line, self.column)
        return "[%s,%s] %s" % (self.line, self.column, self.text)


class Scalar(Token):
    def __init__(self, line, column, text):
        super(Scalar, self).__init__(line, column)
        self.text = text


class Comment(Token):
    def __init__(self, line, column, text):
        """
        :param str text: Text of comment
        """
        super(Comment, self).__init__(line, column)
        self.text = text


class Key(Token):
    pass


class Value(Token):
    pass


class StreamEnd(Token):
    pass


class Buffer:

    line = 0                # type: int # Line number where buffer starts
    column = 0              # type: int # Column number where buffer starts
    stream = None

    def __bool__(self):
        return bool(self.stream)

    def scalar(self):
        scalar = Scalar(self.line, self.column, self.stream.getvalue())
        self.line = 0
        self.column = 0
        self.stream = None
        return scalar

    def add(self, scanner):
        """
        :param Scanner scanner: Associated scanner
        """
        if self.stream is None:
            self.line = scanner.line
            self.column = scanner.column
            self.stream = StringIO()
        self.stream.write(scanner.current)


class Scanner:

    stream = None           # type: open # Stream being read
    buffer = None
    current = None          # type: chr # Current char
    prev = None             # type: chr # Previously read char
    prev2 = None            # type: chr # We track the prev 2 characters
    line = 0                # type: int # Current line number
    column = 0              # type: int # Current column number
    indent = 0              # type: int # Track indentation
    prev_indent = 0         # type: int # Previous meaningful indentation
    stream_start = None

    def __init__(self, stream):
        self.stream = stream

    def next_line(self):
        self.line += 1
        self.column = 0
        self.indent = 0

    def next_char(self):
        self.prev2 = self.prev
        self.prev = self.current
        self.current = self.stream.read(1)
        if self.current == '\n':
            self.next_line()
        self.column += 1
        if self.current == ' ':
            self.indent += 1

    def comment(self):
        buffer = StringIO()
        while True:
            self.next_char()
            if not self.current:
                break
            buffer.write(self.current)
            if self.current == '\n':
                break
        text = buffer.getvalue()
        return Comment(self.line, self.column, text)

    def directive(self):
        buffer = StringIO()
        while True:
            self.next_char()
            if not self.current:
                break
            buffer.write(self.current)
            if self.current == '\n':
                break

    def string(self, delimiter):
        buffer = StringIO()
        line = self.line
        column = self.column
        while True:
            self.next_char()
            if not self.current:
                break
            if self.current == '\\':
                continue
            if self.prev == '\\':
                self.current = codecs.decode(self.prev + self.current, "unicode_escape")
            elif self.current == delimiter:
                break
            buffer.write(self.current)
        return Scalar(line, column, buffer.getvalue())

    def tokens(self):
        self.buffer = Buffer()
        self.next_line()
        while True:
            self.next_char()
            if not self.current:
                break

            if self.current == '\n':
                if self.buffer:
                    yield self.buffer.scalar()
                continue

            if self.column == 1 and self.current == '%':
                yield self.directive()
                continue

            if self.current == '#':
                if self.buffer:
                    yield self.buffer.scalar()

                yield self.comment()
                continue

            if not self.buffer and (self.current == '"' or self.current == "'"):
                yield self.string(self.current)
                continue

            if self.current == ':':
                if self.buffer:
                    yield Key(self.line, self.column)
                    yield self.buffer.scalar()
                    yield Value(self.line, self.column)
                continue

            if self.current == '-':
                pass

            if self.buffer or self.current != ' ':
                self.buffer.add(self)

        yield StreamEnd(self.line, self.column)


class Parser:
    pass


def load(stream):
    """
    :param open stream: Stream being read
    """
    scanner = Scanner(stream)
    buffer = StringIO()
    tokens = []
    for token in scanner.tokens():
        buffer.write(str(token))
        tokens.append(token)
    return buffer.getvalue()
