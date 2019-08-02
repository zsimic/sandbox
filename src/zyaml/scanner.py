BLANKS = " \t\n\r"


class Token(object):

    def __init__(self, line, column, text=None):
        self.line = line
        self.column = column
        self.value = self.parsed_value(text)

    def __repr__(self):
        if self.value is None:
            if self.line:
                return "%s[%s,%s]" % (self.__class__.__name__, self.line, self.column)
            return self.__class__.__name__
        return "%s[%s,%s] %s" % (self.__class__.__name__, self.line, self.column, self.value)

    @staticmethod
    def parsed_value(text):
        return text


class BlockEntryToken(Token):
    pass


class CommentToken(Token):
    pass


class ScalarToken(Token):
    pass


class KeyToken(ScalarToken):
    pass


class Processor:
    def __init__(self, buffer, line, column, pos, indent, current):
        self.buffer = buffer
        self.line = line
        self.column = column
        self.pos = pos
        self.indent = indent
        self.current = current

    def __call__(self, line, column, pos, indent, prev, current):
        pass


class CommentProcessor(Processor):
    def __call__(self, line, column, pos, indent, prev, current):
        if current == "\n":
            return CommentToken(self.line, self.column, self.buffer[self.pos:pos].strip())


class FlowProcessor(Processor):
    def __init__(self, buffer, line, column, pos, indent, current):
        super(FlowProcessor, self).__init__(buffer, line, column, pos, indent, current)
        self.subprocessor = None
        self.ender = "}" if self.current == "{" else "]"

    def consume(self, line, column, pos, indent, prev, current):
        if self.subprocessor is not None:
            return self.subprocessor(line, column, pos, indent, prev, current)

        if current == self.ender:
            return

        if current == '"' or current == '"':
            self.subprocessor = StringProcessor(self.buffer, line, column, pos, indent, current)


class StringProcessor(Processor):
    pass


class ParseError(Exception):
    def __init__(self, line, column, message):
        self.line = line
        self.column = column
        self.message = message


class Scanner2:

    __slots__ = ["source", "buffer", "column", "line", "pos", "size", "indentation", "current", "prev", "prev2", "simplekey_ok"]

    def __init__(self, source):
        if hasattr(source, "read"):
            self.source = source.name
            self.buffer = source.read()
        else:
            self.source = source
            self.buffer = source
        self.column = 1
        self.line = 1
        self.pos = 0
        self.size = len(self.buffer)
        self.indentation = 0
        self.current = self.buffer[0] if self.size else None
        self.prev = None
        self.prev2 = None
        self.simplekey_ok = True

    def __repr__(self):
        if self.pos < self.size:
            head = self.buffer[:self.pos - 1]
            tail = self.buffer[self.pos + 1:]
            return "%s %s %s: %s --[%s]-- %s" % (self.indentation, self.line, self.column, head, self.current, tail)

        return str(self.source)

    def tokens(self):
        buffer = self.buffer
        column = line = 1
        pos = indent = 0
        prev2 = prev = processor = key = None
        processors = {
            "#": CommentProcessor,
            "{": FlowProcessor,
            "[": FlowProcessor,
            '"': StringProcessor,
            "'": StringProcessor,
        }
        for current in buffer:
            if processor is not None:
                assert isinstance(processor, Processor)
                result = processor(line, column, pos, indent, prev, current)
                if result is not None:
                    yield result
                    processor = None

            elif current in " \n":
                if prev == ":":
                    if key is None:
                        raise ParseError(line, column, "':' not allowed without key")
                    yield key

                elif key is None:
                    if prev == "-" and prev2 in " \n":
                        yield BlockEntryToken(line, column)

                else:
                    processor = processors.get(prev)
                    if processor is not None:
                        processor = processor(buffer, line, column, pos, indent, current)

            else:
                pass

            if current == "\n":
                line += 1
                column = 1
                indent = 0

            else:
                column += 1

            pos += 1
            prev2 = prev
            prev = current

        while self.current is not None:
            if self.current == "#":
                pass

            self.advance_to_next_token()
            if self.current == "-":
                pass

    def advance(self, past=None):
        while self.pos < self.size:
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
                return self.current

    def advance_to_next_token(self):
        while self.pos < self.size:
            self.advance(past=BLANKS)
            if self.current == "#":
                self.advance(past="\n")
                if self.current not in BLANKS:
                    return
