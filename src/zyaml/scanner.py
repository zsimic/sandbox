class Scanner2:

    __slots__ = ["source", "buffer", "column", "line", "pos", "size", "indentation", "current", "prev", "prev2", "simplekey_ok"]

    def __init__(self, source):
        if hasattr(source, "read"):
            self.source = source.name
            self.buffer = source.read()
        else:
            self.source = source
            self.buffer = source
        self.column = 0
        self.line = 1
        self.pos = -1
        self.size = len(self.buffer)
        self.indentation = 0
        self.current = None
        self.prev = None
        self.prev2 = None
        self.simplekey_ok = True

    def __repr__(self):
        if 0 < self.pos < self.size:
            head = self.buffer[:self.pos - 1]
            tail = self.buffer[self.pos + 1:]
            return "%s %s %s: %s --[%s]-- %s" % (self.indentation, self.line, self.column, head, self.current, tail)

        return str(self.source)

    def advance(self, past=None):
        while True:
            self.prev2 = self.prev
            self.prev = self.current
            self.pos += 1
            self.current = self.buffer[self.pos]
            if self.current == "\n":
                self.line += 1
                self.column = 1
                self.indentation = 0
                self.simplekey_ok = True

            else:
                self.column += 1
                if self.current == " ":
                    self.indentation += 1
                elif self.current == "\t":
                    self.simplekey_ok = False

            if past is None or self.prev is None or self.prev in past:
                return

    def advance_to_next_token(self):
        while self.pos < self.size:
            self.advance(past=BLANKS)
            if self.current == "#":
                self.advance(past="\n")
                if self.current not in BLANKS:
                    return

    def pop_indent_to_here(self):
        pass

    def tokens(self):
        while self.pos < self.size:
            self.advance_to_next_token()
            self.pop_indent_to_here()
            if self.current == "-":
                pass


BLANKS = " \t\n\r"
