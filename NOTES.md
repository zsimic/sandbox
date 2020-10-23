# Github actions setup

```
$ pwd
/home/runner/work/sandbox/sandbox

$ which -a tox
/opt/hostedtoolcache/Python/3.7.9/x64/bin/tox

$ which -a python
/opt/hostedtoolcache/Python/3.7.9/x64/bin/python
/opt/hostedtoolcache/Python/3.7.9/x64/python
/usr/bin/python

$ which -a python3
/opt/hostedtoolcache/Python/3.7.9/x64/bin/python3
/usr/bin/python3

$ which -a pip
/opt/hostedtoolcache/Python/3.7.9/x64/bin/pip
/usr/bin/pip

$ which -a pip3
/opt/hostedtoolcache/Python/3.7.9/x64/bin/pip3
/usr/bin/pip3

$ /usr/bin/python --version
Python 2.7.17

$ /usr/bin/python3 --version
Python 3.6.9

$ python --version
Python 3.7.9

$ python -c 'import sys; print("\n".join("%s: %s" % (x, getattr(sys, x)) for x in dir(sys) if "prefix" in x))'
base_exec_prefix: /opt/hostedtoolcache/Python/3.7.9/x64
base_prefix: /opt/hostedtoolcache/Python/3.7.9/x64
exec_prefix: /opt/hostedtoolcache/Python/3.7.9/x64
prefix: /opt/hostedtoolcache/Python/3.7.9/x64

$ which -a git
/usr/bin/git

$ git --version
git version 2.28.0

s```
