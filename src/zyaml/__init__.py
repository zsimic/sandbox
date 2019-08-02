from zyaml.scan import BlockEntryToken, ScalarToken, scan_tokens


class KeyStack:
    def __init__(self):
        self.items = []
        self.current = None

    def add(self, key):
        """
        :param Key key:
        """
        self.current = key
        self.items.append(key)

    def pop(self):
        if self.items:
            self.items.pop()
        if self.items:
            self.current = self.items[-1]
        else:
            self.current = None


def load(stream):
    if hasattr(stream, "read"):
        stream = stream.read()
    return load_string(stream)


def load_string(contents):
    """
    :param str contents: Yaml to deserialize
    """
    root = {}
    current = root
    keys = KeyStack()
    for token in scan_tokens(contents):
        if isinstance(token, ScalarToken):
            if token.is_key:
                while keys.current and token.column <= keys.current.column:
                    keys.pop()
                if keys.current:
                    if token.column > keys.current.column:
                        target = keys.current.target
                        current = {}
                        if isinstance(target, dict):
                            target[keys.current.value] = current
                        else:
                            target.append(token.value)
                else:
                    current = root
                keys.add(token)
                keys.current.target = current
                continue

            if keys.current:
                target = keys.current.target
                if isinstance(target, dict):
                    target[keys.current.value] = token.value
                else:
                    target.append(token.value)
            continue

        if isinstance(token, BlockEntryToken):
            if not keys.current:
                continue
            keys.current.target = []

    return root


def load_path(path):
    with open(path) as fh:
        return load_string(fh.read())
