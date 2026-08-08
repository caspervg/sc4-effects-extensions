# SC4 Effects Extensions

Tools for authoring, loading, testing, and inspecting SimCity 4 effects. The repository contains an in-game DLL, a standalone packed-resource editor, and documentation for the recovered effects language and `EFFDIR` binary format.

| Component | Purpose |
| --- | --- |
| `SC4EffectsExtensions.dll` | Loads and recompiles `.fx` sources in-game, exposes an effects console, and writes the compiled effects resource to a DBPF package. |
| EFFDIR Editor | Opens packed effects resources in DBPF packages or as raw blobs and edits their records without discarding unknown data. |
| Documentation | Describes the recovered `.fx` syntax, effect and particle commands, resource binding, and the packed `EFFDIR` format. |

## In-game DLL

The DLL extends the game's effects bootstrap and adds an ImGui-based **SC4 Effects Console**. It can:

- load `.fx` files from the user Plugins directory, optionally including subdirectories;
- refresh the game's effect catalog after editing a source file;
- list and filter parsed effect names;
- spawn effects by name, or keep one effect active while changing its position, rotation, and scale;
- edit `.fx` files with syntax highlighting and surface parser errors on their source lines;
- show effects-manager statistics and a live event log;
- enable the game's packed-resource save path and write the compiled `EFFDIR` resource to `SC4EffectsExtensions.PackedEffects.dat` by default.

The hooks and catalog probe currently target the Windows executable version **1.1.641**. Other detected versions are not patched.

### Installation

Download the Win32 plugin archive from a release and copy its contents into the SimCity 4 user Plugins directory:

```text
Documents\SimCity 4\Plugins
```

Keep `SC4EffectsExtensions.dll` and `SC4EffectsExtensions.ini` together. The in-game panel is provided through [sc4-render-services](https://github.com/caspervg/sc4-render-services), which must also be installed for the console UI to appear.

### Configuration

`SC4EffectsExtensions.ini` uses the following settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `LogLevel` | `info` | `trace`, `debug`, `info`, `warn`, `error`, `critical`, or `off`. |
| `LogToFile` | `true` | Write `SC4EffectsExtensions.log` in the SimCity 4 user-data directory. |
| `StartWindowVisible` | `true` | Show the effects console when the plugin starts. |
| `LoadPluginFxRecursively` | `false` | Search the configured `.fx` root recursively. |
| `PluginFxRoot` | blank | Directory containing `.fx` sources. Blank uses the game's user Plugins directory. |
| `PackedEffectsOutputPath` | blank | Output DBPF path. Blank uses `SC4EffectsExtensions.PackedEffects.dat` beside the Plugins directory. |

Boolean values accept `true`/`false`, `1`/`0`, and `yes`/`no`.

## EFFDIR Editor

`tools/effdir-editor` is a wxPython desktop editor for the packed effects resource `EA5118B0-EA5118B1-00000001`. It accepts DBPF packages and raw extracted `EFFDIR` blobs and provides a resource tree, field editor, synchronized hex view, reference navigation, search, diagnostics, and undo/redo.

The editor supports lossless read/write round trips for major versions 3 and 4, including the version-1 effect-description profile, marker words, and unknown or trailing bytes. Unsupported versions and malformed resources open as raw-preserved, read-only data instead of being interpreted speculatively.

Current limitations:

- command bindings are descriptive; multi-field `set_command` edits are not implemented;
- DBPF entries are saved uncompressed because QFS compression is not implemented;
- flags are edited as raw values rather than through per-bit controls.

Prebuilt Windows x64 packages are attached to releases. The macOS arm64 package is experimental. To run from source, install [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer:

```powershell
cd tools\effdir-editor
uv sync --group dev
uv run effdir-editor
```

Run its tests with:

```powershell
uv run pytest
```

See the [editor README](tools/effdir-editor/README.md) for its internal architecture and API boundary.

## Effects documentation

The [documentation index](docs/README.md) is the starting point for the recovered effects language. It covers:

- comments, variables, namespaces, macros, evaluation, blocks, and scopes;
- top-level effects, particles, dynamic particles, decals, shakes, lights, and sequences;
- nested visual, particle, sound, camera, chain, brush, scrubber, automata, and other effect commands;
- particle sources, emission, forces, warps, collision, appearance curves, and rendering;
- resource binding and the packed `EFFDIR` wire format.

Each page marks behavior as **Confirmed**, **Partial**, or **Inferred** so recovered facts remain distinct from interpretation. The separate render-properties/rules DSL and reverse-engineering notebooks are outside the documentation's scope.

## Building the DLL

Requirements:

- Windows and Visual Studio 2022 with C++ desktop tools;
- CMake 3.20 or newer;
- Git submodules;
- a 32-bit build, because SimCity 4 is a 32-bit process.

Clone and prepare the dependencies:

```powershell
git clone --recurse-submodules <repository-url>
cd sc4-effects-extensions
.\vendor\vcpkg\bootstrap-vcpkg.bat

cmake -S .\vendor\sc4-render-services `
      -B .\vendor\sc4-render-services\build `
      -G "Visual Studio 17 2022" -A Win32
cmake --build .\vendor\sc4-render-services\build --config Release --target imgui
```

Then build the plugin:

```powershell
cmake --preset vs2022-win32-release
cmake --build --preset vs2022-win32-release-build --parallel
```

Use `vs2022-win32-debug` and `vs2022-win32-debug-build` for a debug build. CMake uses the `x86-windows-static-md` vcpkg triplet and C++23. By default, a successful build copies the DLL into `Documents\SimCity 4\Plugins` and adds the default INI only when one does not already exist. Disable this with:

```powershell
cmake --preset vs2022-win32-release -DSC4_ENABLE_PLUGIN_DEPLOYMENT=OFF
```

## Repository layout

```text
src/dll/             Win32 plugin, hooks, effects console, and utilities
tools/effdir-editor/ Standalone Python editor and tests
docs/                Effects-language and binary-format reference
dist/                Default plugin configuration
cmake/               Build helpers
vendor/              gzcom-dll, sc4-render-services, text editor, and vcpkg
```

CI builds Debug and Release Win32 DLLs and runs the editor test suite. Tags matching `vMAJOR.MINOR.PATCH` publish whichever plugin and editor components changed since the previous release.
