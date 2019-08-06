import codecs
import re
from collections import deque


NULL = "null"
FALSE = "false"
TRUE = "true"
RE_TYPED = re.compile(r"^(false|true|null|[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$", re.IGNORECASE)


def parsed_value(text):
    """
    :param str|None text: Text to interpret
    :return str|int|float|None: Parsed value
    """
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
    """Scanned token, visitor pattern is used for parsing"""

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

    def _visit(self, stack):
        """
        :param ParserStack stack: Process this token on given 'stack' (using visitor pattern)
        """


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    def _visit(self, stack):
        stack.pop_doc()


class DocumentStartToken(Token):
    def _visit(self, stack):
        stack.pop_doc()


class DocumentEndToken(Token):
    def _visit(self, stack):
        stack.pop_doc()


class FlowMappingStartToken(Token):
    def _visit(self, stack):
        stack.push_target(None, {})


class FlowSequenceStartToken(Token):
    def _visit(self, stack):
        stack.push_target(None, [])


class FlowEndToken(Token):
    def _visit(self, stack):
        stack.pop()


class FlowEntryToken(Token):
    pass


class BlockEntryToken(Token):
    def _visit(self, stack):
        if stack.top is None or not isinstance(stack.top.target, list):
            stack.push_target(self.column, [])


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

    def _visit(self, stack):
        stack.push_scalar(self.column, self.value, self.is_key)


class ValueContainer:
    def __init__(self, indent, target):
        self.indent = indent
        self.target = target
        self.last_key = None

    def __repr__(self):
        if self.target is None:
            result = "undetermined"
        elif isinstance(self.target, list):
            result = "list"
        elif isinstance(self.target, dict):
            result = "map"
        else:
            result = "str"
        return "%s, indent: %s" % (result, "flow" if self.indent is None else self.indent)

    @property
    def is_list(self):
        return isinstance(self.target, list)

    @property
    def is_map(self):
        return isinstance(self.target, dict)

    def set_key(self, key):
        if not isinstance(self.target, dict):
            raise ParseError("Key not allowed here")
        if self.last_key is not None:
            raise ParseError("Previous key '%s' was not used" % self.last_key)
        self.last_key = key

    def set_value(self, value):
        if isinstance(self.target, dict):
            if self.last_key is None:
                raise ParseError("No key for specified value")
            self.target[self.last_key] = value
            self.last_key = None

        elif isinstance(self.target, list):
            self.target.append(value)

        else:
            self.target = "%s %s" % (self.target, value)


class ParserStack:
    def __init__(self):
        self.docs = []
        self.top = None  # type: ValueContainer
        self.stack = deque()

    def push_target(self, indent,  target):
        self.push(ValueContainer(indent, target))

    def push_scalar(self, indent, value, is_key):
        if is_key:
            if self.top is None or not self.top.is_map:
                self.push(ValueContainer(indent, {}))
        if self.top is None:
            self.push(ValueContainer(indent, ""))
        if is_key:
            self.top.set_key(value)
        else:
            self.top.set_value(value)

    def push(self, container):
        """
        :param ValueContainer container:
        """
        if self.top and self.top.indent:
            while container.indent < self.top.indent:
                self.pop(next=container)
        self.top = container
        self.stack.append(container)

    def pop_until(self, indent):
        pass

    def pop(self, next=None):
        popped = self.stack.pop()
        if popped.last_key is not None:
            if next is None:
                popped.set_value(next)
            else:
                raise ParseError("Key '%s' was not used" % popped.last_key)
        self.top = self.stack[-1] if self.stack else None
        if popped and self.top:
            self.top.set_value(popped.target)
        return popped

    def pop_doc(self):
        prev = None
        while self.top:
            prev = self.top
            self.pop()
        self.docs.append(prev.target if prev else None)

    def deserialized(self, tokens):
        token = None
        try:
            for token in tokens:
                token._visit(self)
            return simplified(self.docs)

        except ParseError as error:
            error.near = token
            raise


class Processor:
    def __init__(self, settings, line, column, pos, current):
        self.settings = settings  # type: ScanSettings
        self.line = line  # type: int
        self.column = column  # type: int
        self.pos = pos  # type: int
        self.current = current  # type: str

    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, next):
        return True

    def contents(self, start, end):
        return self.settings.contents(start, end)

    def __call__(self, line, column, pos, prev, current, next):
        return None


class CommentProcessor(Processor):

    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, next):
        return current == "#" and (prev == " " or prev == "\n")

    def __call__(self, line, column, pos, prev, current, next):
        if current == "\n":
            if not self.settings.yield_comments:
                return []
            return CommentToken(self.line, self.column, self.contents(self.pos, pos).strip())


class FlowProcessor(Processor):
    def __init__(self, settings, line, column, pos, current):
        super(FlowProcessor, self).__init__(settings, line, column, pos, current)
        if current == "{":
            self.end_char = "}"
            self.tokens = [FlowMappingStartToken(line, column)]
        else:
            self.end_char = "]"
            self.tokens = [FlowSequenceStartToken(line, column)]
        self.subprocessor = None
        self.simple_key = None

    def consume_simple_key(self, pos, is_key=False):
        if self.simple_key is not None:
            self.tokens.append(massaged_key(self.settings, self.simple_key, pos, is_key=is_key))
            self.simple_key = None

    def __call__(self, line, column, pos, prev, current, next):
        if self.subprocessor is not None:
            result = self.subprocessor(line, column, pos, prev, current, next)
            if result is not None:
                self.subprocessor = None
                if isinstance(result, list):
                    self.tokens.extend(result)
                else:
                    self.tokens.append(result)

        elif current == self.end_char:
            self.consume_simple_key(pos)
            self.tokens.append(FlowEndToken(line, column))
            return self.tokens

        elif self.simple_key is None:
            if current in PROCESSORS:
                self.subprocessor = get_processor(self.settings, line, column, pos, prev, current, next)

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
            text = self.contents(self.pos + 1, pos)
            text = codecs.decode(text, "unicode_escape")
            return ScalarToken(line, column, text, style='"')


class SingleQuoteProcessor(Processor):
    def __call__(self, line, column, pos, prev, current, next):
        if current == "'" and prev != "'" and next != "'":
            text = self.contents(self.pos + 1, pos).replace("''", "'")
            return ScalarToken(line, column, text, style="'")


class ParseError(Exception):
    def __init__(self, message):
        self.message = message
        self.near = None

    def __str__(self):
        if self.near is None:
            return self.message
        return "%s, line %s column %s" % (self.message, self.near.line, self.near.column)


PROCESSORS = {
    " ": None,
    "\n": None,
    "#": CommentProcessor,
    "{": FlowProcessor,
    "[": FlowProcessor,
    '"': DoubleQuoteProcessor,
    "'": SingleQuoteProcessor,
}


def get_processor(settings, line, column, pos, prev, current, next):
    processor = PROCESSORS.get(current)
    if processor is not None and processor.is_applicable(line, column, pos, prev, current, next):
        return processor(settings, line, column, pos, current)


def massaged_key(settings, key, pos, is_key=False):
    key.value = settings.contents(key.value, pos).strip()
    key.is_key = is_key
    if not is_key and key.style is None:
        key.value = parsed_value(key.value)
    return key


class ScanSettings:
    def __init__(self, yield_comments=False):
        self.yield_comments = yield_comments
        self._buffer = None

    def contents(self, start, end):
        return self._buffer[start:end]


def scan_tokens(buffer, settings=None):
    line = 1
    column = 0
    pos = -1
    prev = processor = simple_key = None
    current = " "

    if settings is None:
        settings = ScanSettings()

    settings._buffer = buffer

    yield StreamStartToken(line, column)

    for next in buffer:
        if processor is not None:
            result = processor(line, column, pos, prev, current, next)
            if result is not None:
                processor = None
                if isinstance(result, list):
                    for token in result:
                        yield token
                else:
                    yield result

        elif simple_key is None:
            if current in PROCESSORS:
                processor = get_processor(settings, line, column, pos, prev, current, next)

            elif current == "-" and next in " \n":
                yield BlockEntryToken(line, column)

            else:
                simple_key = ScalarToken(line, column, pos)

        elif current == "#":
            if prev in " \n":
                yield massaged_key(settings, simple_key, pos)
                simple_key = None
                processor = CommentProcessor(settings, line, column, pos, current)

        elif current == ":":
            if next in " \n":
                yield massaged_key(settings, simple_key, pos, is_key=True)
                simple_key = None

        if current == "\n":
            if simple_key is not None:
                simple_key = massaged_key(settings, simple_key, pos)
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
        yield massaged_key(settings, simple_key, pos)

    yield StreamEndToken(line, column)


def load(stream):
    """
    :param str|file stream: Stream or contents to load
    """
    if hasattr(stream, "read"):
        stream = stream.read()
    return load_string(stream)


def load_string(contents, first_doc_only=False):
    """
    :param str contents: Yaml to deserialize
    """
    settings = ScanSettings()
    return ParserStack().deserialized(scan_tokens(contents))


def load_path(path):
    """
    :param str path: Path to file to deserialize
    """
    with open(path) as fh:
        return load_string(fh.read())


def simplified(docs):
    if isinstance(docs, list) and len(docs) == 1:
        return docs[0]
    return docs
