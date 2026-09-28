# PyPI distribution migration

Trajectory Fidelity Bridge now publishes new releases as `atomicdjt-trajectory-fidelity-bridge`. The prior distribution, `atomicdjt-agent-session-bridge`, remains on PyPI at version 0.4.0. It has not been deleted or replaced with a nonfunctional package.

## Existing installations

An environment that already has `atomicdjt-agent-session-bridge==0.4.0` installed can continue using it. The Python modules, ATIF extension namespace, and `agent-session` command remain compatible. No immediate change is required.

For a new environment, install the renamed distribution:

```bash
python -m pip install atomicdjt-trajectory-fidelity-bridge
```

The renamed distribution provides both `tfb` and the existing `agent-session` command. Existing import paths and the `extra.agent_session_bridge` ATIF extension namespace are unchanged.

## Switching an existing environment

Both distributions install the same Python modules and command entry points. Do not install both and later uninstall one: package managers track files by distribution, so removing one overlapping distribution can remove files still expected by the other.

To switch, uninstall the old distribution and then install the new one:

```bash
python -m pip uninstall atomicdjt-agent-session-bridge
python -m pip install atomicdjt-trajectory-fidelity-bridge
```

If installation of the new distribution fails, restore the previous release:

```bash
python -m pip install atomicdjt-agent-session-bridge==0.4.0
```

For the lowest-risk migration, create a fresh virtual environment and install the new distribution there before retiring the old environment.

## Project dependencies

Replace `atomicdjt-agent-session-bridge` with `atomicdjt-trajectory-fidelity-bridge` in requirements files, dependency declarations, and install instructions. Do not change Python import paths, the `agent-session` command, or stored ATIF documents solely because of the distribution rename.

The old PyPI project remains available as a compatibility release. New releases and the canonical project metadata use `atomicdjt-trajectory-fidelity-bridge`.
