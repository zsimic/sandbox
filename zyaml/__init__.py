import codecs
import re
from io import StringIO


NULL = 'null'
FALSE = 'false'
TRUE = 'true'
RE_TYPED = re.compile(r'^(false|true|null|[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$', re.IGNORECASE)


class Token(object):
    value = None
    line = 0
    column = 0

    def __init__(self, buffer=None, line=None, column=None, text=None):
        """
        :param Buffer buffer:
        """
        if buffer:
            self.line = buffer.line
            self.column = buffer.column
            self.set_value(buffer.pop())
        else:
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


class BlockEntry(Token):
    pass


class Scalar(Token):
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


class Directive(Token):
    pass


class Comment(Token):
    pass


class Key(Scalar):
    pass


class Document(Token):
    pass


class Buffer:

    line = 0                # type: int # Line number where buffer starts
    column = 0              # type: int # Column number where buffer starts
    stream = None

    def __bool__(self):
        return bool(self.stream)

    def __repr__(self):
        if self.stream is None:
            return "%s,%s" % (self.line, self.column)
        return "%s,%s %s" % (self.line, self.column, len(self.stream.getvalue()))

    def pop(self):
        if self.stream is None:
            return None
        text = self.stream.getvalue()
        self.stream = None
        return text

    def add(self, scanner):
        """
        :param Scanner scanner: Associated scanner
        """
        if self.stream is None:
            if scanner.current == ' ' or scanner.current == '\n':
                return
            self.line = scanner.line
            self.column = scanner.column
            self.stream = StringIO()
        self.stream.write(scanner.current)


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


class Scanner:

    stream = None           # type: open # Stream being read
    buffer = None
    current = None          # type: chr # Current char
    prev = None             # type: chr # Previously read char
    prev2 = None            # type: chr # We track the prev 2 characters
    line = 0                # type: int # Current line number
    column = 0              # type: int # Current column number
    stack = None

    def __init__(self, stream):
        self.stream = stream

    def __repr__(self):
        return "%s,%s %s" % (self.line, self.column, self.current)

    def pop(self, consume_until=None):
        if consume_until:
            while True:
                self.next_char()
                if not self.current:
                    break
                if self.current in consume_until:
                    break
                self.consume_current()
        return self.buffer.pop()

    def consume_current(self):
        self.buffer.add(self)

    def next_char(self):
        self.prev2 = self.prev
        self.prev = self.current
        if self.prev == '\n':
            self.line += 1
            self.column = 0
        self.column += 1
        self.current = self.stream.read(1)

    def tokens(self, comments=False):
        self.buffer = Buffer()
        self.line = 1
        self.column = 0
        while True:
            self.next_char()
            if not self.current:
                break

            if self.current == '#':
                if self.buffer:
                    yield Scalar(self.buffer)

                text = self.pop('\n')
                if comments:
                    yield Comment(line=self.line, column=self.column, text=text)
                continue

            if self.column == 1 and self.current == '%':
                yield Directive(line=self.line, column=self.column, text=self.pop('#\n'))
                continue

            if self.current == '\n':
                if self.buffer:
                    yield Scalar(self.buffer)
                continue

            if self.current == ':':
                if self.buffer:
                    yield Key(self.buffer)
                continue

            if self.column == 3 and (self.current == '-' or self.current == '.'):
                if self.prev == self.current and self.prev2 == self.current:
                    yield Document(self.buffer)
                    continue

            if self.current == ' ' and self.prev == '-':
                yield BlockEntry(self.buffer)
                continue

            self.consume_current()


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
        if isinstance(token, Key):
            while keys.current and token.column <= keys.current.column:
                keys.pop()
            if keys.current:
                if token.column > keys.current.column:
                    target = keys.current.target
                    current = {}
                    target[keys.current.value] = current
            else:
                current = root
            keys.add(token)
            keys.current.target = current
            continue
        if isinstance(token, Scalar):
            if keys.current:
                target = keys.current.target
                target[keys.current.value] = token.value
            continue
    return tokens
