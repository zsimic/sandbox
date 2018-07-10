import os
import re

import poyo
import poyo.parser
import poyo.patterns
import yaml
from ruamel.yaml import YAML

import zyaml


DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')

# Temp fix
poyo.patterns._LIST_VALUE = (
    poyo.patterns._BLANK + r"-" + poyo.patterns._BLANK +
    r"('.*?'|\".*?\"|[^#\n]+?)" +
    poyo.patterns._INLINE_COMMENT + poyo.patterns._OPT_NEWLINE
)
poyo.patterns._LIST_ITEM = poyo.patterns._BLANK_LINE + r"|" + poyo.patterns._COMMENT + r"|" + poyo.patterns._LIST_VALUE
poyo.patterns._LIST = poyo.patterns._SECTION + r"(?P<items>(?:" + poyo.patterns._LIST_ITEM + r")*" + poyo.patterns._LIST_VALUE + r")"
poyo.patterns.LIST_ITEM = re.compile(poyo.patterns._LIST_VALUE, re.MULTILINE)
poyo.patterns.LIST = re.compile(poyo.patterns._LIST, re.MULTILINE)
poyo.parser.LIST = poyo.patterns.LIST
poyo.parser.LIST_ITEM = poyo.patterns.LIST_ITEM


def data_paths():
    for fname in os.listdir(DATA_FOLDER):
        if not fname.endswith('.yml'):
            continue
        yield os.path.join(DATA_FOLDER, fname)


def load_pyyaml(path):
    with open(path) as fh:
        return yaml.load(fh)


def load_poyo(path):
    with open(path) as fh:
        return poyo.parse_string(fh.read())


def load_ruamel(path):
    with open(path) as fh:
        yaml = YAML(typ='safe')
        return yaml.load(fh)


def load_zyaml(path):
    with open(path) as fh:
        d = zyaml.load(fh)
        return d
