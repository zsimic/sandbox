import codecs
import collections
import datetime
import dateutil
import re
import sys
# import os


PY2 = sys.version_info < (3, 0)
# DEBUG = os.environ.get("TRACE_YAML")
RESERVED = "@`"
RE_HEADERS = re.compile(r"^(\s*(#).*|(\s*(%.*?)(\s+#.*)?)|(---)(\s.*)?|(\.\.\.)(\s.*)?)$")
RE_BLOCK_SEQUENCE = re.compile(r"\s*((-\s+\S)|-\s*$)")
RE_FLOW_SEP = re.compile(r"""(#|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{},])\s*(\S?)""")
RE_BLOCK_SEP = re.compile(r"""(#|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{}])\s*(\S?)""")
RE_DOUBLE_QUOTE_END = re.compile(r'([^\\]")\s*(.*?)\s*$')
RE_SINGLE_QUOTE_END = re.compile(r"([^']'([^']|$))")
RE_CONTENT = re.compile(r"\s*(.*?)\s*$")


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


# def trace(message, *args):
#     """Output 'message' if tracing is on"""
#     if DEBUG:
#         if args:
#             message = message.format(*args)
#         sys.stderr.write(":: %s\n" % message)
#         sys.stderr.flush()


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


def shortened(text, size=32):
    text = str(text)
    if not text or len(text) < size:
        return text
    return "%s..." % text[:size]


def double_quoted(text):
    text = decode(codecs.encode(str(text), "unicode_escape"))
    return '"%s"' % text.replace('"', '\\"')


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
    text = cleaned_number(text)
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
            return to_number(number)
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


def _todo():
    raise Exception("TODO")


def _dbg_repr(value):
    if isinstance(value, tuple):
        if value[1] is None or value[1] is False:
            return ""
        return value[0]
    return str(value)


def dbg(*args):
    return "".join(_dbg_repr(s) for s in args if s is not None)


class StackedDocument(object):
    def __init__(self):
        self.indent = -1
        self.root = None  # type: ScannerStack
        self.prev = None  # type: StackedDocument
        self.value = None
        self.anchor_token = None  # type: AnchorToken
        self.tag_token = None  # type: TagToken
        self.is_key = False
        self.closed = False

    def __repr__(self):
        indent = self.indent if self.indent != -1 else None
        return dbg(self.__class__.__name__[7], indent, self.represented_decoration())

    def attach(self, root):
        self.root = root

    def underranks(self, indent):
        if indent is None:
            return self.indent is not None
        elif self.indent is None:
            return False
        return self.indent > indent

    def represented_decoration(self):
        return dbg(("&", self.anchor_token), ("!", self.tag_token), (":",  self.is_key))

    def needs_new_list(self, indent):
        return True

    def resolved_value(self):
        value = self.value
        if self.tag_token is not None:
            value = self.tag_token.marshalled(value)
        if self.anchor_token is not None:
            self.root.anchors[self.anchor_token.value] = value
        return value

    def mark_open(self, token):
        self.closed = False

    def mark_as_key(self, token):
        self.is_key = True

    def take_key(self, element):
        self.root.pop_until(element.indent)
        if self.root.head.indent != element.indent:
            self.root.push(StackedMap(element.indent))
        self.root.head.take_key(element)

    def take_value(self, element):
        if self.value is not None:
            raise ParseError("Document separator expected", element)
        self.value = element.resolved_value()

    def consume_scalar(self, token):
        self.root.push(StackedScalar(token))


class StackedScalar(StackedDocument):
    def __init__(self, token):
        super(StackedScalar, self).__init__()
        self.indent = token.indent
        self.line_number = token.line_number
        self.token = token

    def needs_new_list(self, indent):
        _todo()

    def attach(self, root):
        self.root = root
        self.value = self.token.resolved_value(self.anchor_token is None and self.tag_token is None)

    def underranks(self, indent):
        return True

    def take_key(self, element):
        _todo()

    def take_value(self, element):
        if element.indent is None:
            raise ParseError("Missing comma between scalar and entry in flow", self.token)
        raise ParseError("2 consecutive scalars")

    def consume_scalar(self, token):
        if self.prev.indent is None:
            raise ParseError("Missing comma between scalars in flow", self.token)
        self.root.pop()
        self.root.push(StackedScalar(token))


class StackedList(StackedDocument):
    def __init__(self, indent):
        super(StackedList, self).__init__()
        self.indent = indent
        self.value = []

    def needs_new_list(self, indent):
        i = self.indent
        if i is None:
            raise ParseError("Block not allowed in flow")
        if i == indent:
            return False
        if i < indent:
            return True
        raise ParseError("Bad sequence entry indentation")

    def mark_as_key(self, token):
        scalar = token.new_tacked_scalar()
        scalar.is_key = True
        self.root.push(scalar)

    def take_value(self, element):
        if self.closed:
            raise ParseError("Missing comma in list")
        self.value.append(element.resolved_value())
        self.closed = self.indent is None


class StackedMap(StackedDocument):
    def __init__(self, indent):
        super(StackedMap, self).__init__()
        self.indent = indent
        self.value = {}
        self.last_key = None
        self.has_key = False

    def represented_decoration(self):
        return dbg(super(StackedMap, self).represented_decoration(), ("*",  self.last_key))

    def needs_new_list(self, indent):
        i = self.indent
        if i is None:
            raise ParseError("Block not allowed in flow")
        if i >= indent:
            raise ParseError("Bad sequence entry indentation")
        return True

    def resolved_value(self):
        if self.has_key:
            self.add_key_value(self.last_key, None)
        return super(StackedMap, self).resolved_value()

    def mark_open(self, token):
        if self.has_key:
            self.root.push(token.new_tacked_scalar())
            self.root.pop()
        self.closed = False

    def mark_as_key(self, token):
        scalar = token.new_tacked_scalar()
        scalar.is_key = True
        self.root.push(scalar)

    def add_key_value(self, key, value):
        if self.closed:
            raise ParseError("Missing comma in map")
        try:
            self.value[key] = value
        except TypeError:
            raise ParseError("Key '%s' is not hashable" % shortened(str(key)))
        self.closed = self.indent is None
        self.last_key = None
        self.has_key = False

    def check_key(self, element):
        if self.indent is not None and element.indent != self.indent:
            raise ParseError("Key '%s' is not indented properly" % shortened(element.value))

    def take_key(self, element):
        if self.indent is not None and element.indent is not None and element.indent != self.indent:
            # We're pushing a sub-mpa of the form "a:\n  b: ..."
            return super(StackedMap, self).take_key(element)
        if self.has_key and element.indent == self.indent:
            self.add_key_value(self.last_key, None)
        self.check_key(element)
        self.last_key = element.resolved_value()
        self.has_key = True

    def take_value(self, element):
        if self.has_key:
            self.add_key_value(self.last_key, element.resolved_value())
        else:
            self.check_key(element)
            self.add_key_value(element.resolved_value(), None)


class ScannerStack(object):
    def __init__(self):
        super(ScannerStack, self).__init__()
        self.docs = []
        self.directive = None
        self.head = StackedDocument()  # type: StackedDocument
        self.head.root = self
        self.anchors = {}
        self.anchor_token = None
        self.tag_token = None
        self.secondary_anchor_token = None
        self.secondary_tag_token = None

    def __repr__(self):
        stack = []
        head = self.head
        while head is not None:
            stack.append(str(head))
            head = head.prev
        result = " / ".join(stack)
        deco = self.represented_decoration()
        if deco:
            result = "%s [%s]" % (result, deco)
        return result

    def represented_decoration(self):
        return dbg(
            ("&", self.anchor_token),
            ("&", self.secondary_anchor_token),
            ("!", self.tag_token),
            ("!", self.secondary_tag_token),
        )

    def decorate(self, target, name, secondary_name):
        line_number = getattr(target, "line_number", None)
        tag = getattr(self, name)
        if tag is not None and (line_number is None or line_number == tag.line_number):
            setattr(target, name, tag)
            if line_number is not None:
                target.indent = min(target.indent, tag.indent)
            setattr(self, name, getattr(self, secondary_name))
            setattr(self, secondary_name, None)

    def attach(self, target):
        self.decorate(target, "anchor_token", "secondary_anchor_token")
        self.decorate(target, "tag_token", "secondary_tag_token")
        target.attach(self)

    def _set_decoration(self, token, name, secondary_name):
        tag = getattr(self, name)
        if tag is not None:
            if tag.line_number == token.line_number or getattr(self, secondary_name) is not None:
                raise ParseError("Too many %ss" % name.replace("_", " "), token)
            setattr(self, secondary_name, tag)
        setattr(self, name, token)

    def set_anchor_token(self, token):
        self._set_decoration(token, "anchor_token", "secondary_anchor_token")

    def set_tag_token(self, token):
        self._set_decoration(token, "tag_token", "secondary_tag_token")

    def push(self, element):
        """
        :param StackedDocument element:
        """
        self.attach(element)
        element.prev = self.head
        self.head = element

    def pop(self):
        popped = self.head
        if popped.prev is None:
            raise ParseError("Premature end of document")
        self.head = popped.prev
        if popped.is_key:
            self.head.take_key(popped)
        else:
            self.head.take_value(popped)

    def pop_until(self, indent):
        while self.head.underranks(indent):
            self.pop()

    def pop_doc(self):
        while self.head.prev is not None:
            self.pop()
        if self.head.value is not None:
            self.docs.append(self.head.value)
            # trace("---\n{}\n---", self.head.value)
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
        result= "%s[%s,%s]" % (self.__class__.__name__, self.line_number, self.column)
        if self.value is not None:
            result = "%s %s" % (result, self.represented_value())
        return result

    @property
    def column(self):
        return self.indent + 1

    def represented_value(self):
        return str(self.value)

    def new_tacked_scalar(self, text=""):
        return StackedScalar(ScalarToken(self.line_number, self.indent, text))

    def consume_token(self, root):
        """
        :param ScannerStack root: Process this token on given 'root' node
        """


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    def consume_token(self, root):
        if root.tag_token and root.tag_token.line_number == self.line_number:  # last line finished with a tag (but no value)
            root.push(self.new_tacked_scalar())
        root.pop_doc()


class DocumentStartToken(Token):
    def consume_token(self, root):
        root.pop_doc()


class DocumentEndToken(Token):
    def consume_token(self, root):
        if root.tag_token and root.tag_token.line_number == self.line_number - 1:  # last line finished with a tag (but no value)
            root.push(self.new_tacked_scalar())
        if root.head.prev is None and root.head.value is None:  # doc was empty, no tokens
            root.docs.append(None)
        else:
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
        root.push(StackedMap(None))


class FlowSeqToken(Token):
    def consume_token(self, root):
        root.push(StackedList(None))


class FlowEndToken(Token):
    def consume_token(self, root):
        root.pop_until(None)
        root.pop()


class CommaToken(Token):
    def consume_token(self, root):
        root.pop_until(None)
        root.head.mark_open(self)


class DashToken(Token):
    @property
    def column(self):
        return self.indent

    def consume_token(self, root):
        root.pop_until(self.indent)
        if root.head.needs_new_list(self.indent):
            root.push(StackedList(self.indent))


class ColonToken(Token):
    def consume_token(self, root):
        root.head.mark_as_key(self)
        root.pop()


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
        except ValueError:
            raise ParseError("'%s' can't be converted using %s" % (shortened(value), self.value), self)


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

    def resolved_value(self, clean):
        if not clean:
            raise ParseError("Alias should not have any properties")
        return self.value

    def consume_token(self, root):
        if self.anchor not in root.anchors:
            raise ParseError("Undefined anchor &%s" % self.anchor)
        self.value = root.anchors.get(self.anchor)
        root.head.consume_scalar(self)


class ScalarToken(Token):
    def __init__(self, line_number, indent, text, style=None):
        super(ScalarToken, self).__init__(line_number, indent, text)
        self.style = style

    def represented_value(self):
        if self.style == "'":
            return "'%s'" % self.value.replace("'", "''").replace("\n", "\\n")
        if self.style is None or self.style == '"':
            return double_quoted(self.value)
        return "%s %s" % (self.style, double_quoted(self.value))

    def resolved_value(self, clean):
        value = self.value
        if self.style is None and value is not None:
            value = value.strip()
        if clean and self.style is None:
            value = default_marshal(value)
        return value

    def append_text(self, text):
        if self.value is None:
            self.value = text
        elif not self.value:
            self.value = text
        elif self.value[-1] in " \t\n":
            self.value = "%s%s" % (self.value, text.lstrip())
        elif not text:
            self.value = "%s\n" % self.value
        else:
            self.value = "%s %s" % (self.value, text.lstrip())

    def consume_token(self, root):
        root.head.consume_scalar(self)


class ParseError(Exception):
    def __init__(self, message, *context):
        self.message = message
        self.line_number = None
        self.column = None
        self.auto_complete(*context)

    def __str__(self):
        coords = ""
        if self.line_number is not None:
            coords += " line %s" % self.line_number
        if self.column is not None:
            coords += " column %s" % self.column
        if coords:
            coords = ",%s" % coords
        return "%s%s" % (self.message, coords)

    def complete_coordinates(self, line_number, column):
        if self.line_number is None:
            self.line_number = line_number
        if self.column is None:
            self.column = column

    def auto_complete(self, *context):
        if not context:
            return
        if len(context) == 2 and isinstance(context[0], int) and isinstance(context[1], int):
            self.complete_coordinates(context[0], context[1] + 1)
            return
        for c in context:
            column = getattr(c, "column", None)
            if column is None:
                column = getattr(c, "indent", None)
                if column is not None:
                    column = column + 1
            self.complete_coordinates(getattr(c, "line_number", None), column)


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
        if isinstance(value, dict):
            value = list(value.keys())
        return set(_checked_type(value, list))

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
        raise ValueError()

    @staticmethod
    def binary(value):
        return base64_decode(_checked_scalar(value))

    @staticmethod
    def date(value):
        value = default_marshal(_checked_scalar(value))
        if isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
            return value
        raise ValueError()

    @staticmethod
    def float(value):
        return to_float(cleaned_number(_checked_scalar(value)))


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

    def push_flow_ender(self, ender):
        if self.flow_ender is None:
            self.flow_ender = collections.deque()
            self.line_regex = RE_FLOW_SEP
        self.flow_ender.append(ender)

    def pop_flow_ender(self, found):
        if self.flow_ender is None:
            raise ParseError("'%s' without corresponding opener" % found)
        expected = self.flow_ender.pop()
        if not self.flow_ender:
            self.flow_ender = None
            self.line_regex = RE_BLOCK_SEP
        if expected != found:
            raise ParseError("Expecting '%s', but found '%s'" % (expected, found))

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

    def _checked_string(self, line_number, start, end, line_text, token):
        if start >= end:
            line_text = None
            start = 0
        return line_number, start, end, line_text, token

    def _double_quoted(self, line_number, start, end, line_text):
        token = ScalarToken(line_number, start, "", style='"')
        try:
            if start < end and line_text[start] == '"':  # Empty string
                return self._checked_string(line_number, start + 1, end, line_text, [token])
            lines = None
            m = None
            while m is None:
                m = RE_DOUBLE_QUOTE_END.search(line_text, start)
                if m is not None:
                    text = line_text[start:m.span(1)[1] - 1]
                    if lines is not None:
                        lines.append(text)
                        for line in lines:
                            token.append_text(line)
                        text = token.value
                    token.value = codecs.decode(text, "unicode_escape")
                    start, end = m.span(2)
                    return self._checked_string(line_number, start, end, line_text, [token])
                if lines is None:
                    lines = [line_text[start:]]
                    start = 0
                else:
                    lines.append(line_text)
                line_number, line_text = next(self.generator)
                line_text = line_text.strip()
        except StopIteration:
            raise ParseError("Unexpected end, runaway double-quoted string at line %s?" % token.line_number)

    def _single_quoted(self, line_number, start, end, line_text):
        token = ScalarToken(line_number, start, "", style="'")
        try:
            if start < end and line_text[start] == "'":  # Empty string
                return self._checked_string(line_number, start + 1, end, line_text, [token])
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
                        for line in lines:
                            token.append_text(line)
                        text = token.value
                    token.value = text.replace("''", "'")
                    m = RE_CONTENT.search(line_text, quote_pos + 1)
                    start, end = m.span(1)
                    return self._checked_string(line_number, start, end, line_text, [token])
                if lines is None:
                    lines = [line_text[start:]]
                    start = 0
                else:
                    lines.append(line_text)
                line_number, line_text = next(self.generator)
                line_text = line_text.strip()
        except StopIteration:
            raise ParseError("Unexpected end, runaway single-quoted string at line %s?" % token.line_number)

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
        elif (len(lines) > 1 or lines[0]) and value[0] not in " " and not lines[-1].startswith(" "):
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
                m = RE_CONTENT.match(line_text)
                start, end = m.span(1)
                if start == end:
                    self._accumulate_literal(folded, lines, line_text)
                    continue
            except StopIteration:
                line_number += 1
                line_text = ""
                start = end = 0
            if indent is None:
                token.indent = indent = start if start != 0 else 1
            if start < indent:
                if not lines:
                    raise ParseError("Bad literal indentation")
                text = "\n".join(lines)
                if keep is None:
                    token.value = "%s\n" % text.rstrip()
                elif keep is False:
                    token.value = text.rstrip()
                else:
                    token.value = "%s\n" % text
                if start >= end:
                    line_text = None
                return line_number, 0, end, line_text, [token]
            self._accumulate_literal(folded, lines, line_text[indent:])

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
                continue
            if self.flow_ender is None:
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
                actionable = rstart == end or line_text[mstart - 1] == '"' or line_text[mstart + 1] in " \t"
            else:
                actionable = start == mstart or matched in "{}[],"
            if actionable:
                if start < mstart:
                    yield None, start, line_text[start:mstart].rstrip()
                yield matched, mstart, line_text[mstart:mend]
                start = rstart
        if start < end:
            yield None, start, line_text[start:end]

    def header_token(self, tokens, pending, line_number, start, line_text):
        if start == 0:
            m = RE_HEADERS.match(line_text)
            if m is not None:
                if tokens is None:
                    tokens = [] if pending is None else [consumed_pending(*pending)]
                    pending = None
                marker = max(m.span(6)[0], m.span(8)[0])
                if marker >= 0:
                    token = DocumentStartToken if line_text[marker] == "-" else DocumentEndToken
                    tokens.append(token(line_number, 0))
                    start = max(m.span(7)[0], m.span(9)[0])
                    if start < 0:
                        return True, tokens, pending, line_number, 0, None
                    return False, tokens, pending, line_number, start, line_text
                dstart, dend = m.span(4)
                if dstart >= 0:
                    if dstart != 0:
                        raise ParseError("Directive must not be indented", line_number, dstart)
                    tokens.append(DirectiveToken(line_number, 0, line_text[dstart:dend]))
                return True, tokens, pending, line_number, 0, None
        m = RE_BLOCK_SEQUENCE.match(line_text, start)
        if m is None:
            return False, tokens, pending, line_number, start, line_text
        if tokens is None:
            tokens = [] if pending is None else [consumed_pending(*pending)]
            pending = None
        tokens.append(DashToken(line_number, m.span(1)[0] + 1))
        if m.span(2)[0] == -1:
            return True, tokens, pending, line_number, 0, None
        return False, tokens, pending, line_number, m.span(2)[1] - 1, line_text

    def headers(self, pending, line_number, start, line_text):
        tokens = None
        while True:
            if line_text is None:
                try:
                    line_number, line_text = next(self.generator)
                    start = 0
                except StopIteration:
                    if tokens:
                        return tokens, pending, line_number, 0, 0, None
                    raise
            tbc, tokens, pending, line_number, start, line_text = self.header_token(tokens, pending, line_number, start, line_text)
            if not tbc:
                break
        m = RE_CONTENT.match(line_text, start)
        start, end = m.span(1)
        if pending is not None and start == end and pending[0].style is None:
            pending.append("")
        return tokens, pending, line_number, start, end, line_text

    def tokens(self):
        line_number = start = end = offset = 0
        pending = simple_key = upcoming = None
        try:
            yield StreamStartToken(1, 0)
            while True:
                if simple_key is not None:
                    if pending is None:
                        pending = [simple_key]
                    else:
                        pending.append(simple_key.value)
                    simple_key = None
                if start == 0 or upcoming is None:
                    tokens, pending, line_number, start, end, line_text = self.headers(pending, line_number, start, upcoming)
                    if tokens is not None:
                        for token in tokens:
                            yield token
                    if line_text is None:
                        raise StopIteration()
                else:
                    line_text = upcoming
                    if pending is not None:
                        yield consumed_pending(*pending)
                        pending = None
                upcoming = None
                for matched, offset, text in self.next_match(start, end, line_text):
                    if simple_key is None:
                        if matched is None:
                            if text[0] in RESERVED:
                                raise ParseError("Character '%s' is reserved" % text[0], line_number, offset)
                            if pending is None:
                                if text[0] == '"':
                                    line_number, start, end, upcoming, pending = self._double_quoted(line_number, offset + 1, end, line_text)
                                    break
                                if text[0] == "'":
                                    line_number, start, end, upcoming, pending = self._single_quoted(line_number, offset + 1, end, line_text)
                                    break
                                if text[0] in '|>':
                                    line_number, start, end, upcoming, pending = self._consume_literal(line_number, offset, line_text)
                                    break
                            simple_key = ScalarToken(line_number, offset, text)
                            continue
                        if matched == ":":
                            yield ColonToken(line_number, offset)
                            continue
                        tokenizer = self.tokenizer_map.get(matched)
                        if tokenizer is None:
                            print("--> %s %s %s %s" % (line_number, matched, offset, text))
                        if pending is not None:
                            yield consumed_pending(*pending)
                            pending = None
                        yield tokenizer(line_number, offset, text)
                    elif matched == ":":
                        if pending is not None:
                            yield consumed_pending(*pending)
                            pending = None
                        yield simple_key
                        simple_key = None
                        yield ColonToken(line_number, offset)
                    else:
                        tokenizer = self.tokenizer_map.get(matched)
                        if pending is None:
                            yield simple_key
                        else:
                            pending.append(simple_key.value)
                            yield consumed_pending(*pending)
                            pending = None
                        simple_key = None
                        yield tokenizer(line_number, offset, text)
        except StopIteration:
            if pending is not None:
                if simple_key is not None:
                    pending.append(simple_key.value)
                    simple_key = None
                yield consumed_pending(*pending)
            if simple_key is not None:
                yield simple_key
            yield StreamEndToken(line_number, 0)
        except ParseError as error:
            error.auto_complete(line_number, offset)
            raise

    def deserialized(self, simplified=True):
        token = None
        try:
            root = ScannerStack()
            for token in self.tokens():
                token.consume_token(root)
                # trace("{}: {}", token, root)
            if simplified:
                if not root.docs:
                    return None
                if len(root.docs) == 1:
                    return root.docs[0]
            return root.docs
        except ParseError as error:
            error.auto_complete(token)
            raise


def yaml_lines(text, *lines):
    empty = 0
    for line in lines:
        if not text:
            text = line
        elif not line:
            empty = empty + 1
        else:
            if empty > 0:
                text = "%s%s%s" % (text, "\n" * empty, line)
                empty = 0
            else:
                text = "%s %s" % (text, line)
    return text


def consumed_pending(scalar, *lines):
    if lines:
        scalar.value = yaml_lines(scalar.value, *lines)
    return scalar


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
