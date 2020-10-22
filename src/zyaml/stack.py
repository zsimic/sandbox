from zyaml.tokens import *


class StackedDocument(object):
    def __init__(self):
        self.indent = -1  # type: Optional[int]
        self.root = None  # type: Optional[ScannerStack]
        self.prev = None  # type: Optional[StackedDocument]
        self.value = None  # type: Optional[Union[str, list, dict]]
        self.anchor_token = None  # type: Optional[AnchorToken]
        self.tag_token = None  # type: Optional[TagToken]
        self.is_key = False  # type: bool
        self.closed = False  # type: bool

    def __repr__(self):
        return "%s %s" % (self.dbg_representation(), self.value)

    def type_name(self):
        return self.__class__.__name__.replace("Stacked", "").lower()

    def dbg_representation(self):
        indent = self.indent if self.indent != -1 else None
        return dbg(self.__class__.__name__[7], indent, self.represented_decoration())

    def represented_decoration(self):
        return dbg(("&", self.anchor_token), ("!", self.tag_token), (":", self.is_key))

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


def new_stacked_scalar(token, text=""):
    return StackedScalar(ScalarToken(token.scanner, token.linenum, token.indent, text))


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
        scalar = new_stacked_scalar(token)
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
        return dbg(super(StackedMap, self).represented_decoration(), ("*", self.last_key))

    def check_key_indentation(self, indent):  # type: (Optional[int]) -> None
        if indent is not None and self.indent is not None and indent != self.indent:
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
            self.root.push(new_stacked_scalar(token))
            self.root.pop()
        self.closed = False

    def mark_as_key(self, token):
        scalar = new_stacked_scalar(token)
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

    def DirectiveToken(self, token):
        if self.directive is not None:
            raise ParseError("Duplicate directive")
        self.directive = token

    def FlowMapToken(self, token):
        self.push(StackedMap(None))

    def FlowSeqToken(self, token):
        self.push(StackedList(None))

    def FlowEndToken(self, token):
        self.pop_until(None)
        self.pop()

    def CommaToken(self, token):
        self.pop_until(None)
        self.head.mark_open(token)

    def ExplicitMapToken(self, token):
        indent = token.indent + 2
        self.pop_until(indent)
        if not isinstance(self.head, StackedMap) or (self.head.indent is not None and self.head.indent != indent):
            self.push(StackedMap(indent))

    def DashToken(self, token):
        self.pop_until(token.indent)
        self.head.consume_dash(token)

    def ColonToken(self, token):
        self.head.mark_as_key(token)
        self.pop()

    def TagToken(self, token):
        self._set_decoration(token, "tag_token", "secondary_tag_token")

    def AnchorToken(self, token):
        self._set_decoration(token, "anchor_token", "secondary_anchor_token")

    def AliasToken(self, token):
        if token.anchor not in self.anchors:
            raise ParseError("Undefined anchor &%s" % token.anchor)
        token.value = self.anchors.get(token.anchor)
        self.head.consume_scalar(token)

    def ScalarToken(self, token):
        self.head.consume_scalar(token)

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

    def DocumentEndToken(self, token):
        if self.tag_token and self.tag_token.linenum == token.linenum - 1:  # last line finished with a tag (but no value)
            self.push(new_stacked_scalar(self.tag_token))
        if self.head.prev is None and self.head.value is None:  # doc was empty, no tokens
            self.docs.append(None)
        else:
            while self.head.prev is not None:
                self.pop()
            if self.head.value is not None:
                self.docs.append(self.head.value)
                # trace("---\n{}\n---", self.head.value)
                self.head.value = None
        self.anchors = {}
        self.directive = None
