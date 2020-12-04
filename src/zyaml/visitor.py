import collections

from .tokens import Token, VisitedToken


class DocumentStack(VisitedToken):
    def __init__(self):
        self.doc_count = 0
        self.value = []

    def __repr__(self):
        return "%s docs" % self.doc_count

    @property
    def short_name(self):
        return "Docs"

    def consume_value(self, visitor, value):
        self.doc_count += 1
        self.value.append(value)


class TokenVisitor(object):

    top = None  # type: Token

    def __init__(self):
        self.documents = DocumentStack()
        self.root = collections.deque()
        self.root.append(self.documents)

    def __repr__(self):
        return " %s" % " / ".join(t.short_name for t in self.root)

    def deserialized(self, tokens):
        """
        Args:
            tokens: Token generator

        Returns:
            (list): Deserialized documents
        """
        for token in tokens:
            token.evaluate(self)

        if self.documents.doc_count == 1:
            return self.documents.value[0]

        if self.documents.doc_count == 0:
            return None

        return self.documents.value

    def consume_key(self, value):
        self.top.consume_key(self, value)

    def consume_value(self, value):
        self.top.consume_value(self, value)

    def push(self, element):
        self.top = element
        self.root.append(element)

    def pop(self):
        popped = self.root.pop()
        self.top = self.root[-1]
        return popped

    def trigger_auto_pop(self, token):
        self.top.auto_pop(self, token)
