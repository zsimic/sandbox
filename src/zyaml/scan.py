import codecs
import re
from collections import deque


NULL = "null"
FALSE = "false"
TRUE = "true"
RE_TYPED = re.compile(r"^(false|true|null|[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$", re.IGNORECASE)


def parsed_value(text):
    text = text and text.strip()
    if not text:
        return text

    m = RE_TYPED.match(text)
    if not m:
        return text

    text = text.lower()
    if text == NULL:
        return None

    if text == FALSE:
        return False

    if text == TRUE:
        return True

    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


class Token(object):

    def __init__(self, line, column, value=None):
        self.line = line
        self.column = column
        self.value = value

    def __repr__(self):
        if self.value is None:
            if self.line:
                return "%s[%s,%s]" % (self.name(), self.line, self.column)
            return self.name()
        return "%s[%s,%s] %s" % (self.name(), self.line, self.column, self.represented_value())

    def name(self):
        return self.__class__.__name__

    def represented_value(self):
        return str(self.value)

    def process(self, stack):
        """
        :param ParserStack stack:
        """


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    pass


class DocumentStartToken(Token):
    pass


class DocumentEndToken(Token):
    pass


class FlowMappingStartToken(Token):
    pass


class FlowMappingEndToken(Token):
    pass


class FlowEntryToken(Token):
    pass


class BlockEntryToken(Token):
    def process(self, stack):
        if not stack.top:
            return
        stack.top.target = []


class CommentToken(Token):
    pass


class ScalarToken(Token):

    def __init__(self, line, column, text=None, style=None):
        super(ScalarToken, self).__init__(line, column, text)
        self.style = style
        self.is_key = False

    def name(self):
        return "KeyToken" if self.is_key else self.__class__.__name__

    def represented_value(self):
        if self.style is None:
            return str(self.value)
        if self.style == '"':
            return '"%s"' % self.value
        return "'%s'" % self.value

    def process(self, stack):
        if self.is_key:
            stack.unwind(self.column)
            if stack.top:
                if self.column > stack.top.column:
                    target = stack.top.target
                    stack.current = {}
                    if isinstance(target, dict):
                        target[stack.top.value] = stack.current
                    else:
                        target.append(self.value)
            else:
                stack.current = stack.root
            stack.push(self)
            stack.top.target = stack.current
            return

        if stack.top:
            target = stack.top.target
            if isinstance(target, dict):
                target[stack.top.value] = self.value
            else:
                target.append(self.value)


class ParserStack:
    def __init__(self):
        self.root = {}
        self.current = None
        self.top = None
        self.items = deque()

    def push(self, token):
        """
        :param Token token:
        """
        self.top = token
        self.items.append(token)

    def pop(self):
        self.top = self.items.pop() if self.items else None
        return self.top

    def unwind(self, column):
        while self.top and column <= self.top.column:
            self.pop()

    def process(self, token):
        """
        :param Token token: Token to process
        """
        return token.process(self)


class Processor:
    def __init__(self, buffer, line, column, pos, current):
        self.buffer = buffer
        self.line = line
        self.column = column
        self.pos = pos
        self.current = current

    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, next):
        return True

    def __call__(self, line, column, pos, prev, current, next):
        return None


class CommentProcessor(Processor):
    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, next):
        return current == "#" and (prev == " " or prev == "\n")

    def __call__(self, line, column, pos, prev, current, next):
        if current == "\n":
            return CommentToken(self.line, self.column, self.buffer[self.pos:pos].strip())


class FlowProcessor(Processor):
    def __init__(self, buffer, line, column, pos, current):
        super(FlowProcessor, self).__init__(buffer, line, column, pos, current)
        self.tokens = [FlowMappingStartToken(line, column)]  # type: list[Token]
        self.subprocessor = None
        self.simple_key = None
        self.ender = "}" if self.current == "{" else "]"

    def consume_simple_key(self, pos, is_key=False):
        if self.simple_key is not None:
            self.tokens.append(massaged_key(self.buffer, self.simple_key, pos, is_key=is_key))
            self.simple_key = None

    def __call__(self, line, column, pos, prev, current, next):
        if self.subprocessor is not None:
            result = self.subprocessor(line, column, pos, prev, current, next)
            if result is not None:
                self.subprocessor = None
                self.tokens.append(result)

        elif current == self.ender:
            self.consume_simple_key(pos)
            self.tokens.append(FlowMappingEndToken(line, column))
            return self.tokens

        elif self.simple_key is None:
            if current in PROCESSORS:
                self.subprocessor = get_processor(self.buffer, line, column, pos, prev, current, next)

            elif current != ":" or next not in " \n":
                self.simple_key = ScalarToken(line, column, pos)

        elif current == ":":
            if next in " \n":
                self.consume_simple_key(pos, is_key=True)

        elif current == ",":
            self.consume_simple_key(pos)
            self.tokens.append(FlowEntryToken(line, column))


class DoubleQuoteProcessor(Processor):
    def __call__(self, line, column, pos, prev, current, next):
        if current == '"' and prev != "\\":
            text = self.buffer[self.pos + 1:pos]
            text = codecs.decode(text, "unicode_escape")
            return ScalarToken(line, column, text, style='"')


class SingleQuoteProcessor(Processor):
    def __call__(self, line, column, pos, prev, current, next):
        if current == "'" and prev != "'" and next != "'":
            text = self.buffer[self.pos + 1:pos].replace("''", "'")
            return ScalarToken(line, column, text, style="'")


class ParseError(Exception):
    def __init__(self, line, column, message):
        self.line = line
        self.column = column
        self.message = message


PROCESSORS = {
    " ": None,
    "\n": None,
    "#": CommentProcessor,
    "{": FlowProcessor,
    "[": FlowProcessor,
    '"': DoubleQuoteProcessor,
    "'": SingleQuoteProcessor,
}


def get_processor(buffer, line, column, pos, prev, current, next):
    processor = PROCESSORS.get(current)
    if processor is not None and processor.is_applicable(line, column, pos, prev, current, next):
        return processor(buffer, line, column, pos, current)


def massaged_key(buffer, key, pos, is_key=False):
    key.value = buffer[key.value:pos].strip()
    key.is_key = is_key
    if not is_key and key.style is None:
        key.value = parsed_value(key.value)
    return key


def scan_tokens(buffer):
    line = 1
    column = 0
    pos = -1
    prev = processor = simple_key = None
    current = " "
    yield StreamStartToken(line, column)

    for next in buffer:
        if processor is not None:
            result = processor(line, column, pos, prev, current, next)
            if result is not None:
                if isinstance(result, list):
                    for token in result:
                        yield token
                else:
                    yield result
                processor = None

        elif simple_key is None:
            if current in PROCESSORS:
                processor = get_processor(buffer, line, column, pos, prev, current, next)

            elif current == "-" and next in " \n":
                yield BlockEntryToken(line, column)

            else:
                simple_key = ScalarToken(line, column, pos)

        elif current == "#":
            if prev in " \n":
                yield massaged_key(buffer, simple_key, pos)
                simple_key = None
                processor = CommentProcessor(buffer, line, column, pos, current)

        elif current == ":":
            if next in " \n":
                yield massaged_key(buffer, simple_key, pos, is_key=True)
                simple_key = None

        if current == "\n":
            if simple_key is not None:
                simple_key = massaged_key(buffer, simple_key, pos)
                if simple_key.column == 1:
                    if simple_key.value == "---":
                        yield DocumentStartToken(line, column)
                        simple_key = None
                    elif simple_key.value == "...":
                        yield DocumentEndToken(line, column)
                        simple_key = None
                if simple_key is not None:
                    yield simple_key
                    simple_key = None
            line += 1
            column = 1

        else:
            column += 1

        pos += 1
        prev = current
        current = next

    if processor is not None:
        result = processor(line, column, pos, prev, current, None)
        if result is not None:
            if isinstance(result, list):
                for token in result:
                    yield token
            else:
                yield result

    elif simple_key is not None:
        yield massaged_key(buffer, simple_key, pos)

    yield StreamEndToken(line, column)
