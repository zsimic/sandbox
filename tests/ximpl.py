import inspect
import json
import re

import click
import poyo
import ruamel.yaml
import runez
import strictyaml
import yaml as pyyaml

from zyaml import load_path, load_string, tokens_from_path, tokens_from_stream, tokens_from_string
from zyaml.marshal import decode, default_marshal, represented_scalar


def not_implemented():
    raise NotImplementedError(runez.brown("not implemented"))


def implementation_option(option=True, default="zyaml,ruamel", count=None, **kwargs):
    """
    Args:
        option (bool): If True, make this an option
        default (str | None): Default implementation(s) to use
        count (int | None): Exact number of implementations needed (when applicable)
        **kwargs: Passed-through to click
    """
    kwargs["default"] = default

    def _callback(_ctx, _param, value):
        if not value:
            return None

        implementations = ImplementationCollection(value, default=default)
        if implementations.unknown:
            raise click.BadParameter("Unknown implementation(s): %s" % ", ".join(implementations.unknown))

        if count and len(implementations) != count:
            if count == 1:
                raise click.BadParameter("Need exactly 1 implementation")

            raise click.BadParameter("Need exactly %s implementations" % count)

        if count == 1:
            return implementations.selected[0]

        return implementations

    if option:
        if count and count > 1:
            hlp = "%s implementations to use" % count

        else:
            hlp = "Implementation(s) to use"

        kwargs.setdefault("help", hlp)
        kwargs.setdefault("show_default", True)
        kwargs.setdefault("metavar", "IMPL" if count == 1 else "CSV")
        return click.option("--implementation", "-i", callback=_callback, **kwargs)

    return click.argument("implementations", callback=_callback, **kwargs)


def get_descendants(ancestor, adjust=None, _result=None):
    if _result is None:
        _result = {}

    for m in ancestor.__subclasses__():
        name = m.__name__
        if adjust is not None:
            name = adjust(name)

        _result[name] = m
        get_descendants(m, adjust=adjust, _result=_result)

    return _result


def json_sanitized(value, stringify=decode, dt=str):
    if isinstance(value, strictyaml.representation.YAML):
        return dt(value)

    return runez.serialize.json_sanitized(value, stringify=stringify, dt=dt)


class ImplementationCollection(object):
    def __init__(self, names, default="zyaml,ruamel"):
        self.available = get_descendants(YmlImplementation, adjust=lambda x: x.replace("Implementation", "").lower())
        self.available = dict((n, i()) for n, i in self.available.items())
        self.unknown = []
        self.selected = []
        if names.startswith("+"):
            names = "%s,%s" % (names[1:], default)

        names = [s.strip() for s in names.split(",")]
        names = [s for s in names if s]
        seen = {}
        for name in names:
            found = 0
            for i in self.available.values():
                if name == "all" or name in i.name:
                    if i.name not in seen:
                        seen[i.name] = True
                        self.selected.append(i)

                    found += 1

            if found == 0:
                self.unknown.append(name)

        self.combinations = None

    def track_result_combination(self, impl, value):
        name = impl.name
        if self.combinations is None:
            self.combinations = {}
            for i1 in self.selected:
                for i2 in self.selected:
                    if i1.name < i2.name:
                        self.combinations[(i1.name, i2.name)] = set()

        for names, values in self.combinations.items():
            if name in names:
                values.add(value)

    def __repr__(self):
        return ",".join(str(i) for i in self.selected)

    def __len__(self):
        return len(self.selected)

    def __iter__(self):
        for i in self.selected:
            yield i


class ParseResult(object):
    def __init__(self, impl, sample, data=None):
        self.impl = impl  # type: YmlImplementation
        self.sample = sample
        self.data = data
        self.exception = None
        self.error = None

    def __repr__(self):
        if self.error:
            return "Error: %s" % self.error

        return str(self.data)

    def set_exception(self, exc):
        self.exception = exc
        self.error = runez.short(exc)
        if not self.error:
            self.error = exc.__class__.__name__

    def json_payload(self):
        return {"_error": self.error} if self.error else self.data


class YmlImplementation(object):
    """Implementation of loading a yml file"""

    def __repr__(self):
        return self.name

    @property
    def name(self):
        return "_".join(s.lower() for s in re.findall("[A-Z][^A-Z]*", self.__class__.__name__.replace("Implementation", "")))

    def tokens(self, source, stacktrace=True):
        if hasattr(source, "path"):
            tokens, exc = self._protected_call(self._tokens_from_path, source.path, stacktrace)

        else:
            tokens, exc = self._protected_call(self._tokens_from_string, source, stacktrace)

        if tokens is None:
            tokens = []

        if exc:
            tokens.append(exc)

        return tokens

    def _tokenize(self, source):
        if hasattr(source, "path"):
            return self._tokens_from_path(source.path)

        return self._tokens_from_string(source)

    def _tokens_from_path(self, path):
        not_implemented()

    def _tokens_from_stream(self, stream):
        not_implemented()

    def _tokens_from_string(self, text):
        not_implemented()

    def _simplified(self, value):
        if isinstance(value, list) and len(value) == 1:
            return value[0]

        return value

    def _load_string(self, text):
        not_implemented()

    def _load_path(self, path):
        with open(path) as fh:
            return self._load_string(fh.read())

    def _unprotected_call(self, func, target):
        value = func(target)
        if value is not None and inspect.isgenerator(value):
            value = list(value)

        value = self._simplified(value)
        return value

    def _protected_call(self, func, target, stacktrace):
        if stacktrace:
            value = self._unprotected_call(func, target)
            return value, None

        try:
            value = self._unprotected_call(func, target)
            return value, None

        except Exception as e:
            return None, e

    def load_sample(self, sample, stacktrace=True):
        """
        Args:
            sample (Sample): Sample to load
            stacktrace (bool): If True, don't catch parsing exceptions

        Returns:
            (ParseResult): Parsed sample
        """
        data, exc = self._protected_call(self._load_path, sample.path, stacktrace)
        result = ParseResult(self, sample, data)
        if exc:
            result.set_exception(exc)

        return result

    def load_string(self, text, stacktrace=True):
        data, exc = self._protected_call(self._load_string, text, stacktrace)
        if exc:
            return exc

        return data

    def json_representation(self, result, stringify=decode, dt=str):
        try:
            payload = result.json_payload()
            payload = json_sanitized(payload, stringify=stringify, dt=dt)
            return "%s\n" % json.dumps(payload, sort_keys=True, indent=2)

        except Exception:
            print("Failed to json serialize %s" % result.sample)
            raise

    def represented_token(self, token):
        if isinstance(token, Exception):
            return runez.red(token)

        return str(token)


class ZyamlImplementation(YmlImplementation):
    def _load_string(self, text):
        return load_string(text)

    def _load_path(self, path):
        return load_path(path)

    def _tokens_from_path(self, path):
        return tokens_from_path(path)

    def _tokens_from_stream(self, stream):
        return tokens_from_stream(stream)

    def _tokens_from_string(self, text):
        return tokens_from_string(text)

    def _simplified(self, value):
        return value


def ruamel_passthrough_tags(loader, tag, node):
    name = node.__class__.__name__
    if "Seq" in name:
        result = []
        for v in node.value:
            result.append(ruamel_passthrough_tags(loader, tag, v))

        return result

    if "Map" in name:
        result = {}
        for k, v in node.value:
            k = ruamel_passthrough_tags(loader, tag, k)
            v = ruamel_passthrough_tags(loader, tag, v)
            result[k] = v

        return result

    return default_marshal(node.value)


class RuamelImplementation(YmlImplementation):
    def _simplified(self, value):
        if not value:
            return None

        if len(value) == 1:
            return value[0]

        return value

    def _load_string(self, text):
        y = ruamel.yaml.YAML(typ="safe")
        ruamel.yaml.add_multi_constructor('', ruamel_passthrough_tags, Loader=ruamel.yaml.SafeLoader)
        return y.load_all(text)

    def _tokens_from_path(self, path):
        with open(path) as fh:
            return list(ruamel.yaml.main.scan(fh))

    def _tokens_from_string(self, text):
        return ruamel.yaml.main.scan(text)


class PyyamlBaseImplementation(YmlImplementation):
    def _load_string(self, text):
        return pyyaml.load_all(text, Loader=pyyaml.BaseLoader)

    def represented_token(self, token):
        if isinstance(token, Exception):
            return runez.red(token)

        linenum = token.start_mark.line + 1
        column = token.start_mark.column + 1
        result = "%s[%s,%s]" % (token.__class__.__name__, linenum, column)
        value = getattr(token, "value", None)
        if value is not None:
            if token.id == "<scalar>":
                value = represented_scalar(token.style, value)

            elif token.id == "<anchor>":
                value = "&%s" % value

            elif token.id == "<alias>":
                value = "*%s" % value

            elif token.id == "<tag>":
                assert isinstance(value, tuple)
                value = " ".join(str(s) for s in runez.flattened(value))

            elif token.id == "<directive>":
                result += " %s" % token.name
                value = " ".join(str(s) for s in runez.flattened(value))

            else:
                assert False

            result = "%s %s" % (result, value)

        return result

    def _tokens_from_path(self, path):
        with open(path) as fh:
            return list(self._tokens_from_string(fh))

    def _tokens_from_string(self, text):
        yaml_loader = pyyaml.BaseLoader(text)
        curr = yaml_loader.get_token()
        while curr is not None:
            yield curr
            curr = yaml_loader.get_token()


class PyyamlSafeImplementation(YmlImplementation):
    def _load_string(self, text):
        return pyyaml.load_all(text, Loader=pyyaml.SafeLoader)


class PyyamlFullImplementation(YmlImplementation):
    def _load_string(self, text):
        return pyyaml.load_all(text, Loader=pyyaml.FullLoader)


class PoyoImplementation(YmlImplementation):
    def _load_string(self, text):
        return [poyo.parse_string(text)]


class StrictImplementation(YmlImplementation):
    def _load_string(self, text):
        return strictyaml.load(text)
