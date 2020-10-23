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

$ git config -l
filter.lfs.required=true
filter.lfs.clean=git-lfs clean -- %f
filter.lfs.smudge=git-lfs smudge -- %f
filter.lfs.process=git-lfs filter-process
core.repositoryformatversion=0
core.filemode=true
core.bare=false
core.logallrefupdates=true
remote.origin.url=https://github.com/zsimic/sandbox
remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*
gc.auto=0
http.https://github.com/.extraheader=AUTHORIZATION: basic ***
branch.master.remote=origin
branch.master.merge=refs/heads/master

user.name=github-actions
user.email=github-actions@github.com

$ env | sort
AGENT_TOOLSDIRECTORY=/opt/hostedtoolcache
ANDROID_HOME=/usr/local/lib/android/sdk
ANDROID_SDK_ROOT=/usr/local/lib/android/sdk
ANT_HOME=/usr/share/ant
AZURE_EXTENSION_DIR=/opt/az/azcliextensions
BOOST_ROOT_1_69_0=/opt/hostedtoolcache/boost/1.69.0/x64
BOOST_ROOT_1_72_0=/opt/hostedtoolcache/boost/1.72.0/x64
CHROME_BIN=/usr/bin/google-chrome
CHROMEWEBDRIVER=/usr/local/share/chrome_driver
CI=true
CONDA=/usr/share/miniconda
DEBIAN_FRONTEND=noninteractive
DEPLOYMENT_BASEPATH=/opt/runner
DOTNET_MULTILEVEL_LOOKUP="0"
DOTNET_NOLOGO="1"
DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1"
GECKOWEBDRIVER=/usr/local/share/gecko_driver
GITHUB_ACTION=run1
GITHUB_ACTIONS=true
GITHUB_ACTOR=zsimic
GITHUB_API_URL=https://api.github.com
GITHUB_BASE_REF=
GITHUB_ENV=/home/runner/work/_temp/_runner_file_commands/set_env_dfc884c0-22ce-40c7-8624-a8b6ef0f5259
GITHUB_EVENT_NAME=push
GITHUB_EVENT_PATH=/home/runner/work/_temp/_github_workflow/event.json
GITHUB_GRAPHQL_URL=https://api.github.com/graphql
GITHUB_HEAD_REF=
GITHUB_JOB=run-tests
GITHUB_PATH=/home/runner/work/_temp/_runner_file_commands/add_path_dfc884c0-22ce-40c7-8624-a8b6ef0f5259
GITHUB_REF=refs/heads/master
GITHUB_REPOSITORY=zsimic/sandbox
GITHUB_REPOSITORY_OWNER=zsimic
GITHUB_RETENTION_DAYS=90
GITHUB_RUN_ID=323542268
GITHUB_RUN_NUMBER=13
GITHUB_SERVER_URL=https://github.com
GITHUB_SHA=2a9a76572f51171f39d89adf7a9cfdfd72b19239
GITHUB_WORKFLOW=Validate
GITHUB_WORKSPACE=/home/runner/work/sandbox/sandbox
GOROOT=/opt/hostedtoolcache/go/1.14.10/x64
GOROOT_1_11_X64=/opt/hostedtoolcache/go/1.11.13/x64
GOROOT_1_12_X64=/opt/hostedtoolcache/go/1.12.17/x64
GOROOT_1_13_X64=/opt/hostedtoolcache/go/1.13.15/x64
GOROOT_1_14_X64=/opt/hostedtoolcache/go/1.14.10/x64
GOROOT_1_15_X64=/opt/hostedtoolcache/go/1.15.3/x64
GRADLE_HOME=/usr/share/gradle
HOME=/home/runner
HOMEBREW_CELLAR="/home/linuxbrew/.linuxbrew/Cellar"
HOMEBREW_PREFIX="/home/linuxbrew/.linuxbrew"
HOMEBREW_REPOSITORY="/home/linuxbrew/.linuxbrew/Homebrew"
ImageOS=ubuntu18
ImageVersion=20201015.1
INVOCATION_ID=a5ab147affaa45b2aa2a68f8be8308af
JAVA_HOME=/usr/lib/jvm/adoptopenjdk-8-hotspot-amd64
JAVA_HOME_11_X64=/usr/lib/jvm/adoptopenjdk-11-hotspot-amd64
JAVA_HOME_12_X64=/usr/lib/jvm/adoptopenjdk-12-hotspot-amd64
JAVA_HOME_7_X64=/usr/lib/jvm/zulu-7-azure-amd64
JAVA_HOME_8_X64=/usr/lib/jvm/adoptopenjdk-8-hotspot-amd64
JOURNAL_STREAM=9:20627
LANG=C.UTF-8
LD_LIBRARY_PATH=/opt/hostedtoolcache/Python/2.7.18/x64/lib
LEIN_HOME=/usr/local/lib/lein
LEIN_JAR=/usr/local/lib/lein/self-installs/leiningen-2.9.4-standalone.jar
M2_HOME=/usr/share/apache-maven-3.6.3
PATH=/opt/hostedtoolcache/Python/2.7.18/x64/bin:/opt/hostedtoolcache/Python/2.7.18/x64:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:/opt/pipx_bin:/usr/share/rust/.cargo/bin:/home/runner/.config/composer/vendor/bin:/home/runner/.dotnet/tools:/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
PERFLOG_LOCATION_SETTING=RUNNER_PERFLOG
PIPX_BIN_DIR="/opt/pipx_bin"
PIPX_HOME="/opt/pipx"
POWERSHELL_DISTRIBUTION_CHANNEL=GitHub-Actions-ubuntu18
PWD=/home/runner/work/sandbox/sandbox
pythonLocation=/opt/hostedtoolcache/Python/2.7.18/x64
RUNNER_OS=Linux
RUNNER_PERFLOG=/home/runner/perflog
RUNNER_TEMP=/home/runner/work/_temp
RUNNER_TOOL_CACHE=/opt/hostedtoolcache
RUNNER_TRACKING_ID=github_e44b9e4d-cb63-451c-a92e-4dc697bf5571
RUNNER_USER=runner
RUNNER_WORKSPACE=/home/runner/work/sandbox
SELENIUM_JAR_PATH=/usr/share/java/selenium-server-standalone.jar
SHLVL=1
SWIFT_PATH=/usr/share/swift/usr/bin
USER=runner
VCPKG_INSTALLATION_ROOT=/usr/local/share/vcpkg
```
