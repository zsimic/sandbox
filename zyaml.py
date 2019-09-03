import codecs
import collections
import datetime
import dateutil
import re
import sys
# import os


# DEBUG = os.environ.get("TRACE_YAML")
PY2 = sys.version_info < (3, 0)
RESERVED = "@`"
RE_HEADERS = re.compile(r"^(\s*#|\s*%|(---|\.\.\.)(\s|$))")
RE_BLOCK_SEQUENCE = re.compile(r"\s*((-\s+\S)|-\s*$)")
RE_FLOW_SEP = re.compile(r"""(#|\?\s|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{},])\s*(\S?)""")
RE_BLOCK_SEP = re.compile(r"""(#|\?\s|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{}])\s*(\S?)""")
RE_DOUBLE_QUOTE_END = re.compile(r'([^\\]")\s*(.*?)\s*$')
RE_SINGLE_QUOTE_END = re.compile(r"([^']'([^']|$))")
RE_CONTENT = re.compile(r"\s*(.*?)\s*$")
RE_COMMENT = re.compile(r"\s+#.*$")


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
    from typing import List, Optional

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


def _dbg_repr(value):
    if isinstance(value, tuple):
        if value[1] is None or value[1] is False:
            return "" if len(value) < 3 else value[2]
        return value[0]
    return str(value)


def dbg(*args):
    return "".join(_dbg_repr(s) for s in args if s is not None)


class StackedDocument(object):
    def __init__(self):
        self.indent = -1
        self.root = None  # type: Optional[ScannerStack]
        self.prev = None  # type: Optional[StackedDocument]
        self.value = None
        self.anchor_token = None  # type: Optional[AnchorToken]
        self.tag_token = None  # type: Optional[TagToken]
        self.is_key = False
        self.closed = False

    def __repr__(self):
        return "%s %s" % (self.dbg_representation(), self.value)

    def type_name(self):
        return self.__class__.__name__.replace("Stacked", "").lower()

    def dbg_representation(self):
        indent = self.indent if self.indent != -1 else None
        return dbg(self.__class__.__name__[7], indent, self.represented_decoration())

    def represented_decoration(self):
        return dbg(("&", self.anchor_token), ("!", self.tag_token), (":",  self.is_key))

    def check_indentation(self, indent, name, offset=0):
        if indent is not None:
            si = self.indent
            if si is not None and si >= 0:
                si = si + offset
                if indent < si:
                    raise ParseError("%s must be indented at least %s columns" % (name, si + 1), None, indent)

    def check_value_indentation(self, indent):
        self.check_indentation(indent, "Value")

    def attach(self, root):
        self.root = root

    def under_ranks(self, indent):
        if indent is None:
            return self.indent is not None
        elif self.indent is None:
            return False
        return self.indent > indent

    def consume_dash(self, token):
        self.root.push(StackedList(token.indent))

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
        ei = element.indent
        self.root.pop_until(ei)
        if self.root.head.indent != ei:
            self.root.push(StackedMap(ei))
        self.root.head.take_key(element)

    def take_value(self, element):
        if self.value is not None:
            raise ParseError("Document separator expected", element)
        self.check_value_indentation(element.indent)
        self.value = element.resolved_value()

    def consume_scalar(self, token):
        self.root.push(StackedScalar(token))


class StackedScalar(StackedDocument):
    def __init__(self, token):
        super(StackedScalar, self).__init__()
        self.indent = token.indent
        self.linenum = token.linenum
        self.token = token

    def attach(self, root):
        self.root = root
        self.value = self.token.resolved_value(self.anchor_token is None and self.tag_token is None)

    def under_ranks(self, indent):
        return True

    def take_value(self, element):
        if element.indent is None:
            raise ParseError("Missing comma between %s and %s in flow" % (self.type_name(), element.type_name()), self.token)

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

    def consume_dash(self, token):
        i = self.indent
        if i is None:
            raise ParseError("Block not allowed in flow")
        if i == token.indent:
            return
        self.root.push(StackedList(token.indent))

    def mark_as_key(self, token):
        scalar = token.new_tacked_scalar()
        scalar.is_key = True
        self.root.push(scalar)

    def take_key(self, element):
        ei = element.indent
        self.root.pop_until(ei)
        if self.root.head.indent != ei:
            self.root.push(StackedMap(ei))
        if self.root.head is self:
            raise ParseError("List values are not allowed here")
        self.root.head.take_key(element)

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

    def check_key_indentation(self, indent):  # type: (Optional[int]) -> None
        if self.indent is not None and indent != self.indent:
            raise ParseError("Key is not indented properly", None, indent)

    def check_value_indentation(self, indent):  # type: (Optional[int]) -> None
        self.check_indentation(indent, "Value", offset=1)

    def consume_dash(self, token):
        i = self.indent
        if i is None:
            raise ParseError("Block not allowed in flow")
        if i >= token.indent:
            raise ParseError("Bad sequence entry indentation")
        self.root.push(StackedList(token.indent))

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

    def take_key(self, element):
        ei = element.indent
        if self.indent is not None and ei is not None and ei != self.indent:
            # We're pushing a sub-map of the form "a:\n  b: ..."
            if not self.has_key and ei > self.indent:
                raise ParseError("Mapping values are not allowed here")
            return super(StackedMap, self).take_key(element)
        if self.has_key and ei == self.indent:
            self.add_key_value(self.last_key, None)
        self.check_key_indentation(ei)
        self.last_key = element.resolved_value()
        self.has_key = True

    def take_value(self, element):
        if self.has_key:
            self.check_value_indentation(element.indent)
            self.add_key_value(self.last_key, element.resolved_value())
        else:
            self.check_key_indentation(element.indent)
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
            stack.append(head.dbg_representation())
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
        linenum = getattr(target, "linenum", None)
        tag = getattr(self, name)
        if tag is not None and (linenum is None or linenum == tag.linenum):
            setattr(target, name, tag)
            if linenum is not None:
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
            if tag.linenum == token.linenum or getattr(self, secondary_name) is not None:
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
        while self.head.under_ranks(indent):
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

    def __init__(self, linenum, indent, value=None):
        self.linenum = linenum
        self.indent = indent
        self.value = value

    def __repr__(self):
        result = "%s[%s,%s]" % (self.__class__.__name__, self.linenum, self.column)
        if self.value is not None:
            result = "%s %s" % (result, self.represented_value())
        return result

    @property
    def column(self):
        return self.indent + 1

    def represented_value(self):
        return str(self.value)

    def new_tacked_scalar(self, text=""):
        return StackedScalar(ScalarToken(self.linenum, self.indent, text))

    def consume_token(self, root):
        """
        :param ScannerStack root: Process this token on given 'root' node
        """


class StreamStartToken(Token):
    pass


class StreamEndToken(Token):
    def consume_token(self, root):
        if root.tag_token and root.tag_token.linenum == self.linenum:  # last line finished with a tag (but no value)
            root.push(root.tag_token.new_tacked_scalar())
        root.pop_doc()


class DocumentStartToken(Token):
    def consume_token(self, root):
        root.pop_doc()


class DocumentEndToken(Token):
    def consume_token(self, root):
        if root.tag_token and root.tag_token.linenum == self.linenum - 1:  # last line finished with a tag (but no value)
            root.push(root.tag_token.new_tacked_scalar())
        if root.head.prev is None and root.head.value is None:  # doc was empty, no tokens
            root.docs.append(None)
        else:
            root.pop_doc()


class DirectiveToken(Token):
    def __init__(self, linenum, indent, text):
        m = RE_COMMENT.search(text)
        if m is not None:
            text = text[:m.start()]
        if text.startswith("%YAML"):
            self.name = "%YAML"
            text = text[5:].strip()
        elif text.startswith("%TAG"):
            self.name = "%TAG"
            text = text[4:].strip()
        else:
            self.name, _, text = text.partition(" ")
        super(DirectiveToken, self).__init__(linenum, indent, text.strip())

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


class ExplicitMapToken(Token):
    def __init__(self, linenum, indent):
        super(ExplicitMapToken, self).__init__(linenum, indent + 2)

    def consume_token(self, root):
        root.pop_until(self.indent)
        if not isinstance(root.head, StackedMap) or (root.head.indent is not None and root.head.indent != self.indent):
            root.push(StackedMap(self.indent))


class DashToken(Token):
    @property
    def column(self):
        return self.indent

    def consume_token(self, root):
        root.pop_until(self.indent)
        root.head.consume_dash(self)


class ColonToken(Token):
    def consume_token(self, root):
        root.head.mark_as_key(self)
        root.pop()


class TagToken(Token):
    def __init__(self, linenum, indent, text):
        super(TagToken, self).__init__(linenum, indent, text)
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
    def __init__(self, linenum, indent, text):
        super(AnchorToken, self).__init__(linenum, indent, text[1:])

    def represented_value(self):
        return "&%s" % self.value

    def consume_token(self, root):
        root.set_anchor_token(self)


class AliasToken(Token):
    def __init__(self, linenum, indent, text):
        super(AliasToken, self).__init__(linenum, indent)
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
    def __init__(self, linenum, indent, text, style=None):
        super(ScalarToken, self).__init__(linenum, indent, text)
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

    def consume_token(self, root):
        root.head.consume_scalar(self)


class ParseError(Exception):
    def __init__(self, message, *context):
        self.message = message
        self.linenum = None
        self.column = None
        self.auto_complete(*context)

    def __str__(self):
        coords = ""
        if self.linenum is not None:
            coords += " line %s" % self.linenum
        if self.column is not None:
            coords += " column %s" % self.column
        if coords:
            coords = ",%s" % coords
        return "%s%s" % (self.message, coords)

    def complete_coordinates(self, linenum, column):
        if self.linenum is None and isinstance(linenum, int):
            self.linenum = linenum
        if self.column is None and isinstance(column, int):
            self.column = column

    def auto_complete(self, *context):
        if not context:
            return
        if len(context) == 2:
            self.complete_coordinates(context[0], context[1] + 1 if isinstance(context[1], int) else None)
            return
        for c in context:
            column = getattr(c, "column", None)
            if column is None:
                column = getattr(c, "indent", None)
                if column is not None:
                    column = column + 1
            self.complete_coordinates(getattr(c, "linenum", None), column)


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
        self.simple_key = None  # type: Optional[ScalarToken]
        self.pending_dash = None  # type: Optional[DashToken]
        self.pending_scalar = None  # type: Optional[ScalarToken]
        self.pending_lines = None  # type: Optional[List[str]]
        self.pending_tokens = None  # type: Optional[List[Token]]
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
            "?": self.consume_map,
        }

    def __repr__(self):
        return dbg(
            ("flow mode ", self.flow_ender, "block mode "),
            ("K", self.simple_key), ("S", self.pending_scalar), ("L", self.pending_lines),
            ("T", self.pending_tokens), ("-", self.pending_dash)
        )

    def promote_simple_key(self):
        if self.simple_key is not None:
            if self.pending_scalar is None:
                self.pending_scalar = self.simple_key
            elif self.simple_key.indent == 0 and self.simple_key.indent != self.pending_scalar.indent:
                raise ParseError("Simple key must be indented in order to continue previous line")
            else:
                if self.pending_lines is None:
                    self.pending_lines = []
                self.pending_lines.append(self.simple_key.value)
            self.simple_key = None

    def promote_pending_scalar(self):
        if self.pending_scalar is not None:
            if self.pending_lines is not None:
                self.pending_scalar.value = yaml_lines(self.pending_lines, text=self.pending_scalar.value)
            self.add_pending_token(self.pending_scalar)
            self.pending_scalar = None
            self.pending_lines = None

    def is_dash_meaningful(self, linenum, indent):
        if self.pending_dash is not None:
            return linenum == self.pending_dash.linenum or indent == self.pending_dash.indent
        if self.pending_scalar is not None:
            return indent < self.pending_scalar.indent
        return True

    def add_pending_dash(self, linenum, indent):
        if self.is_dash_meaningful(linenum, indent):
            self.pending_dash = DashToken(linenum, indent)
            self.add_pending_token(self.pending_dash)
        else:
            self.add_pending_line("-")

    def add_pending_token(self, token):
        if self.pending_tokens is None:
            self.pending_tokens = []
        self.pending_tokens.append(token)

    def add_pending_line(self, text):
        if self.pending_lines is None:
            self.pending_lines = []
        self.pending_lines.append(text)

    def consumed_pending(self):
        if self.pending_scalar is not None:
            if self.pending_lines is not None:
                self.pending_scalar.value = yaml_lines(self.pending_lines, text=self.pending_scalar.value)
            yield self.pending_scalar
            self.pending_scalar = None
            self.pending_lines = None
        if self.pending_tokens is not None:
            for token in self.pending_tokens:
                yield token
            self.pending_tokens = None

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

    def consume_flow_map_start(self, linenum, start, _):
        self.push_flow_ender("}")
        return FlowMapToken(linenum, start)

    def consume_flow_map_end(self, linenum, start, _):
        self.pop_flow_ender("}")
        return FlowEndToken(linenum, start)

    def consume_flow_list_start(self, linenum, start, _):
        self.push_flow_ender("]")
        return FlowSeqToken(linenum, start)

    def consume_flow_list_end(self, linenum, start, _):
        self.pop_flow_ender("]")
        return FlowEndToken(linenum, start)

    @staticmethod
    def consume_comma(linenum, start, _):
        return CommaToken(linenum, start)

    @staticmethod
    def consume_map(linenum, start, _):
        return ExplicitMapToken(linenum, start)

    @staticmethod
    def _checked_string(linenum, start, end, line_text):
        if start >= end:
            line_text = None
            start = 0
        return linenum, start, end, line_text

    def _double_quoted(self, linenum, start, end, line_text):
        token = ScalarToken(linenum, start, "", style='"')
        self.pending_scalar = token
        try:
            if start < end and line_text[start] == '"':  # Empty string
                return self._checked_string(linenum, start + 1, end, line_text)
            lines = None
            m = None
            while m is None:
                m = RE_DOUBLE_QUOTE_END.search(line_text, start)
                if m is not None:
                    text = line_text[start:m.span(1)[1] - 1]
                    if lines is not None:
                        lines.append(text)
                        text = yaml_lines(lines)
                    token.value = codecs.decode(text, "unicode_escape")
                    start, end = m.span(2)
                    return self._checked_string(linenum, start, end, line_text)
                if lines is None:
                    lines = [line_text[start:]]
                    start = 0
                else:
                    lines.append(line_text)
                linenum, line_text = next(self.generator)
                line_text = line_text.strip()
        except StopIteration:
            raise ParseError("Unexpected end, runaway double-quoted string at line %s?" % token.linenum)

    def _single_quoted(self, linenum, start, end, line_text):
        token = ScalarToken(linenum, start, "", style="'")
        self.pending_scalar = token
        try:
            if start < end and line_text[start] == "'":  # Empty string
                return self._checked_string(linenum, start + 1, end, line_text)
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
                        text = yaml_lines(lines)
                    token.value = text.replace("''", "'")
                    m = RE_CONTENT.match(line_text, quote_pos + 1)
                    start, end = m.span(1)
                    return self._checked_string(linenum, start, end, line_text)
                if lines is None:
                    lines = [line_text[start:]]
                    start = 0
                else:
                    lines.append(line_text)
                linenum, line_text = next(self.generator)
                line_text = line_text.strip()
        except StopIteration:
            raise ParseError("Unexpected end, runaway single-quoted string at line %s?" % token.linenum)

    @staticmethod
    def _get_literal_styled_token(linenum, start, style):
        original = style
        if len(style) > 3:
            raise ParseError("Invalid literal style '%s', should be less than 3 chars" % style, linenum, start)
        keep = None
        if "-" in style:
            style = style.replace("-", "", 1)
            keep = False
        if "+" in style:
            if keep is not None:
                raise ParseError("Ambiguous literal style '%s'" % original, linenum, start)
            keep = True
            style = style.replace("+", "", 1)
        indent = None
        if len(style) == 2:
            indent = style[1]
            style = style[0]
            if not indent.isdigit():
                raise ParseError("Invalid literal style '%s'" % original, linenum, start)
            indent = int(indent)
            if indent < 1:
                raise ParseError("Indent must be between 1 and 9", linenum, start)
        return style == ">", keep, indent, ScalarToken(linenum, indent, None, style=original)

    def _consume_literal(self, linenum, start, style):
        folded, keep, indent, token = self._get_literal_styled_token(linenum, start, style)
        self.pending_scalar = token
        lines = []
        while True:
            try:
                linenum, line_text = next(self.generator)
                m = RE_CONTENT.match(line_text)
                start, end = m.span(1)
                if start == end:
                    lines.append(line_text)
                    continue
            except StopIteration:
                line_text = None
                start = end = 0
            if indent is None:
                token.indent = indent = start if start != 0 else 1
            if start < indent:
                if not lines:
                    raise ParseError("Bad literal indentation")
                text = yaml_lines(lines, indent=indent, folded=folded, keep=keep)
                if keep is None:
                    token.value = "%s\n" % text.rstrip()
                elif keep is False:
                    token.value = text.rstrip()
                else:
                    token.value = "%s\n" % text
                if start >= end:
                    line_text = None
                return linenum, 0, end, line_text
            lines.append(line_text)

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
            else:
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
                    actionable = rstart == end or line_text[mstart - 1] == '"' or line_text[mstart + 1] in " \t,"
                else:
                    actionable = start == mstart or matched in "{}[],"
                if actionable:
                    if start < mstart:
                        yield None, start, line_text[start:mstart].rstrip()
                    yield matched, mstart, line_text[mstart:mend]
                    start = rstart
        if start < end:
            yield None, start, line_text[start:end]

    def header_token(self, linenum, start, line_text):
        if start == 0:
            m = RE_HEADERS.match(line_text)
            if m is not None:
                self.promote_pending_scalar()
                start, end = m.span(1)
                matched = line_text[start:end]
                if matched[0] == "-":
                    self.add_pending_token(DocumentStartToken(linenum, 0))
                    if matched[-1] == " ":
                        return False, linenum, end, line_text
                    return True, linenum, 0, None
                elif matched[0] == ".":
                    self.add_pending_token(DocumentEndToken(linenum, 0))
                    if matched[-1] == " ":
                        return False, linenum, end, line_text
                    return True, linenum, 0, None
                elif matched[-1] == "%":
                    if end != 1:
                        raise ParseError("Directive must not be indented", linenum, end - 1)
                    self.add_pending_token(DirectiveToken(linenum, 0, line_text))
                    return True, linenum, 0, None
                return True, linenum, 0, None
        m = RE_BLOCK_SEQUENCE.match(line_text, start)
        if m is None:
            return False, linenum, start, line_text
        start = m.span(1)[0] + 1
        self.add_pending_dash(linenum, start)
        first_non_blank = m.span(2)[1] - 1
        if first_non_blank < 0:
            return True, linenum, 0, None
        if line_text[first_non_blank] == "-":
            return True, linenum, start, line_text
        return False, linenum, first_non_blank, line_text

    def headers(self, linenum, start, line_text):
        tbc = True
        while tbc:
            if line_text is None:
                linenum, line_text = next(self.generator)
                start = 0
            tbc, linenum, start, line_text = self.header_token(linenum, start, line_text)
        m = RE_CONTENT.match(line_text, start)
        start, end = m.span(1)
        if start == end and self.pending_scalar is not None and self.pending_scalar.style is None:
            self.add_pending_line("")
        return linenum, start, end, line_text

    def tokens(self):
        start = end = offset = 0
        linenum = 1
        upcoming = None
        try:
            yield StreamStartToken(1, 0)
            while True:
                self.promote_simple_key()
                if start == 0 or upcoming is None:
                    linenum, start, end, line_text = self.headers(linenum, start, upcoming)
                    if self.pending_tokens is not None:
                        for token in self.consumed_pending():
                            yield token
                else:
                    line_text = upcoming
                    for token in self.consumed_pending():
                        yield token
                upcoming = None
                for matched, offset, text in self.next_match(start, end, line_text):
                    if self.simple_key is None:
                        if matched is None:
                            if text[0] in RESERVED:
                                raise ParseError("Character '%s' is reserved" % text[0], linenum, offset)
                            if self.pending_scalar is None:
                                if text[0] == '"':
                                    linenum, start, end, upcoming = self._double_quoted(linenum, offset + 1, end, line_text)
                                    break
                                if text[0] == "'":
                                    linenum, start, end, upcoming = self._single_quoted(linenum, offset + 1, end, line_text)
                                    break
                                if text[0] in '|>':
                                    linenum, start, end, upcoming = self._consume_literal(linenum, offset, text)
                                    break
                            self.simple_key = ScalarToken(linenum, offset, text)
                            continue
                        if matched == ":":
                            yield ColonToken(linenum, offset)
                            continue
                        for token in self.consumed_pending():
                            yield token
                        tokenizer = self.tokenizer_map.get(matched)
                        yield tokenizer(linenum, offset, text)
                        self.pending_dash = None
                    elif matched == ":":
                        self.pending_dash = None
                        for token in self.consumed_pending():
                            yield token
                        yield self.simple_key
                        self.simple_key = None
                        yield ColonToken(linenum, offset)
                    else:
                        self.promote_simple_key()
                        for token in self.consumed_pending():
                            yield token
                        tokenizer = self.tokenizer_map.get(matched)
                        yield tokenizer(linenum, offset, text)
        except StopIteration:
            self.promote_simple_key()
            self.promote_pending_scalar()
            last_token = None
            for token in self.consumed_pending():
                last_token = token
                yield token
            if isinstance(last_token, DashToken):
                yield ScalarToken(linenum, last_token.indent + 1, None)
            yield StreamEndToken(linenum, 0)
        except ParseError as error:
            error.auto_complete(linenum, offset)
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


def yaml_lines(lines, text=None, indent=None, folded=None, keep=None):
    empty = 0
    was_over_indented = False
    for line in lines:
        if indent is not None:
            line = line[indent:]
            if line:
                if line[0] in " \t":
                    if not was_over_indented:
                        empty = empty + 1
                        was_over_indented = True
                elif was_over_indented:
                    was_over_indented = False
        if not text:
            text = line if text is None or not folded else "\n%s" % line
        elif not line:
            empty = empty + 1
        elif empty > 0:
            text = "%s%s%s" % (text, "\n" * empty, line)
            empty = 1 if was_over_indented else 0
        elif folded is None:
            text = "%s %s" % (text, line)
        else:
            text = "%s%s%s" % (text, " " if folded else "\n", line)
    if keep and empty:
        if was_over_indented:
            empty = empty - 1
        text = "%s%s" % (text, "\n" * empty)
    return text


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
