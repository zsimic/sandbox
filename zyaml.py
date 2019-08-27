import codecs
import collections
import datetime
import dateutil
import re
import sys


PY2 = sys.version_info < (3, 0)
RESERVED = "@`"
RE_LINE_SPLIT = re.compile(r"^(\s*([%#]).*|(\s*(-)(\s.*)?)|(---|\.\.\.)(\s.*)?)$")
RE_FLOW_SEP = re.compile(r"""(\s*)(#.*|![^\s\[\]{}]*\s*|[&*][^\s:,\[\]{}]+\s*|[\[\]{}:,]\s*)""")
RE_BLOCK_SEP = re.compile(r"""(\s*)(#.*|![^\s\[\]{}]*\s*|[&*][^\s:,\[\]{}]+\s*|[\[\]{}]\s*|:(\s+|$))""")
RE_DOUBLE_QUOTE_END = re.compile(r'([^\\]")')
RE_SINGLE_QUOTE_END = re.compile(r"([^']'([^']|$))")

RE_SIMPLE_SCALAR = re.compile(
    r"^("
    r"(false|true|null|~)|"
    r"([-+]?([0-9_]*\.?[0-9_]*([eE][-+]?[0-9_]+)?|\.?inf|\.?nan|0o[0-7]+|0x[0-9a-f]+))|"
    r"(([0-9]{4})-([0-9][0-9]?)-([0-9][0-9]?)" 
    r"([Tt \t]([0-9][0-9]?):([0-9][0-9]?):([0-9][0-9]?)(\.[0-9]*)?"
    r"([ \t]*(Z|[+-][0-9][0-9]?(:([0-9][0-9]?))?))?)?)"
    r")$",
    re.IGNORECASE
)

UTC = dateutil.tz.tzoffset("UTC", 0)
CONSTANTS = {
    "null": None,
    "~": None,
    "false": False,
    "n": False,
    "no": False,
    "off": False,
    "true": True,
    "y": True,
    "yes": True,
    "on": True,
}


if PY2:
    def cleaned_number(text):
        return text.replace("_", "")

    def base64_decode(value):
        return _checked_scalar(value).decode('base64')

else:
    import base64

    def cleaned_number(text):
        return text

    def base64_decode(value):
        return base64.decodebytes(_checked_scalar(value).encode("ascii"))


def to_float(text):
    try:
        return float(text)
    except ValueError:
        if len(text) >= 3:
            if text[0] == "0":
                if text[1] == "o":
                    return int(text, base=8)
                if text[1] == "x":
                    return int(text, base=16)
            return float(text.replace(".", ""))  # Edge case: "-.inf"
        raise


def to_number(text):
    try:
        return int(text)
    except ValueError:
        return to_float(text)


def get_tzinfo(text):
    if text is None:
        return None
    if text == "Z":
        return UTC
    hours, _, minutes = text.partition(":")
    minutes = int(minutes) if minutes else 0
    offset = int(hours) * 3600 + minutes * 60
    return UTC if offset == 0 else dateutil.tz.tzoffset(text, offset)


def default_marshal(text):
    if not text:
        return text
    match = RE_SIMPLE_SCALAR.match(text)
    if match is None:
        return text
    _, constant, number, _, _, _, y, m, d, _, hh, mm, ss, sf, _, tz, _, _ = match.groups()
    if constant is not None:
        return CONSTANTS.get(constant.lower(), text)
    if number is not None:
        try:
            cleaned = cleaned_number(number)
            return to_number(cleaned)
        except ValueError:
            return text
    y = int(y)
    m = int(m)
    d = int(d)
    if hh is None:
        return datetime.date(y, m, d)
    hh = int(hh)
    mm = int(mm)
    ss = int(ss)
    sf = int(round(float(sf or 0) * 1000000))
    return datetime.datetime(y, m, d, hh, mm, ss, sf, get_tzinfo(tz))


def first_line_split_match(match):
    for g in (2, 4, 6):
        s = match.span(g)[0]
        if s >= 0:
            return s, match.group(g)
    return 0, None


def decode(value):
    """Python 2/3 friendly decoding of output"""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
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


def _todo():
    raise Exception("TODO")


class StackedElement(object):
    def __init__(self, root, indent):
        self.root = root  # type: ScannerStack
        self.indent = indent
        self.is_temp = False
        self.prev = None  # type: StackedElement
        self.value = None
        self.anchor_token = None  # type: AnchorToken
        self.tag_token = None  # type: TagToken

    def __repr__(self):
        return "%s%s%s" % (self.__class__.__name__[7], "" if self.indent is None else self.indent, self.represented_decoration())

    def represented_decoration(self):
        return "%s%s%s" % ("&" if self.anchor_token else "", "!" if self.tag_token else "", "<tmp>" if self.is_temp else "")

    def resolved_value(self):
        value = self.value
        if self.tag_token is not None:
            value = self.tag_token.marshalled(value)
        if self.anchor_token is not None:
            self.root.anchors[self.anchor_token.value] = value
        return value

    def wrap_up(self, value):
        self.push_value(value)

    def push_value(self, value):
        self.value = value

    def consume_dash(self, indent):
        pass

    def consume_colon(self, token):
        smap = StackedMap(self.root, token.indent)
        smap.consume_colon(token)
        self.push(smap)

    def push(self, element):
        if self.indent is None:
            element.is_temp = element.indent is not None
        self.root.decorate(element)
        element.prev = self
        self.root.head = element


class StackedScalar(StackedElement):
    def __init__(self, root, token):
        super(StackedScalar, self).__init__(root, token.indent)
        _todo()

    def consume_dash(self, indent):
        _todo()


class StackedList(StackedElement):
    def __init__(self, root, indent):
        super(StackedList, self).__init__(root, indent)
        self.value = []

    def push_value(self, value):
        self.value.append(value)


class StackedMap(StackedElement):
    def __init__(self, root, indent):
        super(StackedMap, self).__init__(root, indent)
        self.value = {}
        self.last_key = None

    def represented_decoration(self):
        return "%s%s" % (super(StackedMap, self).represented_decoration(), "" if self.last_key is None else ":")

    def wrap_up(self, value):
        if self.last_key is None:
            self.value[value] = None
        else:
            self.value[self.last_key] = value
            self.last_key = None

    def push_value(self, value):
        self.value[self.last_key] = value
        self.last_key = None

    def consume_dash(self, indent):
        _todo()

    def consume_colon(self, token):
        if self.indent is None or token.indent == self.indent:
            self.last_key = token.resolved_value(self.root)
        else:
            smap = StackedMap(self.root, token.indent)
            smap.consume_colon(token)
            self.push(smap)


class ScannerStack(object):
    def __init__(self):
        super(ScannerStack, self).__init__()
        self.docs = []
        self.directive = None
        self.head = StackedElement(self, 0)  # type: StackedElement
        self.anchors = {}
        self.anchor_token = None
        self.tag_token = None
        self.last_scalar = None

    def __repr__(self):
        stack = []
        head = self.head
        while head is not None:
            stack.append(str(head))
            head = head.prev
        return "%s [%s]" % (" / ".join(stack), self.represented_decoration())

    def represented_decoration(self):
        return "%s%s%s" % ("&" if self.anchor_token else "", "!" if self.tag_token else "", "" if self.last_scalar is None else "$")

    def decorate(self, target, line_number=None):
        if self.anchor_token is not None and (line_number is None or line_number == self.anchor_token.line_number):
            target.anchor_token = self.anchor_token
            if line_number is not None:
                target.indent = min(target.indent, self.anchor_token.indent)
            self.anchor_token = None
        if self.tag_token is not None and (line_number is None or line_number == self.tag_token.line_number):
            target.tag_token = self.tag_token
            if line_number is not None:
                target.indent = min(target.indent, self.tag_token.indent)
            self.tag_token = None

    def set_anchor_token(self, token):
        if self.anchor_token is not None:
            raise ParseError("Too many anchor tokens")
        self.anchor_token = token

    def set_tag_token(self, token):
        if self.tag_token is not None:
            raise ParseError("Too many tag tokens")
        self.tag_token = token

    def consume_dash(self, indent):
        self.auto_wrap_up()
        self.pop_until(indent)
        if self.head.indent is None:
            raise ParseError("Block sequence not allowed in flow")
        if indent > self.head.indent:
            self.head.push(StackedList(self, indent))
        self.head.consume_dash(indent)

    def consume_comma(self):
        assert self.head.indent is None or self.head.is_temp
        self.pop_temp()

    def pop_temp(self):
        while self.head.is_temp:
            self.pop()
        self.auto_wrap_up()

    def consume_colon(self, token):
        if self.last_scalar is None:
            token.value = ""
        else:
            token = self.last_scalar
            self.last_scalar = None
        self.pop_until(token.indent)
        self.head.consume_colon(token)

    def auto_wrap_up(self):
        if self.last_scalar is not None:
            token = self.last_scalar
            value = token.resolved_value(self)
            self.last_scalar = None
            self.head.wrap_up(value)

    def push_scalar(self, token):
        self.decorate(token, line_number=token.line_number)
        if self.last_scalar is not None:
            if self.head.indent is None or self.last_scalar.line_number == token.line_number:
                raise ParseError("2 consecutive scalars given")
            else:
                self.auto_wrap_up()
        self.last_scalar = token

    def pop(self):
        self.auto_wrap_up()
        popped = self.head
        self.head = popped.prev
        assert isinstance(popped, StackedElement)
        self.head.push_value(popped.resolved_value())

    def pop_until(self, indent):
        while self.head.indent is not None and self.head.indent > indent:
            self.pop()

    def pop_doc(self):
        if self.last_scalar is None and (self.anchor_token is not None or self.tag_token is not None):
            pass
        self.auto_wrap_up()
        while self.head.prev is not None:
            self.pop()
        if self.head.value is not None:
            self.docs.append(self.head.value)
            self.head.value = None
        self.anchors = {}
        self.directive = None


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
        :param ScannerStack root: Process this token on given 'root' node
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
        root.pop_doc()


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

    def consume_token(self, root):
        if root.directive is not None:
            raise ParseError("Duplicate directive")
        root.directive = self


class FlowMapToken(Token):
    def consume_token(self, root):
        root.head.push(StackedMap(root, None))


class FlowSeqToken(Token):
    def consume_token(self, root):
        root.head.push(StackedList(root, None))


class FlowEndToken(Token):
    def consume_token(self, root):
        root.pop_temp()
        assert root.head.indent is None
        root.pop()


class CommaToken(Token):
    def consume_token(self, root):
        root.consume_comma()


class DashToken(Token):
    def consume_token(self, root):
        root.consume_dash(self.indent)


class ColonToken(Token):
    def consume_token(self, root):
        root.consume_colon(self)


class TagToken(Token):
    def __init__(self, line_number, indent, text):
        super(TagToken, self).__init__(line_number, indent, text)
        self.marshaller = Marshallers.get_marshaller(text)

    def consume_token(self, root):
        root.set_tag_token(self)

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
        root.set_anchor_token(self)


class AliasToken(Token):
    def __init__(self, line_number, indent, text):
        super(AliasToken, self).__init__(line_number, indent)
        self.anchor = text[1:]

    def represented_value(self):
        return "*%s" % self.anchor

    def resolved_value(self, root):
        return self.value

    def consume_token(self, root):
        if self.anchor not in root.anchors:
            raise ParseError("Undefined anchor &%s" % self.anchor)
        if root.anchor_token is not None:
            raise ParseError("Anchors not allowed on aliases")
        if root.tag_token is not None:
            raise ParseError("Tags not allowed on aliases")
        self.value = root.anchors.get(self.anchor)
        root.push_scalar(self)


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

    def resolved_value(self, root):
        value = self.value
        if self.style is None and value is not None:
            value = value.strip()
        if self.tag_token is not None:
            value = self.tag_token.marshalled(value)
        elif self.style is None:
            value = default_marshal(value)
        if self.anchor_token:
            root.anchors[self.anchor_token.value] = value
        return value

    def append_text(self, text):
        if self.value is None:
            self.value = text
        elif not self.value:
            self.value = text
        elif self.value[-1] in " \n":
            self.value = "%s%s" % (self.value, text.lstrip())
        elif not text:
            self.value = "%s\n" % self.value
        else:
            self.value = "%s %s" % (self.value, text.lstrip())

    def consume_token(self, root):
        root.push_scalar(self)


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


def _checked_type(value, expected_type):
    if not isinstance(value, expected_type):
        raise ParseError("Expecting %s, got %s" % (expected_type.__name__, type(value).__name__))
    return value


class DefaultMarshaller:
    @staticmethod
    def get_marshaller(name):
        if not name:
            return DefaultMarshaller.non_specific
        return getattr(DefaultMarshaller, name, None)

    @staticmethod
    def non_specific(value):
        return value

    @staticmethod
    def map(value):
        return _checked_type(value, dict)

    @staticmethod
    def omap(value):
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            result = {}
            for item in value:
                result.update(item)
            return result
        raise ParseError("Can't transform %s to an ordered map" % type(value).__name__)

    @staticmethod
    def seq(value):
        return _checked_type(value, list)

    @staticmethod
    def set(value):
        return _checked_type(value, list)

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
        value = CONSTANTS.get(_checked_scalar(value).lower())
        if isinstance(value, bool):
            return value
        raise ParseError("'%s' is not a boolean" % value)

    @staticmethod
    def binary(value):
        return base64_decode(_checked_scalar(value))

    @staticmethod
    def date(value):
        value = default_marshal(_checked_scalar(value))
        if isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
            return value
        raise ParseError("'%s' is not a date" % value)

    @staticmethod
    def float(value):
        return to_float(_checked_scalar(value))


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
            self.generator = enumerate(buffer.read().splitlines(), start=1)
        else:
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
        return start + 2, DashToken(line_number, start + 1)

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
        return FlowMapToken(line_number, start)

    def consume_flow_map_end(self, line_number, start, _):
        self.pop_flow_ender("}")
        return FlowEndToken(line_number, start)

    def consume_flow_list_start(self, line_number, start, _):
        self.push_flow_ender("]")
        return FlowSeqToken(line_number, start)

    def consume_flow_list_end(self, line_number, start, _):
        self.pop_flow_ender("]")
        return FlowEndToken(line_number, start)

    @staticmethod
    def consume_comma(line_number, start, _):
        return CommaToken(line_number, start)

    def _multiline(self, line_number, start, line_size, line_text, style):
        regex = RE_DOUBLE_QUOTE_END if style == '"' else RE_SINGLE_QUOTE_END
        token = ScalarToken(line_number, start, "", style=style)
        try:
            start = start + 1
            if start < line_size and line_text[start] == style:
                token.value = ""
                start = start + 1
                if start >= line_size:
                    line_text = None
                return line_number, start, line_size, line_text, token
            lines = None
            m = None
            while m is None:
                m = regex.search(line_text, start)
                if m is not None:
                    end = m.span(1)[1]
                    text = line_text[start:end]
                    text = text[:-1] if text.endswith(style) else text[:-2]
                    line_size = len(line_text)
                    if lines is not None:
                        lines.append(text)
                        for line in lines:
                            token.append_text(line)
                        text = token.value
                    if style == "'":
                        token.value = text.replace("''", "'")
                    else:
                        token.value = codecs.decode(text, "unicode_escape")
                    if end >= line_size:
                        line_text = None
                    return line_number, end, line_size, line_text, token
                if lines is None:
                    lines = [line_text[start:]]
                    start = 0
                else:
                    lines.append(line_text)
                line_number, line_text = next(self.generator)
                line_text = line_text.strip()
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
        return style == ">", keep, indent, ScalarToken(line_number, indent, None, style=original)

    @staticmethod
    def _accumulate_literal(folded, lines, value):
        if not folded or not lines or not value:
            lines.append(value)
        elif (len(lines) > 1 or lines[0]) and not value.startswith(" ") and not lines[-1].startswith(" "):
            if lines[-1]:
                lines[-1] = "%s %s" % (lines[-1], value)
            else:
                lines[-1] = value
        else:
            lines.append(value)

    def _consume_literal(self, line_number, start, line_text):
        folded, keep, indent, token = self._get_literal_styled_token(line_number, start, de_commented(line_text[start:]))
        lines = []
        while True:
            try:
                line_number, line_text = next(self.generator)
                line_size = len(line_text)
                if line_size == 0:
                    self._accumulate_literal(folded, lines, line_text)
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
                token.indent = indent
                return line_number, 0, line_size, line_text, token
            self._accumulate_literal(folded, lines, line_text[indent:])

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
                while matched == "#" and line_text[start - 1] != " " \
                    or (self.flow_ender is not None and should_ignore(matched, start, line_text)):
                    start = start + 1
                    if start > line_size:
                        yield prev_start, line_text[prev_start:]
                        return
                    m = self.line_regex.search(line_text, start)
                    if m is None:
                        yield prev_start, line_text[prev_start:]
                        return
                    start, end = m.span(2)
                    matched = line_text[start]
                yield prev_start, line_text[prev_start:start]
            if matched == "#":
                return
            if matched == ":":
                yield start, matched
            else:
                yield start, line_text[start:end].strip()
            start = end

    def tokens(self):
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
                        pending.append_text("")
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
                            yield ColonToken(line_number, start)
                            continue
                        if pending is None:
                            if text[0] in "\"'":
                                line_number, start, line_size, upcoming, token = self._multiline(
                                    line_number, start, line_size, current_line, text[0]
                                )
                                break
                            if text[0] in '|>':
                                line_number, start, line_size, upcoming, token = self._consume_literal(line_number, start, current_line)
                                break
                        tokenizer = self.tokenizer_map.get(text[0])
                        if tokenizer is None:
                            if text[0] in RESERVED:
                                raise ParseError("Character '%s' is reserved" % text[0], line_number, start)
                            simple_key = ScalarToken(line_number, start, text)
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
                        yield ColonToken(line_number, start)
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

    def deserialized(self, simplified=True):
        token = None
        try:
            root = ScannerStack()
            for token in self.tokens():
                token.consume_token(root)
            if simplified:
                return simplified_docs(root.docs)
            return root.docs
        except ParseError as error:
            error.auto_complete(token)
            raise


def should_ignore(matched, start, line_text):
    """Yaml has so many weird edge cases... this one is to support sample 7.18"""
    try:
        if matched == ":" and line_text[start + 1] != " ":
            return line_text[start - 1] not in "'\""
    except IndexError:
        return line_text[start - 1] not in "'\""


def load(stream, simplified=True):
    """
    :param str|file stream: Stream or contents to load
    :param bool simplified: If True, return document itself when there was only one document (instead of list with 1 item)
    """
    scanner = Scanner(stream)
    return scanner.deserialized(simplified=simplified)


def load_string(contents, simplified=True):
    """
    :param str contents: Yaml to deserialize
    :param bool simplified: If True, return document itself when there was only one document (instead of list with 1 item)
    """
    scanner = Scanner(contents)
    return scanner.deserialized(simplified=simplified)


def load_path(path, simplified=True):
    """
    :param str path: Path to file to deserialize
    :param bool simplified: If True, return document itself when there was only one document (instead of list with 1 item)
    """
    with open(path) as fh:
        return load_string(fh.read(), simplified=simplified)


def simplified_docs(docs):
    if isinstance(docs, list) and len(docs) == 1:
        return docs[0]
    return docs
