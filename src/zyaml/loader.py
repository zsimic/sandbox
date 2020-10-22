class SimpleLoader(object):
    def __init__(self, scanner):
        self.scanner = scanner
        self.docs = []

    def DocumentEndToken(self, token):
        pass

    def BlockMapToken(self, token):
        pass

    def KeyToken(self, token):
        pass
