import codecs
import datetime
import dateutil
import os
import re
import sys


PY2 = sys.version_info < (3, 0)
DEBUG = os.environ.get("TRACE_YAML")
UTC = dateutil.tz.tzoffset("UTC", 0)

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
    from typing import List, Optional, Union

    def cleaned_number(text):
        return text

    def base64_decode(value):
        return base64.decodebytes(_checked_scalar(value).encode("ascii"))


def trace(message, *args):
    """Output 'message' if tracing is on"""
    if DEBUG:
        if args:
            message = message.format(*args)
        sys.stderr.write(":: %s\n" % message)
        sys.stderr.flush()


def shortened(text, size=32):  # type: (str, int) -> str
    text = str(text)
    if not text or len(text) < size:
        return text
    return "%s..." % text[:size]


def double_quoted(text):  # type: (str) -> str
    text = decode(codecs.encode(str(text), "unicode_escape"))
    return '"%s"' % text.replace('"', '\\"')


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
        return "".join((self.message, coords))

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


def to_float(text):  # type: (str) -> float
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


def to_number(text):  # type: (str) -> Union[int, float]
    text = cleaned_number(text)
    try:
        return int(text)
    except ValueError:
        return to_float(text)


def get_tzinfo(text):  # type: (str) -> Optional[datetime.tzinfo]
    if text is None:
        return None
    if text == "Z":
        return UTC
    hours, _, minutes = text.partition(":")
    minutes = int(minutes) if minutes else 0
    offset = int(hours) * 3600 + minutes * 60
    return UTC if offset == 0 else dateutil.tz.tzoffset(text, offset)


def default_marshal(text):  # type: (Optional[str]) -> Union[str, int, float, list, dict, datetime.date, datetime.datetime]
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
