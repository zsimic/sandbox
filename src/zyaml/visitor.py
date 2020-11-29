from .marshal import ParseError
from .tokens import Token


def unpexpected_token(layer, token):
    pass
    # raise ParseError("Unexpected token '%s' in %s" % (token.__class__.__name__, layer.short_name), token=token)


class DocumentLayer(object):

    token = None  # type: Token
    root = None   # type: DocumentLayer
    prev = None   # type: DocumentLayer
    top = None   # type: DocumentLayer

    def __repr__(self):
        if self.prev is None or self.top is self:
            return "[root]"

        short = "" if self.token is None else self.token.short_name
        if self.prev is not None:
            short = "%s / %s" % (self.prev, short)

        return short

    @property
    def short_name(self):
        return self.__class__.__name__.replace("Layer", "")

    def on_push(self, new_layer):
        pass

    def push(self, layer, token):
        if self.prev is None and self.top is not self:
            return self.top.push(layer, token)

        new_layer = layer()
        assert isinstance(new_layer, DocumentLayer)
        new_layer.token = token
        new_layer.root = self.root
        new_layer.prev = self
        self.root.top = new_layer
        self.on_push(new_layer)
        return new_layer

    def on_pop(self, value):
        pass

    def pop(self, token):
        if self.prev is None and self.top is not self:
            return self.top.pop(token)

        value = self.wrapped_value()
        prev = self.prev
        prev.root.top = prev
        return prev.on_pop(value)

    def wrapped_value(self):
        pass

    def consume_value(self, value):
        pass

    KeyToken = unpexpected_token
    CommaToken = unpexpected_token
    DashToken = unpexpected_token
    ValueToken = unpexpected_token


class ContainerLayer(DocumentLayer):
    pass


class MapLayer(ContainerLayer):

    def KeyToken(self, token):
        pass

    def CommaToken(self, token):
        pass

    def ValueToken(self, token):
        pass


class SeqLayer(ContainerLayer):

    def CommaToken(self, token):
        pass

    def DashToken(self, token):
        pass


class ScalarLayer(DocumentLayer):
    pass


class TokenVisitor(object):

    complete = False  # type: bool # If True, require implementation for all tokens
    root = None  # type: DocumentLayer

    def consume(self, token):
        """
        Args:
            token (Token): Token to consume
        """
        assert isinstance(token, Token)
        tname = token.__class__.__name__
        func = getattr(self, tname, None)
        if func is None:
            func = getattr(self.root.top, tname, None)

        if func is None:
            if self.complete:
                raise ParseError("Unexpected token '%s' in %s" % (tname, self.root.top.short_name), token=token)

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
        root.root = root
        root.top = root
        self.root = root
        for token in tokens:
            self.consume(token)

        return root.wrapped_value()

    def FlowMapToken(self, token):
        self.root.push(MapLayer, token)

    def FlowSeqToken(self, token):
        self.root.push(SeqLayer, token)

    def FlowEndToken(self, token):
        self.root.pop(token)

    def BlockMapToken(self, token):
        self.root.push(MapLayer, token)

    def BlockSeqToken(self, token):
        self.root.push(SeqLayer, token)

    def BlockEndToken(self, token):
        self.root.pop(token)

    def TagToken(self, token):
        pass

    def AnchorToken(self, token):
        pass

    def AliasToken(self, token):
        pass

    def ScalarToken(self, token):
        self.root.push(ScalarLayer, token)


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
