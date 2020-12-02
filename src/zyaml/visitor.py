import collections

from .marshal import ParseError
from .tokens import Token


class DocumentLayer(object):

    def __init__(self, value=None):
        self.value = value

    def __repr__(self):
        return self.__class__.__name__.replace("Layer", "")

    def resolved_value(self):
        return self.value

    def consume_scalar(self, value):
        self.value = value

    def consume_value(self, value):
        self.value = value


class MapLayer(DocumentLayer):

    def __init__(self):
        super(MapLayer, self).__init__(value={})
        self.needs_wrap = False
        self.pending_key = None
        self.consume_scalar = self.consume_key

    def resolved_value(self):
        if self.needs_wrap:
            self.consume_value(None)

        return self.value

    def consume_key(self, value):
        self.pending_key = value
        self.needs_wrap = True

    def consume_value(self, value):
        self.value[self.pending_key] = value
        self.pending_key = None
        self.needs_wrap = False

    def KeyToken(self, token):
        self.needs_wrap = True
        self.consume_scalar = self.consume_key

    def CommaToken(self, token):
        if self.needs_wrap:
            self.consume_value(None)

    def ValueToken(self, token):
        self.consume_scalar = self.consume_value
        self.needs_wrap = True


class SeqLayer(DocumentLayer):

    def __init__(self):
        super(SeqLayer, self).__init__(value=[])
        self.needs_wrap = False

    def resolved_value(self):
        if self.needs_wrap:
            self.consume_value(None)

        return self.value

    def consume_scalar(self, value):
        self.value.append(value)
        self.needs_wrap = False

    def consume_value(self, value):
        self.value.append(value)
        self.needs_wrap = False

    def CommaToken(self, token):
        if self.needs_wrap:
            self.consume_value(None)

    def ValueToken(self, token):
        pass

    def DashToken(self, token):
        self.needs_wrap = True


class TokenVisitor(object):

    top = None  # type: DocumentLayer

    def __init__(self):
        self.docs = []
        self.root = collections.deque()

    def consume(self, token):
        """
        Args:
            token (Token): Token to consume
        """
        assert isinstance(token, Token)
        tname = token.__class__.__name__
        func = getattr(self.top, tname, None)
        if func is None:
            func = getattr(self, tname, None)

        if func is None:
            message = "Unexpected token %s" % tname
            if self.top is not None:
                message += " in %s" % self.top

            raise ParseError(message, token=token)

        func(token)

    def deserialized(self, tokens):
        """
        Args:
            tokens: Token generator

        Returns:
            (list): Deserialized documents
        """
        for token in tokens:
            self.consume(token)

        if len(self.docs) == 1:
            self.docs = self.docs[0]

        return self.docs

    def push(self, element):
        self.top = element
        self.root.append(element)

    def pop(self):
        popped = self.root.pop()
        self.top = self.root[-1]
        value = popped.resolved_value()
        self.top.consume_value(value)

    def StreamStartToken(self, token):
        pass

    def StreamEndToken(self, token):
        self.root = None

    def DocumentStartToken(self, token):
        self.push(DocumentLayer())

    def DocumentEndToken(self, token):
        popped = self.root.pop()
        value = popped.resolved_value()
        self.docs.append(value)

    def DirectiveToken(self, token):
        pass

    def FlowMapToken(self, token):
        self.push(MapLayer())

    def FlowSeqToken(self, token):
        self.push(SeqLayer())

    def FlowEndToken(self, token):
        self.pop()

    def BlockMapToken(self, token):
        self.push(MapLayer())

    def BlockSeqToken(self, token):
        self.push(SeqLayer())

    def BlockEndToken(self, token):
        self.pop()

    def TagToken(self, token):
        pass

    def AnchorToken(self, token):
        pass

    def AliasToken(self, token):
        pass

    def ScalarToken(self, token):
        from .tokens import ScalarToken
        assert isinstance(token, ScalarToken)
        value = token.resolved_value()
        self.top.consume_scalar(value)


class BaseVisitor(TokenVisitor):
    pass
