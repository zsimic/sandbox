import os
import re

import poyo
import poyo.parser
import poyo.patterns
import yaml
from ruamel.yaml import YAML

import zyaml


DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")


def resource(*relative_paths):
    return os.path.join(DATA_FOLDER, *relative_paths)


def relative_path(full_path):
    if full_path and full_path.startswith(DATA_FOLDER):
        return full_path[len(DATA_FOLDER) + 1:]
    return full_path


def data_paths(folder=DATA_FOLDER):
    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if os.path.isdir(fpath):
            for path in data_paths(fpath):
                yield path
        if not fname.endswith(".yml"):
            continue
        yield fpath


def load_pyyaml(path):
    with open(path) as fh:
        docs = list(yaml.load_all(fh))
        if len(docs) == 1:
            return docs[0]
        return docs


def load_poyo(path):
    with open(path) as fh:
        return poyo.parse_string(fh.read())


def load_ruamel(path):
    with open(path) as fh:
        yaml = YAML(typ="safe")
        docs = list(yaml.load_all(fh))
        if len(docs) == 1:
            return docs[0]
        return docs


def load_zyaml(path):
    with open(path) as fh:
        d = zyaml.load(fh)
        return d
