import click
import poyo
import ruamel.yaml
import runez
import strictyaml
import yaml as pyyaml

from zyaml import load_path, load_string, tokens_from_path, tokens_from_string
from zyaml.marshal import decode, default_marshal, represented_scalar

from . import TestSettings


class ImplementationCollection(object):
    def __init__(self, names, default="zyaml,ruamel"):
        av = [ZyamlImplementation, RuamelImplementation, PyyamlBaseImplementation, PoyoImplementation, StrictImplementation]
        self.available = dict((m.name, m()) for m in av)
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

    def track_result_combination(self, impl, data):
        if isinstance(data, Exception):
            value = runez.stringified(data)

        else:
            value = runez.represented_json(data, stringify=decode, keep_none=True)

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


class Implementation(object):
    """Implementation of loading a yml file"""

    name = None  # type: str

    def __repr__(self):
        return self.name

    @classmethod
    def option(cls, default="zyaml,ruamel", count=None, **kwargs):
        """
        Args:
            default (str | None): Default implementation(s) to use
            count (int | None): Optional: exact number of implementations that have to specified
            **kwargs: Passed-through to click
        """
        kwargs["default"] = default

        def _callback(_ctx, _param, value):
            if not value:
                return None

            impls = ImplementationCollection(value, default=default)
            if impls.unknown:
                raise click.BadParameter("Unknown implementation(s): %s" % ", ".join(impls.unknown))

            if count and len(impls) != count:
                if count == 1:
                    raise click.BadParameter("Need exactly 1 implementation")

                raise click.BadParameter("Need exactly %s" % runez.plural(count, "implementation"))

            if count == 1:
                return impls.selected[0]

            return impls

        metavar = "I1,..."
        hlp = "Implementation(s)"
        if count:
            hlp = runez.plural(count, "implementation")
            metavar = ",".join("I%s" % (i + 1) for i in range(count))

        kwargs.setdefault("help", "%s to use" % hlp)
        kwargs.setdefault("show_default", True)
        kwargs.setdefault("metavar", metavar)
        name = "implementation" if count == 1 else "implementations"
        return click.option(name, "-i", callback=_callback, **kwargs)

    def show_result(self, data, tokens=False):
        rtype = "tokens" if tokens else data.__class__.__name__ if data is not None else "None"
        rep = data
        if not tokens or isinstance(data, Exception):
            rep = TestSettings.represented(data)

        message = "---- %s: %s" % (runez.bold(self.name), runez.dim(rtype))
        if isinstance(data, NotImplementedError):
            print("%s - %s" % (message, rep))
            return

        print(message)
        print(rep)

    def get_outcome(self, content, tokens=False):
        if tokens:
            data = self.tokens(content)
            if isinstance(data, list):
                data = "\n".join(self.represented_token(t) for t in data)

            return data

        return self.deserialized(content)

    def deserialized(self, source):
        value = TestSettings.protected_call(self._deserialized, source)
        return self._simplified(value)

    def tokens(self, source):
        return TestSettings.protected_call(self._tokenize, source)

    def represented_token(self, token):
        return str(token)

    def _deserialized(self, source):
        if hasattr(source, "path"):
            return self._deserialized_from_path(source.path)

        return self._deserialized_from_string(source)

    def _deserialized_from_path(self, path):
        with open(path) as fh:
            return self._deserialized_from_string(fh.read())

    def _deserialized_from_string(self, source):
        raise NotImplementedError()

    def _tokenize(self, source):
        if hasattr(source, "path"):
            return self._tokens_from_path(source.path)

        return self._tokens_from_string(source)

    def _tokens_from_path(self, path):
        with open(path) as fh:
            return TestSettings.unwrapped(self._tokens_from_string(fh.read()))

    def _tokens_from_string(self, source):
        raise NotImplementedError()

    def _simplified(self, value):
        if isinstance(value, list) and len(value) == 1:
            return value[0]

        return value


class ZyamlImplementation(Implementation):
    name = "zyaml"

    def _deserialized_from_path(self, path):
        return load_path(path)

    def _deserialized_from_string(self, source):
        return load_string(source)

    def _tokens_from_path(self, path):
        return tokens_from_path(path)

    def _tokens_from_string(self, source):
        return tokens_from_string(source)

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


class RuamelImplementation(Implementation):
    name = "ruamel"

    def _deserialized_from_string(self, source):
        y = ruamel.yaml.YAML(typ="safe")
        ruamel.yaml.add_multi_constructor("", ruamel_passthrough_tags, Loader=ruamel.yaml.SafeLoader)
        return y.load_all(source)

    def _tokens_from_string(self, source):
        return ruamel.yaml.main.scan(source)


class PyyamlBaseImplementation(Implementation):
    name = "pyyaml"

    def _deserialized_from_string(self, source):
        return pyyaml.load_all(source, Loader=pyyaml.BaseLoader)

    def _tokens_from_string(self, source):
        yaml_loader = pyyaml.BaseLoader(source)
        curr = yaml_loader.get_token()
        while curr is not None:
            yield curr
            curr = yaml_loader.get_token()

    def represented_token(self, token):
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


class PoyoImplementation(Implementation):
    name = "poyo"

    def _deserialized_from_string(self, source):
        return [poyo.parse_string(source)]


class StrictImplementation(Implementation):
    name = "strict"

    def _deserialized_from_string(self, source):
        obj = strictyaml.dirty_load(source, allow_flow_style=True)
        return obj.data
