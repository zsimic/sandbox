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

    def _process(self, root):
        """
        :param RootNode root: Process this token on given 'root' node
        """


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    def _process(self, root):
        root.pop_doc()


class DocumentStartToken(Token):
    def _process(self, root):
        root.pop_doc()


class DocumentEndToken(Token):
    def _process(self, root):
        root.pop_doc()


class FlowMappingStartToken(Token):
    def _process(self, root):
        root.push(MapNode(None))


class FlowSequenceStartToken(Token):
    def _process(self, root):
        root.push(ListNode(None))


class FlowEndToken(Token):
    def _process(self, root):
        root.pop()


class FlowEntryToken(Token):
    pass


class BlockEntryToken(Token):
    def _process(self, root):
        root.ensure_node(self.column + 1, ListNode)


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

    def _process(self, root):
        if self.is_key:
            root.push_key(self.column, self.value)
        else:
            root.push_value(self.column, self.value)


class ParseNode:
    def __init__(self, indent):
        self.indent = indent
        self.prev = None
        self.is_map = False
        self.is_temp = False
        self.target = self._get_target()

    def __repr__(self):
        result = "%s%s%s" % (self.__class__.__name__[0], "" if self.indent is None else self.indent, "*" if self.is_temp else "")
        if self.prev:
            result = "%s / %s" % (result, self.prev)
        return result

    def _get_target(self):
        pass

    def set_key(self, key):
        raise ParseError("Key not allowed here")

    def set_value(self, value):
        pass


class ListNode(ParseNode):
    def _get_target(self):
        return []

    def set_value(self, value):
        self.target.append(value)


class MapNode(ParseNode):
    def __init__(self, indent):
        super(MapNode, self).__init__(indent)
        self.is_map = True
        self.last_key = None

    def _get_target(self):
        return {}

    def set_key(self, key):
        if self.last_key is not None:
            self.target[self.last_key] = None
        self.last_key = key

    def set_value(self, value):
        if self.last_key is None:
            raise ParseError("No key for specified value")
        self.target[self.last_key] = value
        self.last_key = None


class ScalarNode(ParseNode):
    def _get_target(self):
        return ""

    def set_value(self, value):
        if self.target:
            self.target = "%s %s" % (self.target, value)
        else:
            self.target = value


class RootNode(ListNode):
    def __init__(self):
        super(RootNode, self).__init__(0)
        self.head = None  # type: ParseNode | None

    def __repr__(self):
        return str(self.head or "/")

    def needs_new_node(self, indent, type):
        if self.head is None:
            return True
        if self.head.__class__ is not type:
            return True
        if indent is None:
            return self.head.indent is not None
        if self.head.indent is None:
            return False
        return indent > self.head.indent

    def needs_pop(self, indent, type):
        if indent is None or self.head is None or self.head.indent is None:
            return False
        # if self.head.indent == indent:
        #     return self.head.__class__ is not type
        return self.head.indent > indent

    def ensure_node(self, indent, type):
        while self.needs_pop(indent, type):
            self.pop()
        if self.needs_new_node(indent, type):
            self.push(type(indent))

    def push_key(self, indent, key):
        self.ensure_node(indent, MapNode)
        self.head.set_key(key)

    def push_value(self, indent, value):
        if self.head is None:
            self.push(ScalarNode(indent))
        self.head.set_value(value)
        if self.head.is_temp:
            self.pop()

    def push(self, node):
        """
        :param ParseNode node:
        """
        if self.head:
            if self.head.indent is None:
                node.is_temp = node.indent is not None
            elif node.indent is not None:
                while node.indent < self.head.indent:
                    self.pop()
        node.prev = self.head
        self.head = node

    def pop(self):
        popped = self.head
        self.head = popped.prev
        if popped and self.head:
            self.head.set_value(popped.target)
        return popped

    def pop_doc(self):
        prev = None
        while self.head:
            prev = self.head
            self.pop()
        self.target.append(prev.target if prev else None)

    def deserialized(self, tokens):
        token = None
        try:
            for token in tokens:
                token._process(self)
            return simplified(self.target)

        except ParseError as error:
            error.near = token
            raise


class Tokenizer:
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


class CommentTokenizer(Tokenizer):

    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, next):
        return current == "#" and (prev == " " or prev == "\n")

    def __call__(self, line, column, pos, prev, current, next):
        if current == "\n":
            if not self.settings.yield_comments:
                return []
            return [CommentToken(self.line, self.column, self.contents(self.pos, pos).strip())]


class FlowTokenizer(Tokenizer):
    def __init__(self, settings, line, column, pos, current):
        super(FlowTokenizer, self).__init__(settings, line, column, pos, current)
        if current == "{":
            self.end_char = "}"
            self.tokens = [FlowMappingStartToken(line, column)]
        else:
            self.end_char = "]"
            self.tokens = [FlowSequenceStartToken(line, column)]
        self.subtokenizer = None
        self.simple_key = None

    def consume_simple_key(self, pos, is_key=False):
        if self.simple_key is not None:
            self.tokens.append(massaged_key(self.settings, self.simple_key, pos, is_key=is_key))
            self.simple_key = None

    def __call__(self, line, column, pos, prev, current, next):
        if self.subtokenizer is not None:
            result = self.subtokenizer(line, column, pos, prev, current, next)
            if result is not None:
                self.subtokenizer = None
                self.tokens.extend(result)

        elif current == self.end_char:
            self.consume_simple_key(pos)
            self.tokens.append(FlowEndToken(line, column))
            return self.tokens

        elif self.simple_key is None:
            if current in TOKENIZERS:
                self.subtokenizer = get_tokenizer(self.settings, line, column, pos, prev, current, next)

            elif current == ",":
                self.tokens.append(FlowEntryToken(line, column))

            elif current != ":" or next not in " \n":
                self.simple_key = ScalarToken(line, column, pos)

        elif current == ":":
            if next in " \n":
                self.consume_simple_key(pos, is_key=True)

        elif current == ",":
            self.consume_simple_key(pos)
            self.tokens.append(FlowEntryToken(line, column))


class DoubleQuoteTokenizer(Tokenizer):
    def __call__(self, line, column, pos, prev, current, next):
        if current == '"' and prev != "\\":
            text = self.contents(self.pos + 1, pos)
            text = codecs.decode(text, "unicode_escape")
            return [ScalarToken(line, column, text, style='"')]


class SingleQuoteTokenizer(Tokenizer):
    def __call__(self, line, column, pos, prev, current, next):
        if current == "'" and prev != "'" and next != "'":
            text = self.contents(self.pos + 1, pos).replace("''", "'")
            return [ScalarToken(line, column, text, style="'")]


class ParseError(Exception):
    def __init__(self, message):
        self.message = message
        self.near = None

    def __str__(self):
        if self.near is None:
            return self.message
        return "%s, line %s column %s" % (self.message, self.near.line, self.near.column)


TOKENIZERS = {
    " ": None,
    "\n": None,
    "#": CommentTokenizer,
    "{": FlowTokenizer,
    "[": FlowTokenizer,
    '"': DoubleQuoteTokenizer,
    "'": SingleQuoteTokenizer,
}


def get_tokenizer(settings, line, column, pos, prev, current, next):
    tokenizer = TOKENIZERS.get(current)
    if tokenizer is not None and tokenizer.is_applicable(line, column, pos, prev, current, next):
        return tokenizer(settings, line, column, pos, current)


def massaged_key(settings, key, pos, is_key=False):
    key.value = settings.contents(key.value, pos).strip()
    if key.column == 1:
        if key.value == "---":
            return DocumentStartToken(key.line, key.column)
        if key.value == "...":
            return DocumentEndToken(key.line, key.column)
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
    prev = tokenizer = simple_key = None
    current = " "

    if settings is None:
        settings = ScanSettings()

    settings._buffer = buffer

    yield StreamStartToken(line, column)

    for next in buffer:
        if tokenizer is not None:
            result = tokenizer(line, column, pos, prev, current, next)
            if result is not None:
                for token in result:
                    yield token
                tokenizer = None

        elif simple_key is None:
            if current in TOKENIZERS:
                tokenizer = get_tokenizer(settings, line, column, pos, prev, current, next)

            elif current == "-" and next in " \n":
                yield BlockEntryToken(line, column)

            else:
                simple_key = ScalarToken(line, column, pos)

        elif current == "#":
            if prev in " \n":
                yield massaged_key(settings, simple_key, pos)
                simple_key = None
                tokenizer = CommentTokenizer(settings, line, column, pos, current)

        elif current == ":":
            if next in " \n":
                yield massaged_key(settings, simple_key, pos, is_key=True)
                simple_key = None

        if current == "\n":
            if simple_key is not None:
                yield massaged_key(settings, simple_key, pos)
                simple_key = None
            line += 1
            column = 1

        else:
            column += 1

        pos += 1
        prev = current
        current = next

    if tokenizer is not None:
        result = tokenizer(line, column, pos, prev, current, None)
        if result is not None:
            for token in result:
                yield token

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
    return RootNode().deserialized(scan_tokens(contents))


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
