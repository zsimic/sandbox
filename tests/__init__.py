import inspect

import runez


class TestSettings:
    stacktrace = False  # Can be set to True via `./run --stacktrace ...`, useful for troubleshooting in debugger
    line_numbers = False  # Show line numbers in show_lines(), set via `./run --lines ...`
    profiler = None  # Optional current profiler (if --profile used)

    @classmethod
    def colored(cls, message, color=None):
        if color is None:
            return message

        return color(message)

    @classmethod
    def represented(cls, value, size=runez.UNSET, stringify=runez.stringified, dt=str):
        if isinstance(value, NotImplementedError):
            if size is None:
                return {"_error": "not implemented"}

            return runez.orange("not implemented")

        if isinstance(value, Exception):
            if size is None:
                return {"_error": runez.short(value, size=256)}

            return runez.red(runez.short(value, size=size))

        return runez.represented_json(value, stringify=stringify, dt=dt, keep_none=True, none_key="-null-")

    @classmethod
    def colored_if_meaningful(cls, count, text, color):
        message = "%s %s" % (count, text)
        if count > 0:
            return color(message)

        return message

    @classmethod
    def unwrapped(cls, value):
        if value is not None and inspect.isgenerator(value):
            value = list(value)

        return value

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
    def protected_call(cls, func, *args, **kwargs):
        if cls.stacktrace:
            value = func(*args, **kwargs)
            return cls.unwrapped(value)

        try:
            value = func(*args, **kwargs)
            return cls.unwrapped(value)

        except Exception as e:
            return e

    @classmethod
    def stop_profiler(cls):
        cls.profiler.disable()
        filepath = runez.SYS_INFO.project_path(".tox", "lastrun.profile")
        try:
            cls.profiler.dump_stats(filepath)
            if runez.which("qcachegrind") is None:
                print("run 'brew install qcachegrind'")
                return

            runez.run("pyprof2calltree", "-k", "-i", filepath, stdout=None, stderr=None)

        except Exception as e:
            print("Can't save %s: %s" % (filepath, e))
