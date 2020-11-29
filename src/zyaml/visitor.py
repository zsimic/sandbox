from .marshal import ParseError
from .tokens import Token


class DocumentLayer(object):
    def __init__(self, token=None, parent=None):
        self.parent = parent
        self.token = token
        self.next = None

    def wrapped_value(self):
        pass

    def consume_value(self, value):
        pass


class MapLayer(DocumentLayer):
    pass


class SeqLayer(DocumentLayer):
    pass


class ScalarLayer(DocumentLayer):
    pass


class TokenVisitor(object):

    complete = False  # type: bool # If True, require implementation for all tokens
    root = None  # type: DocumentLayer
    current = None  # type: DocumentLayer

    def push(self, layer):
        c = self.current
        layer.parent = c
        c.next = layer
        self.current = layer

    def pop(self):
        popped = self.current
        c = popped.parent
        self.current = c
        value = popped.wrapped_value()
        c.consume_value(value)

    def consume(self, token):
        """
        Args:
            token (Token): Token to consume
        """
        assert isinstance(token, Token)
        tname = token.__class__.__name__
        func = getattr(self, tname, None)
        if func is None:
            func = getattr(self.current, tname, None)

        if func is None:
            if self.complete:
                raise ParseError("Unexpected token '%s'" % tname, token=token)

        else:
            func(token)

    def deserialized(self, tokens):
        """
        Args:
            tokens: Token generator

        Returns:
            (list): Deserialized documents
        """
        root = DocumentLayer()
        self.root = root
        self.current = root
        for token in tokens:
            self.consume(token)

        return root.wrapped_value()

    def FlowMapToken(self, token):
        self.push(MapLayer(token))

    def FlowSeqToken(self, token):
        self.push(SeqLayer(token))

    def FlowEndToken(self, token):
        self.pop()

    def CommaToken(self, token):
        pass

    def BlockMapToken(self, token):
        self.push(MapLayer(token))

    def BlockSeqToken(self, token):
        self.push(SeqLayer(token))

    def BlockEndToken(self, token):
        self.pop()

    def DashToken(self, token):
        pass

    def KeyToken(self, token):
        pass

    def ValueToken(self, token):
        pass

    def TagToken(self, token):
        pass

    def AnchorToken(self, token):
        pass

    def AliasToken(self, token):
        pass

    def ScalarToken(self, token):
        self.push(ScalarLayer(token))


class BaseVisitor(TokenVisitor):

    def StreamStartToken(self, token):
        self.docs = []

    def StreamEndToken(self, token):
        pass

    def DocumentStartToken(self, token):
        pass

    def DocumentEndToken(self, token):
        pass

    def DirectiveToken(self, token):
        pass
