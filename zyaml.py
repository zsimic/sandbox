import codecs
import re


NULL = "null"
FALSE = "false"
TRUE = "true"
RE_TYPED = re.compile(r"^(false|true|null|[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$", re.IGNORECASE)
LEADING_SPACES = re.compile(r"\n\s*", re.MULTILINE)


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


def first_non_blank(text):
    for c in text:
        if c != " ":
            return c


class Token(object):
    """Scanned token, visitor pattern is used for parsing"""

    def __init__(self, line, column, value=None):
        self.line = line
        self.column = column
        self.value = value

    def __repr__(self):
        if self.value is None:
            if self.line:
                return "%s[%s,%s]" % (self.token_name(), self.line, self.column)
            return self.token_name()
        return "%s[%s,%s] %s" % (self.token_name(), self.line, self.column, self.represented_value())

    def token_name(self):
        return self.__class__.__name__

    def represented_value(self):
        return str(self.value)

    def consume_token(self, root):
        """
        :param RootNode root: Process this token on given 'root' node
        """


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    def consume_token(self, root):
        root.pop_doc()


class DocumentStartToken(Token):
    def consume_token(self, root):
        root.pop_doc()


class DocumentEndToken(Token):
    def consume_token(self, root):
        root.pop_doc(explicit=True)


class FlowMappingStartToken(Token):
    def consume_token(self, root):
        root.push(MapNode(root, None))


class FlowSequenceStartToken(Token):
    def consume_token(self, root):
        root.push(ListNode(root, None))


class FlowEndToken(Token):
    def consume_token(self, root):
        root.pop()


class FlowEntryToken(Token):
    def consume_token(self, root):
        root.auto_apply()


class BlockEntryToken(Token):
    def consume_token(self, root):
        root.ensure_node(self.column + 1, ListNode)


class CommentToken(Token):
    pass


class DirectiveToken(Token):
    def __init__(self, line, column, text):
        if text.startswith("%YAML"):
            self.name = "%YAML"
            text = text[5:].strip()
        elif text.startswith("%TAG"):
            self.name = "%TAG"
            text = text[4:].strip()
        else:
            self.name, _, text = text.partition(" ")
        super(DirectiveToken, self).__init__(line, column, text.strip())

    def represented_value(self):
        return "%s %s" % (self.name, self.value)


class AnchorToken(Token):
    def consume_token(self, root):
        root.set_anchor(self)


class AliasToken(Token):
    def consume_token(self, root):
        value = root.anchors.get(self.value)
        root.push_value(self.column, value)


class TagToken(Token):
    def consume_token(self, root):
        assert not root.tag_token
        root.tag_token = self

    def transformed(self, value):
        if self.value is not None:
            return self.value.transformed(value)
        return value


class ScalarToken(Token):

    def __init__(self, line, column, text=None, style=None):
        super(ScalarToken, self).__init__(line, column, text)
        self.style = style
        self.is_key = False

    def token_name(self):
        return "KeyToken" if self.is_key else self.__class__.__name__

    def represented_value(self):
        if self.style is None:
            return str(self.value)
        if self.style == '"':
            return '"%s"' % self.value
        if self.style == "'":
            return "'%s'" % self.value
        return "%s %s" % (self.style, self.value)

    def consume_token(self, root):
        if self.is_key:
            root.push_key(self.column, self.value)
        else:
            root.push_value(self.column, self.value)


class ParseNode(object):
    def __init__(self, root, indent):
        self.root = root  # type: RootNode
        if root is not None and root.tag_token:
            self.indent = root.tag_token.column
        else:
            self.indent = indent
        self.prev = None
        self.is_temp = False
        self.needs_apply = False
        self.last_value = None
        self.target = None
        self.anchor_token = None

    def __repr__(self):
        result = "%s%s%s" % (self.__class__.__name__[0], "" if self.indent is None else self.indent, "*" if self.is_temp else "")
        if self.prev:
            result = "%s / %s" % (result, self.prev)
        return result

    def set_key(self, key):
        raise ParseError("Key not allowed here")

    def set_value(self, value):
        self.needs_apply = True
        value = self.root.transformed(value)
        if self.last_value is None:
            self.last_value = value
        elif value is not None:
            self.last_value = "%s %s" % (self.last_value, value)

    def auto_apply(self):
        if self.anchor_token:
            self.root.anchors[self.anchor_token.value] = self.last_value
            self.anchor_token = None
        if self.needs_apply:
            self.apply()

    def apply(self):
        """Apply 'self.last_value' to 'self.target'"""
        self.needs_apply = False


class ListNode(ParseNode):
    def apply(self):
        if self.target is None:
            self.target = []
        self.target.append(self.last_value)
        self.last_value = None
        self.needs_apply = False


class MapNode(ParseNode):
    def __init__(self, root, indent):
        super(MapNode, self).__init__(root, indent)
        self.last_key = None

    def set_key(self, key):
        if self.last_key is not None:
            raise ParseError("Unexpected key")
        self.last_key = self.root.transformed(key)
        self.needs_apply = True

    def apply(self):
        if self.target is None:
            self.target = {}
        self.target[self.last_key] = self.last_value
        self.last_key = None
        self.last_value = None
        self.needs_apply = False


class ScalarNode(ParseNode):
    def apply(self):
        self.target = self.last_value
        self.last_value = None
        self.needs_apply = False


class RootNode(object):
    def __init__(self):
        self.docs = []
        self.head = None  # type: ParseNode | None
        self.tag_token = None
        self.anchors = {}

    def __repr__(self):
        return str(self.head or "/")

    def transformed(self, value):
        if self.tag_token is not None:
            value = self.tag_token.transformed(value)
            self.tag_token = None
        return value

    def set_anchor(self, token):
        self.head.anchor_token = token

    def auto_apply(self):
        if self.head:
            self.head.auto_apply()

    def needs_new_node(self, indent, node_type):
        if self.head is None or self.head.__class__ is not node_type:
            return True
        if indent is None:
            return self.head.indent is not None
        if self.head.indent is None:
            return False
        return indent > self.head.indent

    def needs_pop(self, indent):
        if indent is None or self.head is None or self.head.indent is None:
            return False
        return self.head.indent > indent

    def ensure_node(self, indent, node_type):
        while self.needs_pop(indent):
            self.pop()
        if self.needs_new_node(indent, node_type):
            if node_type is ListNode and self.head is not None and self.head.indent is not None and indent is not None:
                if indent <= self.head.indent:
                    raise ParseError("Line should be indented at least %s chars" % (self.head.indent - 1))
            self.push(node_type(self, indent))
        self.auto_apply()

    def push_key(self, indent, key):
        self.ensure_node(indent, MapNode)
        self.head.set_key(key)

    def push_value(self, indent, value):
        if self.head is None:
            self.push(ScalarNode(self, indent))
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
        if popped:
            popped.auto_apply()
            if self.head:
                self.head.set_value(popped.target)
                self.head.auto_apply()

    def pop_doc(self, explicit=False):
        prev = None
        while self.head:
            prev = self.head
            self.pop()
        if prev:
            self.docs.append(prev.target)
        elif explicit:
            self.docs.append(None)

    def deserialized(self, tokens):
        token = None
        try:
            for token in tokens:
                token.consume_token(self)
            return simplified(self.docs)

        except ParseError as error:
            if token and error.line is None:
                error.line = token.line
                error.column = token.column
            raise


class Tokenizer(object):
    def __init__(self, settings, line, column, pos, current, upcoming):
        self.settings = settings  # type: ScanSettings
        self.line = line  # type: int
        self.column = column  # type: int
        self.pos = pos  # type: int
        self.current = current  # type: str
        self.upcoming = upcoming  # type: str

    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, upcoming):
        return True

    def contents(self, start, end):
        return self.settings.contents(start, end)

    def __call__(self, line, column, pos, prev, current, upcoming):
        """Implemented by descendants, consuming one char at a time"""


class CommentTokenizer(Tokenizer):

    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, upcoming):
        return current == "#" and (prev == " " or prev == "\n")

    def __call__(self, line, column, pos, prev, current, upcoming):
        if current == "\n":
            if not self.settings.yield_comments:
                return []
            return [CommentToken(self.line, self.column, self.contents(self.pos, pos).strip())]


class FlowTokenizer(Tokenizer):
    def __init__(self, settings, line, column, pos, current, upcoming):
        super(FlowTokenizer, self).__init__(settings, line, column, pos, current, upcoming)
        if current == "{":
            self.end_char = "}"
            self.tokens = [FlowMappingStartToken(line, column)]  # type: list[Token]
        else:
            self.end_char = "]"
            self.tokens = [FlowSequenceStartToken(line, column)]  # type: list[Token]
        self.sub_tokenizer = None
        self.simple_key = None

    def consume_simple_key(self, pos, is_key=False):
        if self.simple_key is not None:
            self.tokens.append(massaged_key(self.settings, self.simple_key, pos, is_key=is_key))
            self.simple_key = None

    def __call__(self, line, column, pos, prev, current, upcoming):
        if self.sub_tokenizer is not None:
            result = self.sub_tokenizer(line, column, pos, prev, current, upcoming)
            if result is not None:
                self.tokens.extend(result)
                self.sub_tokenizer = None

        elif current == self.end_char:
            self.consume_simple_key(pos)
            self.tokens.append(FlowEndToken(line, column))
            return self.tokens

        elif self.simple_key is None:
            if current != " " and current != "\n":
                self.sub_tokenizer = get_tokenizer(self.settings, line, column, pos, prev, current, upcoming)
                if self.sub_tokenizer is None:
                    if current == ",":
                        self.tokens.append(FlowEntryToken(line, column))

                    elif current != ":" or upcoming not in " \n":
                        self.simple_key = ScalarToken(line, column, pos)

        elif current == ":":
            if upcoming in " \n":
                self.consume_simple_key(pos, is_key=True)

        elif current == ",":
            self.consume_simple_key(pos)
            self.tokens.append(FlowEntryToken(line, column))

        elif current == "\n":
            self.consume_simple_key(pos)


class DoubleQuoteTokenizer(Tokenizer):
    def __call__(self, line, column, pos, prev, current, upcoming):
        if current == '"' and prev != "\\":
            text = self.contents(self.pos + 1, pos)
            text = LEADING_SPACES.sub(" ", codecs.decode(text, "unicode_escape"))
            return [ScalarToken(line, column, text, style='"')]


class SingleQuoteTokenizer(Tokenizer):
    def __call__(self, line, column, pos, prev, current, upcoming):
        if current == "'" and prev != "'" and upcoming != "'":
            text = self.contents(self.pos + 1, pos).replace("''", "'")
            text = LEADING_SPACES.sub(" ", text)
            return [ScalarToken(line, column, text, style="'")]


class TagHandler(object):
    def __init__(self, prefix, name, transformer):
        self.prefix = prefix
        self.name = name
        self.transformer = transformer

    def __repr__(self):
        return "!%s!%s" % (self.prefix, self.name)

    def transformed(self, value):
        if self.transformer is not None:
            return self.transformer(value)
        return value


class TagTokenizer(Tokenizer):
    def __call__(self, line, column, pos, prev, current, upcoming):
        if current == " " or current == "\n":
            text = self.settings.contents(self.pos, pos)
            if text.startswith("!"):
                handler = self.settings.get_tag_handler(text[1:])
                return [TagToken(self.line, self.column, handler)]
            if text.startswith("&"):
                return [AnchorToken(self.line, self.column, text[1:])]
            if text.startswith("*"):
                return [AliasToken(self.line, self.column, text[1:])]
            raise ParseError("Internal error, unknown tag: %s" % text)


class DirectiveTokenizer(Tokenizer):
    @classmethod
    def is_applicable(cls, line, column, pos, prev, current, upcoming):
        return column == 1

    def __call__(self, line, column, pos, prev, current, upcoming):
        if current == "\n":
            text = self.settings.contents(self.pos, pos)
            return [DirectiveToken(self.line, self.column, text)]


class LiteralTokenizer(Tokenizer):
    def __init__(self, settings, line, column, pos, current, upcoming):
        super(LiteralTokenizer, self).__init__(settings, line, column, pos, current, upcoming)
        self.min_indent = settings.last_key.column if settings.last_key else 1
        self.indent = None
        self.in_comment = False
        if upcoming == "\n" or upcoming == " ":
            self.style = current
        elif current == "|" and upcoming in "-+":
            self.style = "%s%s" % (current, upcoming)
        elif upcoming.isdigit():
            self.min_indent = int(upcoming)
            self.indent = int(upcoming)
            self.style = "%s%s" % (current, upcoming)
        else:
            raise ParseError("Invalid style", line, column)

    def __call__(self, line, column, pos, prev, current, upcoming):
        if line == self.line:  # Allow only blanks and comments on first line
            if current == "\n":  # We're done with the first line
                self.pos = pos + 1
                self.in_comment = False
            elif not self.in_comment:
                if current == "#":
                    self.in_comment = True
                elif current != " ":
                    if pos != self.pos + 1:
                        raise ParseError("Invalid char in literal", line, column)

        elif current == "\n" or upcoming is None:
            self.in_comment = False
            if upcoming is None or upcoming not in "# \n":
                return self.extracted_tokens(line, column, pos)

        elif not self.in_comment:
            if self.indent is None:
                if current != " ":
                    if column < self.min_indent:
                        raise ParseError("Literal value should be indented", line, column)
                    self.indent = column - 1

            elif current == "#" and prev in " \n":
                self.in_comment = True

            elif upcoming != " " and column <= self.min_indent:
                return self.extracted_tokens(line, column, pos)

    def extracted_tokens(self, line, column, pos):
        if self.indent is None:
            raise ParseError("No indent in literal", line, column)
        text = self.contents(self.pos, pos + 1)
        result = []
        indent = self.indent
        for line in text.split("\n"):
            if not result or self.style == ">" or first_non_blank(line) != "#":
                result.append(line[indent:])
        text = "\n".join(result)
        if text and self.upcoming != "+" and self.style[0] != ">" and not self.style[-1].isdigit():
            if self.upcoming == "-":
                text = text.strip()
            elif text[-1] == "\n":
                text = "%s\n" % text.strip()
        return [ScalarToken(line, column, text, style=self.style)]


class ParseError(Exception):
    def __init__(self, message, line=None, column=None):
        self.message = message
        self.line = line
        self.column = column

    def __str__(self):
        if self.line is None:
            return self.message
        return "%s, line %s column %s" % (self.message, self.line, self.column)


TOKENIZER_MAP = {
    "%": DirectiveTokenizer,
    "!": TagTokenizer,
    "&": TagTokenizer,
    "*": TagTokenizer,
    ">": LiteralTokenizer,
    "|": LiteralTokenizer,
    "#": CommentTokenizer,
    "{": FlowTokenizer,
    "[": FlowTokenizer,
    '"': DoubleQuoteTokenizer,
    "'": SingleQuoteTokenizer,
}


def get_tokenizer(settings, line, column, pos, prev, current, upcoming):
    """:rtype: Tokenizer"""
    tokenizer = TOKENIZER_MAP.get(current)  # type: Tokenizer
    if tokenizer is not None and tokenizer.is_applicable(line, column, pos, prev, current, upcoming):
        return tokenizer(settings, line, column, pos, current, upcoming)


def massaged_key(settings, key, pos, is_key=False):
    key.value = settings.contents(key.value, pos).strip()
    settings.last_key = key
    if key.column == 1:
        if key.value == "---":
            return DocumentStartToken(key.line, key.column)
        if key.value == "...":
            return DocumentEndToken(key.line, key.column)
    key.is_key = is_key
    if not is_key and key.style is None:
        key.value = settings.scalar_marshaller(key.value)
    return key


def to_map(value):
    if isinstance(value, list):
        if len(value) % 2 == 0:
            return dict(value)
    return value


def to_list(value):
    if isinstance(value, dict):
        result = []
        for k, v in value:
            result.append(k)
            result.append(v)
        return result
    return value


def to_str(value):
    return str(value)


def to_null(_):
    return None


def to_bool(value):
    text = str(value).lower()
    if text in (FALSE, "n", "no", "off"):
        return False
    if text in (TRUE, "y", "yes", "on"):
        return True
    raise ParseError("%s is not a boolean" % value)


def to_int(value):
    return int(value)


class ScanSettings(object):
    def __init__(self, yield_comments=False, scalar_marshaller=parsed_value):
        self.yield_comments = yield_comments
        self.buffer = None
        self.last_key = None
        self.scalar_marshaller = scalar_marshaller
        self.taggers = {"": {
            "bool": to_bool,
            "int": to_int,
            "map": to_map,
            "null": to_null,
            "omap": to_map,
            "seq": to_list,
            "set": to_list,
            "str": to_str,
        }}

    def contents(self, start, end):
        return self.buffer[start:end]

    def get_tag_handler(self, text):
        prefix, _, name = text.partition("!")
        transformer = None
        tagger = self.taggers.get(prefix)
        if tagger:
            transformer = tagger.get(name)
        return TagHandler(prefix, name, transformer)


def scan_tokens(buffer, settings=None):
    yield StreamStartToken(1, 1)
    if not buffer:
        yield StreamEndToken(1, 1)
        return

    if settings is None:
        settings = ScanSettings()
    settings.buffer = buffer

    if len(buffer) <= 2:
        yield massaged_key(settings, ScalarToken(1, 1, 0), len(buffer))
        yield StreamEndToken(1, len(buffer))
        return

    line = 1
    column = 1
    pos = 0
    prev = " "
    upcoming = tokenizer = simple_key = None
    current = None

    for upcoming in buffer:
        if current is None:
            current = upcoming
            continue

        if tokenizer is not None:
            result = tokenizer(line, column, pos, prev, current, upcoming)
            if result is not None:
                for token in result:
                    yield token
                tokenizer = None

        elif current == " " or current == "\n":
            if simple_key is not None and column == 4 and line == simple_key.line and (prev == "-" or prev == "."):
                text = settings.contents(pos - 3, pos)
                if text == "---":
                    yield DocumentStartToken(line, column)
                    simple_key = None
                elif text == "...":
                    yield DocumentEndToken(line, column)
                    simple_key = None

        elif simple_key is None:
            tokenizer = get_tokenizer(settings, line, column, pos, prev, current, upcoming)
            if tokenizer is None:
                if current == "-" and upcoming in " \n":
                    yield BlockEntryToken(line, column)

                else:
                    simple_key = ScalarToken(line, column, pos)

        elif current == "#":
            if prev in " \n":
                yield massaged_key(settings, simple_key, pos)
                simple_key = None
                tokenizer = CommentTokenizer(settings, line, column, pos, current, upcoming)

        elif current == ":":
            if upcoming in " \n":
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
        current = upcoming

    if upcoming is not None:
        pos += 1
        prev = current
        current = upcoming

        if tokenizer is not None:
            result = tokenizer(line, column, pos, prev, current, None)
            if result is not None:
                for token in result:
                    yield token

        if simple_key is not None:
            yield massaged_key(settings, simple_key, pos)

        yield StreamEndToken(line, column)


def load(stream):
    """
    :param str|file stream: Stream or contents to load
    """
    if hasattr(stream, "read"):
        stream = stream.read()
    return load_string(stream)


def load_string(contents):
    """
    :param str contents: Yaml to deserialize
    """
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
