class TokenVisitor(object):

    def consume(self, token):
        func = getattr(self, token.__class__.__name__, None)
        if func is not None:
            func(token)

    def documents(self):
        """list: Parsed documents"""


class BaseVistor(TokenVisitor):

    docs = None

    def documents(self):
        return self.docs

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

    def FlowMapToken(self, token):
        pass

    def FlowSeqToken(self, token):
        pass

    def FlowEndToken(self, token):
        pass

    def CommaToken(self, token):
        pass

    def BlockMapToken(self, token):
        pass

    def BlockSeqToken(self, token):
        pass

    def BlockEndToken(self, token):
        pass

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
        pass
