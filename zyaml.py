import codecs
import collections
import re


NULL = ("null", "~")
FALSE = "false"
TRUE = "true"
RE_TYPED = re.compile(r"^(false|true|null|[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$", re.IGNORECASE)
RE_LINE_SPLIT = re.compile(r"^(\s*([%#]).*|(\s*(-)(\s.*)?)|(---|\.\.\.)(\s.*)?)$")
RE_FLOW_SEP = re.compile(r"""(\s*)(#.*|[!&*][^\s:,\[\]{}]+\s*|[\[\]{}:,]\s*)""")
RE_BLOCK_SEP = re.compile(r"""(\s*)(#.*|[!&*][^\s:,\[\]{}]+\s*|[\[\]{}]\s*|:(\s+|$))""")
RE_DOUBLE_QUOTE_END = re.compile(r'([^\\]")')
RE_SINGLE_QUOTE_END = re.compile(r"([^']'([^']|$))")


def first_line_split_match(match):
    for g in (2, 4, 6):
        s = match.span(g)[0]
        if s >= 0:
            return s, match.group(g)
    return 0, None


def default_marshal(value):
    if value is None:
        return None
    text = value.strip()
    if not text:
        return value
    m = RE_TYPED.match(text)
    if m is None:
        return value
    text = text.lower()
    if text in NULL:
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
            return value


def decode(value):
    """Python 2/3 friendly decoding of output"""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def de_commented(text):
    try:
        i = text.index(" #")
        return text[:i].rstrip()
    except ValueError:
        return text


def get_indent(text):
    count = 0
    for c in text:
        if c != " ":
            return count
        count += 1
    return count


class Token(object):
    """Scanned token, visitor pattern is used for parsing"""

    def __init__(self, line_number, indent, value=None):
        self.line_number = line_number
        self.indent = indent
        self.value = value

    def __repr__(self):
        name = self.__class__.__name__
        if self.indent is not None:
            name = "%s[%s,%s]" % (name, self.line_number, self.indent + 1)
        if self.value is None:
            return name
        return "%s %s" % (name, self.represented_value())

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
        root.pop_doc(closing=True)


class FlowMappingStartToken(Token):
    def consume_token(self, root):
        root.push(MapNode(None))


class FlowSequenceStartToken(Token):
    def consume_token(self, root):
        root.push(ListNode(None))


class FlowEndToken(Token):
    def consume_token(self, root):
        root.pop()


class FlowEntryToken(Token):
    def consume_token(self, root):
        root.wrap_up()


class BlockEntryToken(Token):
    def __init__(self, line_number, indent):
        super(BlockEntryToken, self).__init__(line_number, indent)

    def consume_token(self, root):
        root.wrap_up()
        root.ensure_node(self.indent + 1, ListNode)


class DirectiveToken(Token):
    def __init__(self, line_number, indent, text):
        text = de_commented(text)
        if text.startswith("%YAML"):
            self.name = "%YAML"
            text = text[5:].strip()
        elif text.startswith("%TAG"):
            self.name = "%TAG"
            text = text[4:].strip()
        else:
            self.name, _, text = text.partition(" ")
        super(DirectiveToken, self).__init__(line_number, indent, text.strip())

    def represented_value(self):
        return "%s %s" % (self.name, self.value)


class KeyToken(Token):
    def consume_token(self, root):
        if root.scalar_token is None:
            root.set_scalar_token(ScalarToken(self.line_number, self.indent, ""))
        root.push_key(self)


class TagToken(Token):
    def __init__(self, line_number, indent, text):
        super(TagToken, self).__init__(line_number, indent, text)
        self.marshaller = Marshallers.get_marshaller(text)

    def consume_token(self, root):
        root.decoration.set_tag_token(self)

    def marshalled(self, value):
        if self.marshaller is None:
            return value
        try:
            return self.marshaller(value)
        except ParseError as e:
            e.auto_complete(self)
            raise


class AnchorToken(Token):
    def __init__(self, line_number, indent, text):
        super(AnchorToken, self).__init__(line_number, indent, text[1:])

    def represented_value(self):
        return "&%s" % self.value

    def consume_token(self, root):
        root.decoration.set_anchor_token(self)


class AliasToken(Token):
    def __init__(self, line_number, indent, text):
        super(AliasToken, self).__init__(line_number, indent)
        self.anchor = text[1:]

    def represented_value(self):
        return "*%s" % self.anchor

    def resolved_value(self):
        return self.value

    def consume_token(self, root):
        if self.anchor not in root.anchors:
            raise ParseError("Undefined anchor &%s" % self.anchor)
        self.value = root.anchors.get(self.anchor)
        root.set_scalar_token(self)


class ScalarToken(Token):
    def __init__(self, line_number, indent, text, style=None):
        super(ScalarToken, self).__init__(line_number, indent, text)
        self.style = style
        self.anchor_token = None
        self.tag_token = None

    def represented_value(self):
        if self.style is None:
            return str(self.value)
        if self.style == '"':
            return '"%s"' % decode(codecs.encode(self.value, "unicode_escape"))
        if self.style == "'":
            return "'%s'" % self.value.replace("'", "''")
        return "%s %s" % (self.style, self.value)

    def resolved_value(self):
        if self.tag_token is None:
            return default_marshal(self.value)
        return self.tag_token.marshalled(self.value)

    def set_raw_lines(self, lines):
        self.set_raw_text(" ".join(lines))

    def set_raw_text(self, text):
        if self.style == "'":
            text = text.replace("''", "'")
        elif self.style == '"':
            text = codecs.decode(text, "unicode_escape")
        self.value = text

    def append_newline(self):
        self.value = "%s\n" % (self.value or "")

    def append_text(self, text):
        if not self.value:
            self.value = text
        elif self.value[-1] in " \n":
            self.value = "%s%s" % (self.value, text.lstrip())
        else:
            self.value = "%s %s" % (self.value, text.lstrip())

    def consume_token(self, root):
        root.set_scalar_token(self)


class ParseNode(object):
    def __init__(self, indent):
        self.indent = indent
        self.anchor_token = None
        self.tag_token = None
        self.prev = None
        self.is_temp = False
        self.target = self._new_target()

    def __repr__(self):
        result = self.__class__.__name__[0]
        result += "" if self.indent is None else str(self.indent)
        result += "&" if self.anchor_token else ""
        result += "!" if self.tag_token else ""
        result += "-" if self.is_temp else ""
        return result

    def full_representation(self):
        result = str(self)
        if self.prev is not None:
            result = "%s / %s" % (result, self.prev.full_representation())
        return result

    def _new_target(self):
        """Return specific target instance for this node type"""

    def resolved_value(self):
        if self.tag_token is None:
            return default_marshal(self.target)
        return self.tag_token.marshalled(self.target)

    def push_key(self, value):
        raise ParseError("Key not allowed here")

    def set_value(self, value):
        if self.target is None:
            self.target = value
        elif value is not None:
            self.target = "%s %s" % (self.target, value)

    def wrap_up(self):
        """Nothing to do for lists and scalars"""


class ListNode(ParseNode):
    def _new_target(self):
        return []

    def resolved_value(self):
        if self.tag_token is None:
            return self.target
        return self.tag_token.marshalled(self.target)

    def set_value(self, value):
        self.target.append(value)


class MapNode(ParseNode):
    def __init__(self, indent):
        super(MapNode, self).__init__(indent)
        self.last_key = None

    def _new_target(self):
        return {}

    def resolved_value(self):
        if self.last_key is not None:
            self.target[self.last_key] = None
            self.last_key = None
        if self.tag_token is None:
            return self.target
        return self.tag_token.marshalled(self.target)

    def set_value(self, value):
        self.target[self.last_key] = value
        self.last_key = None

    def push_key(self, value):
        if self.last_key is not None:
            self.target[self.last_key] = None
        self.last_key = value

    def wrap_up(self):
        if self.last_key is not None:
            self.target[self.last_key] = None
            self.last_key = None


class Decoration:
    def __init__(self, root):
        self.root = root
        self.line_number = 0
        self.indent = 0
        self.anchor_token = None
        self.tag_token = None
        self.secondary_anchor_token = None
        self.secondary_tag_token = None

    def __repr__(self):
        result = "[%s,%s] " % (self.line_number, self.indent)
        result += "" if self.anchor_token is None else "&1 "
        result += "" if self.tag_token is None else "!1 "
        result += "" if self.secondary_anchor_token is None else "&2 "
        result += "" if self.secondary_tag_token is None else "!2 "
        return result

    def track(self, token):
        if token.line_number != self.line_number:
            self.root.wrap_up()
            self.line_number = token.line_number
            self.indent = token.indent
            self.slide_anchor_token()
            self.slide_tag_token()

    def slide_anchor_token(self):
        if self.anchor_token is not None:
            if self.secondary_anchor_token is not None:
                raise ParseError("Too many anchor tokens", self.anchor_token)
            self.secondary_anchor_token = self.anchor_token
            self.anchor_token = None

    def slide_tag_token(self):
        if self.tag_token is not None:
            if self.secondary_tag_token is not None:
                raise ParseError("Too many tag tokens", self.tag_token)
            self.secondary_tag_token = self.tag_token
            self.tag_token = None

    def set_anchor_token(self, token):
        self.track(token)
        if self.anchor_token is not None:
            self.slide_anchor_token()
        self.anchor_token = token

    def set_tag_token(self, token):
        self.track(token)
        if self.tag_token is not None:
            self.slide_tag_token()
        self.tag_token = token

    def decorate_token(self, token):
        self.track(token)
        anchor_token, tag_token = self.pop_tokens(allow_secondary=False)
        self.decorate(token, anchor_token, tag_token)

    def decorate_node(self, node):
        anchor_token, tag_token = self.pop_tokens(allow_secondary=True)
        self.decorate(node, anchor_token, tag_token)

    def pop_tokens(self, allow_secondary=False):
        anchor_token = tag_token = None
        if self.anchor_token is not None:
            anchor_token = self.anchor_token
            self.anchor_token = None
        elif allow_secondary:
            anchor_token = self.secondary_anchor_token
            self.secondary_anchor_token = None
        if self.tag_token is not None:
            tag_token = self.tag_token
            self.tag_token = None
        elif allow_secondary:
            tag_token = self.secondary_tag_token
            self.secondary_tag_token = None
        return anchor_token, tag_token

    @staticmethod
    def decorate(target, anchor_token, tag_token):
        if anchor_token is not None:
            if not hasattr(target, "anchor_token"):
                raise ParseError("Anchors not allowed on %s" % target.__class__.__name__)
            target.anchor_token = anchor_token
        if tag_token is not None:
            if not hasattr(target, "tag_token"):
                raise ParseError("Tags not allowed on %s" % type(target))
            target.tag_token = tag_token

    @staticmethod
    def resolved_value(root, target):
        if target is None:
            return None
        value = target.resolved_value()
        anchor = getattr(target, "anchor_token", None)
        if anchor is not None:
            root.anchors[anchor.value] = value
        return value


class RootNode(object):
    def __init__(self):
        self.docs = []
        self.head = None  # type: ParseNode | None
        self.decoration = Decoration(self)
        self.scalar_token = None
        self.anchors = {}

    def __repr__(self):
        result = str(self.decoration)
        result += "*" if isinstance(self.scalar_token, AliasToken) else ""
        result += "$" if self.scalar_token else ""
        result = "[%s]" % result
        if self.head is None:
            return "%s /" % result
        return "%s %s" % (result, self.head.full_representation())

    def set_scalar_token(self, token):
        self.decoration.decorate_token(token)
        if self.scalar_token is not None:
            raise ParseError("2 consecutive scalars given")
        self.scalar_token = token

    def wrap_up(self):
        if self.scalar_token is not None:
            value = self.decoration.resolved_value(self, self.scalar_token)
            self.scalar_token = None
            if self.head is None:
                self.push(ParseNode(self.decoration.indent))
            self.head.set_value(value)
            if self.head.is_temp:
                self.pop()

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
                if indent < self.head.indent:
                    raise ParseError("Line should be indented at least %s chars" % self.head.indent)
            self.push(node_type(indent))

    def push_key(self, key_token):
        self.decoration.track(key_token)
        key = self.decoration.resolved_value(self, self.scalar_token)
        self.scalar_token = None
        self.ensure_node(self.decoration.indent, MapNode)
        self.head.push_key(key)

    def push(self, node):
        self.decoration.decorate_node(node)
        if self.head is not None:
            if self.head.indent is None:
                node.is_temp = node.indent is not None
            elif node.indent is not None:
                while node.indent < self.head.indent:
                    self.pop()
        node.prev = self.head
        self.head = node

    def pop(self):
        self.wrap_up()
        popped = self.head
        if popped is not None:
            self.head = popped.prev
            value = self.decoration.resolved_value(self, popped)
            if self.head is None:
                self.docs.append(value)
            else:
                self.head.set_value(value)

    def pop_doc(self, closing=False):
        if self.head is None:
            self.wrap_up()
        if closing and self.head is None:
            self.docs.append("")
        while self.head is not None:
            self.pop()
        self.anchors = {}

    def deserialized(self, tokens):
        token = None
        try:
            for token in tokens:
                token.consume_token(self)
            return simplified(self.docs)
        except ParseError as error:
            error.auto_complete(token)
            raise


class ParseError(Exception):
    def __init__(self, message, *context):
        self.message = message
        self.line_number = None
        self.indent = None
        self.auto_complete(*context)

    def __str__(self):
        if self.indent is None:
            return self.message
        return "%s, line %s column %s" % (self.message, self.line_number, self.indent + 1)

    def complete_coordinates(self, line_number, indent):
        if self.line_number is None:
            self.line_number = line_number
        if self.indent is None:
            self.indent = indent

    def auto_complete(self, *context):
        if context:
            if isinstance(context[0], Token):
                self.complete_coordinates(context[0].line_number, context[0].indent)
            elif len(context) == 2:
                self.complete_coordinates(*context)


def _checked_scalar(value):
    if isinstance(value, list):
        raise ParseError("scalar needed, got list instead")
    if isinstance(value, dict):
        raise ParseError("scalar needed, got map instead")
    return value


class DefaultMarshaller:
    @staticmethod
    def get_marshaller(name):
        return getattr(DefaultMarshaller, name, None)

    @staticmethod
    def map(value):
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            if all(isinstance(x, dict) for x in value):
                result = {}
                for x in value:
                    result.update(x)
                return result
        raise ParseError("not a map")

    @staticmethod
    def seq(value):
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            result = []
            for k, v in value.items():
                result.append(k)
                result.append(v)
            return result
        raise ParseError("not a list or map")

    @staticmethod
    def set(value):
        if isinstance(value, dict):
            return set(value.keys())
        raise ParseError("not a map, !!set applies to maps")

    @staticmethod
    def str(value):
        return str(_checked_scalar(value))

    @staticmethod
    def int(value):
        return int(_checked_scalar(value))

    @staticmethod
    def null(value):
        _checked_scalar(value)
        return None

    @staticmethod
    def bool(value):
        text = str(_checked_scalar(value)).lower()
        if text in (FALSE, "n", "no", "off"):
            return False
        if text in (TRUE, "y", "yes", "on"):
            return True
        raise ParseError("'%s' is not a boolean" % value)


class Marshallers(object):
    providers = {"": DefaultMarshaller}

    @classmethod
    def get_marshaller(cls, text):
        if text.startswith("!"):
            text = text[1:]
        prefix, _, name = text.partition("!")
        provider = cls.providers.get(prefix)
        if provider:
            return provider.get_marshaller(name)


class Scanner(object):
    def __init__(self, buffer):
        if hasattr(buffer, "read"):
            buffer = buffer.read()
        self.generator = enumerate(buffer.splitlines(), start=1)
        self.line_regex = RE_BLOCK_SEP
        self.flow_ender = None
        self.leaders = {
            "%": self.consume_directive,
            "-": self.consume_block_entry,
            "---": self.consume_doc_start,
            "...": self.consume_doc_end,
        }
        self.tokenizer_map = {
            "!": TagToken,
            "&": AnchorToken,
            "*": AliasToken,
            "{": self.consume_flow_map_start,
            "}": self.consume_flow_map_end,
            "[": self.consume_flow_list_start,
            "]": self.consume_flow_list_end,
            ",": self.consume_comma,
        }

    def __repr__(self):
        return "block mode" if self.flow_ender is None else "flow mode"

    @staticmethod
    def consume_directive(line_number, start, text):
        if start != 0:
            raise ParseError("Directive must not be indented")
        return len(text), DirectiveToken(line_number, 0, text)

    @staticmethod
    def consume_block_entry(line_number, start, _):
        return start + 2, BlockEntryToken(line_number, start)

    @staticmethod
    def consume_doc_start(line_number, start, _):
        return 4, DocumentStartToken(line_number, start)

    @staticmethod
    def consume_doc_end(line_number, start, _):
        return 4, DocumentEndToken(line_number, start)

    def next_actionable_line(self, line_number, line_text):
        comments = 0
        while True:
            m = RE_LINE_SPLIT.match(line_text)
            if m is None:
                return line_number, get_indent(line_text), len(line_text), line_text, comments, None
            end = m.span(0)[1]
            start, leader = first_line_split_match(m)
            if leader is None:
                return line_number, start, end, line_text, comments, None
            if leader != "#":
                start, token = self.leaders.get(leader)(line_number, start, line_text)
                return line_number, start, end, line_text, comments, token
            comments += 1
            line_number, line_text = next(self.generator)

    def push_flow_ender(self, ender):
        if self.flow_ender is None:
            self.flow_ender = collections.deque()
            self.line_regex = RE_FLOW_SEP
        self.flow_ender.append(ender)

    def pop_flow_ender(self, expected):
        if self.flow_ender is None:
            raise ParseError("'%s' without corresponding opener" % expected)
        popped = self.flow_ender.pop()
        if not self.flow_ender:
            self.flow_ender = None
            self.line_regex = RE_BLOCK_SEP
        if popped != expected:
            raise ParseError("Expecting '%s', but found '%s'" % (expected, popped))

    def consume_flow_map_start(self, line_number, start, _):
        self.push_flow_ender("}")
        return FlowMappingStartToken(line_number, start)

    def consume_flow_map_end(self, line_number, start, _):
        self.pop_flow_ender("}")
        return FlowEndToken(line_number, start)

    def consume_flow_list_start(self, line_number, start, _):
        self.push_flow_ender("]")
        return FlowSequenceStartToken(line_number, start)

    def consume_flow_list_end(self, line_number, start, _):
        self.pop_flow_ender("]")
        return FlowEndToken(line_number, start)

    @staticmethod
    def consume_comma(line_number, start, _):
        return FlowEntryToken(line_number, start)

    def _multiline(self, line_number, start, line_text, style):
        regex = RE_DOUBLE_QUOTE_END if style == '"' else RE_SINGLE_QUOTE_END
        token = ScalarToken(line_number, start, None, style=style)
        try:
            start = start + 1
            lines = None
            m = None
            while m is None:
                m = regex.search(line_text, start)
                if m is not None:
                    end = m.span(1)[1]
                    text = line_text[start:end]
                    text = text[:-1] if text.endswith(style) else text[:-2]
                    text = text.strip()
                    line_size = len(line_text)
                    if lines is None:
                        token.set_raw_text(text)
                    else:
                        lines.append(text)
                        token.set_raw_lines(lines)
                    if end >= line_size:
                        line_text = None
                    return line_number, end, line_size, line_text, token
                if lines is None:
                    lines = [line_text[start:]]
                    start = 0
                else:
                    lines.append(line_text.strip())
                line_number, line_text = next(self.generator)
        except StopIteration:
            raise ParseError("Unexpected end, runaway string at line %s?" % token.line_number)

    @staticmethod
    def _get_literal_styled_token(line_number, start, style):
        original = style
        if len(style) > 3:
            raise ParseError("Invalid literal style '%s', should be less than 3 chars" % style, line_number, start)
        keep = None
        if "-" in style:
            style = style.replace("-", "", 1)
            keep = False
        if "+" in style:
            if keep is not None:
                raise ParseError("Ambiguous literal style '%s'" % original, line_number, start)
            keep = True
            style = style.replace("+", "", 1)
        indent = None
        if len(style) == 2:
            indent = style[1]
            style = style[0]
            if not indent.isdigit():
                raise ParseError("Invalid literal style '%s'" % original, line_number, start)
            indent = int(indent)
            if indent < 1:
                raise ParseError("Indent must be between 1 and 9", line_number, start)
        if style == ">":
            folded = True
        elif style == "|":
            folded = False
        else:
            raise ParseError("Internal error, invalid style '%s'" % original, line_number, start)
        return folded, keep, indent, ScalarToken(line_number, indent, None, style=original)

    def _consume_literal(self, line_number, start, line_text):
        folded, keep, indent, token = self._get_literal_styled_token(line_number, start, de_commented(line_text[start:]))
        lines = []
        while True:
            try:
                line_number, line_text = next(self.generator)
                line_size = len(line_text)
                if line_size == 0:
                    lines.append(line_text)
                    continue
            except StopIteration:
                line_number += 1
                line_text = ""
                line_size = 0
            i = get_indent(line_text)
            if indent is None:
                indent = i if i != 0 else 1
            if i < indent:
                text = "\n".join(lines)
                if keep is None:
                    token.value = "%s\n" % text.rstrip()
                elif keep is False:
                    token.value = text.rstrip()
                else:
                    token.value = "%s\n" % text
                if i >= line_size:
                    line_text = None
                return line_number, i, line_size, line_text, token
            value = line_text[indent:]
            if folded and lines and not value.startswith(" ") and not lines[-1].startswith(" "):
                if lines[-1]:
                    lines[-1] = "%s %s" % (lines[-1], value)
                else:
                    lines[-1] = value
            else:
                lines.append(value)

    def next_match(self, start, line_size, line_text):
        while start < line_size:
            m = self.line_regex.search(line_text, start)
            if m is None:
                yield start, line_text[start:]
                return
            prev_start = start if start < m.span(1)[0] else None  # span1: spaces, span2: match, span3: spaces following ':'
            start, end = m.span(2)
            matched = line_text[start]
            if prev_start is not None:
                if matched in "!&*{[":
                    yield prev_start, de_commented(line_text[prev_start:])
                    return
                yield prev_start, line_text[prev_start:start]
            if matched == "#":
                return
            if matched == ":":
                yield start, matched
            else:
                yield start, line_text[start:end].strip()
            start = end

    def __iter__(self):
        start = line_number = line_size = comments = 0
        pending = simple_key = upcoming = token = None
        try:
            yield StreamStartToken(1, 0)
            while True:
                if token is not None:
                    if pending is not None:
                        yield pending
                        pending = None
                    yield token
                    token = None
                if upcoming is None:
                    line_number, upcoming = next(self.generator)
                    start = comments = 0
                if start == 0:
                    line_number, start, line_size, upcoming, comments, token = self.next_actionable_line(line_number, upcoming)
                if simple_key is not None:
                    if pending is None:
                        pending = simple_key
                    else:
                        pending.append_text(simple_key.value)
                    simple_key = None
                if token is not None:
                    if pending is not None:
                        yield pending
                        pending = None
                    yield token
                    token = None
                if pending is not None and comments:
                    yield pending
                    pending = None
                if start == line_size:
                    if pending is not None:
                        pending.append_newline()
                    upcoming = None
                    continue
                current_line = upcoming
                upcoming = None
                for start, text in self.next_match(start, line_size, current_line):
                    if simple_key is None:
                        if text == ":":
                            if pending is not None:
                                yield pending
                                pending = None
                            yield KeyToken(line_number, start)
                            continue
                        if pending is None:
                            if text[0] in "\"'":
                                line_number, start, line_size, upcoming, token = self._multiline(line_number, start, current_line, text[0])
                                break
                            if text[0] in '|>':
                                line_number, start, line_size, upcoming, token = self._consume_literal(line_number, start, current_line)
                                break
                        tokenizer = self.tokenizer_map.get(text[0])
                        if tokenizer is None:
                            simple_key = ScalarToken(line_number, start, text.strip())
                        else:
                            if pending is not None:
                                yield pending
                                pending = None
                            yield tokenizer(line_number, start, text)
                    elif text == ":":
                        if pending is not None:
                            yield pending
                            pending = None
                        yield simple_key
                        simple_key = None
                        yield KeyToken(line_number, start)
                    else:
                        tokenizer = self.tokenizer_map.get(text[0])
                        if tokenizer is None:
                            simple_key.append_text(text)
                        else:
                            if pending is None:
                                yield simple_key
                            else:
                                pending.append_text(simple_key.value)
                                yield pending
                                pending = None
                            simple_key = None
                            yield tokenizer(line_number, start, text)
        except StopIteration:
            if pending is not None:
                if simple_key is not None:
                    pending.append_text(simple_key.value)
                    simple_key = None
                yield pending
            if simple_key is not None:
                yield simple_key
            yield StreamEndToken(line_number, 0)
        except ParseError as error:
            error.auto_complete(line_number, start)
            raise


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
    scanner = Scanner(contents)
    return RootNode().deserialized(scanner)


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
