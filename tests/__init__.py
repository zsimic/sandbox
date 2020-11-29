import inspect

import runez


class TestSettings:
    stacktrace = False
    line_numbers = False

    @classmethod
    def show_lines(cls, content, header=None):
        if hasattr(content, "path"):
            header = header or str(content)
            content = runez.readlines(content.path)

        elif hasattr(content, "splitlines"):
            content = content.splitlines()

        result = []
        for n, line in enumerate(content, start=1):
            line = line.rstrip("\n")
            result.append("%s%s" % (runez.dim("%3s: " % n) if cls.line_numbers else "", line))

        if header:
            print("========  %s  ========" % header)

        print("\n".join(result))

    @classmethod
    def _unwrapped(cls, func, *args, **kwargs):
        value = func(*args, **kwargs)
        if value is not None and inspect.isgenerator(value):
            value = list(value)

        return value

    @classmethod
    def protected_call(cls, func, *args, **kwargs):
        if cls.stacktrace:
            value = cls._unwrapped(func, *args, **kwargs)
            return value

        try:
            value = cls._unwrapped(func, *args, **kwargs)
            return value

        except Exception as e:
            return e
