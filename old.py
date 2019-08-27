from zyaml import AliasToken, ParseError, simplified_docs, Token, ScalarToken


def wrap_up(self):
    token = self.pop_last_scalar()
    value = None if token is None else token.resolved_value(self)
    self.head.wrap_up(value)
    while self.head.is_temp:
        self.pop()


class StreamEndToken(Token):
    def consume_token(self, root):
        tag_token = root.decoration.tag_token
        if tag_token and root.scalar_token is None:
            root.set_scalar_token(ScalarToken(tag_token.line_number, tag_token.indent, ""))
        root.wrap_up()
        root.pop_doc()


class DashToken(Token):
    def __init__(self, line_number, indent):
        super(DashToken, self).__init__(line_number, indent)

    def consume_token(self, root):
        root.wrap_up()
        indent = self.indent + 1
        if root.head is not None and root.head.indent == indent and not isinstance(root.head, StackedList):
            raise ParseError("Bad sequence entry indentation", self)
        root.ensure_node(indent, StackedList)


class ColonToken(Token):
    def consume_token(self, root):
        if root.scalar_token is None:
            if root.last_popped is not None:
                if getattr(root.last_popped.target, "__hash__", None) is None:
                    raise ParseError("%s is not hashable" % type(root.last_popped.target).__name__)
                text = str(root.last_popped.target)
            else:
                text = ""
            root.set_scalar_token(ScalarToken(self.line_number, self.indent, text))
        root.push_key(self)


class StackedElement(object):
    def __init__(self, indent):
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
            return self.target
        return self.tag_token.marshalled(self.target)

    def set_value(self, value):
        self.target = value


class StackedList(StackedElement):
    def _new_target(self):
        return []

    def set_value(self, value):
        self.target.append(value)


class StackedMap(StackedElement):
    def __init__(self, indent):
        super(StackedMap, self).__init__(indent)
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
            if self.anchor_token.line_number == token.line_number:
                raise ParseError("Too many anchor tokens", self.anchor_token)
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
                raise ParseError("Tags not allowed on %s" % target.__class__.__name__)
            target.tag_token = tag_token

    @staticmethod
    def resolved_value(root, target):
        value = target.resolved_value()
        anchor = getattr(target, "anchor_token", None)
        if anchor is not None:
            root.anchors[anchor.value] = value
        return value


class ScannerStack(object):
    def __init__(self):
        self.decoration = Decoration(self)
        self.scalar_token = None
        self.last_popped = None

    def __repr__(self):
        result = str(self.decoration)
        result += "*" if isinstance(self.scalar_token, AliasToken) else ""
        result += "$" if self.scalar_token else ""
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
            if self.head is None:
                self.push(StackedElement(self.decoration.indent))
            self.head.set_value(value)
            self.scalar_token = None
            if self.head.is_temp:
                self.pop()

    def needs_new_node(self, indent, node_type):
        if self.head is None or self.head.__class__ is not node_type:
            return True
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
            if node_type is StackedList and self.head is not None and self.head.indent is not None and indent is not None:
                if indent < self.head.indent:
                    raise ParseError("Line should be indented at least %s chars" % self.head.indent)
            self.push(node_type(indent))

    def push_key(self, key_token):
        self.decoration.track(key_token)
        key = self.decoration.resolved_value(self, self.scalar_token)
        self.scalar_token = None
        self.ensure_node(self.decoration.indent, StackedMap)
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
            self.last_popped = popped
            if self.head is None:
                self.docs.append(value)
            else:
                self.head.set_value(value)
