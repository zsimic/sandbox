# Overview

This folder contains samples for testing and verifying that this library complies with the spec.

Most samples come from [the official yaml spec](https://yaml.org/spec), as well as [yamllint](https://pypi.org/project/yamllint/)'s
collection of those examples.

Samples are organized in folders:
- [flex](./flex): samples that are correct, but require a bit of flexibility from the parsing lib to be usable
- [invalid](./invalid): effectively invalid yaml
- [js](./js): from the javascript world
- [valid](./valid): those work in [ruamel](https://pypi.org/project/ruamel.yaml/) as well, and deserialize correctly


# Testing

Regular `test_` files are exercised on each commit.

There is an extra `./run` command that provides useful things while developing, see `./run --help`:
- all commands can use various other python yaml implementations (such as ruamel, pyyaml, poyo and strictyaml)
- all commands can be scoped to a subset of samples
- commands:
    - **benchmark**: compare how long it takes to deserialize yaml files using the different python yaml libs
    - **diff**: see diff on how 2 python yaml implementations deserialize a sample
    - **find-samples**: see which samples are used (given a filter)
    - **refresh**: regenerate `test/samples/*/_xpct-*`
    - **show**: show how given sample(s) are deserialized (json representation)
    - **tokens**: see parse tokens (implemented for pyyaml and zyaml only for now)

Tests exercise all samples, and verify that the outcome is as expected
- each `.yml` sample is deserialized with this library
- then serialized back to json
- that deserialization is then compared with the recorded corresponding:
  - `./_xpct-json/sample-N.n.json`
  - `./_xpct-token/sample-N.n.txt`

If outcome is expected to change, one can run `./run refresh` to refresh all `*/_xpct-*` files.
Verify that the new outcome is correct with `git diff`.

# Examples

- Run all unit tests: `tox`
- See diff on all samples: `./run diff all`
- See diff on valid samples: `./run diff valid`
- See diff on sample 2.24 only: `./run diff 2.24`
- See how sample 2.24 is rendered by zyaml and ruamel: `./run show 2.24 -i zyaml,ruamel`
- See how sample 2.24 is rendered by zyaml and pyaml: `./run show 2.24 -i zyaml,pyyaml_base`
