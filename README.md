# SC4 DLL Template

`SC4 DLL Template` is a GitHub template repository for building new SimCity 4 Win32 DLL plugins with the same basic toolchain and deployment flow used in `sc4-advanced-plop`.

It includes:

- `gzcom-dll`, `sc4-render-services`, and `vcpkg` as git submodules
- `spdlog`, `mINI` (`pulzed-mini` in vcpkg), and `WIL` via vcpkg manifest mode
- the Win32 static-library vcpkg triplet `x86-windows-static-md`
- Visual Studio 2022 Win32 debug and release presets
- automatic post-build deployment to `Documents\SimCity 4\Plugins`
- a starter `cRZMessage2COMDirector` implementation
- reusable logging, version detection, and INI settings helpers
- a minimal ImGui panel wired through `sc4-render-services`
- a GitHub Actions workflow that builds Win32 debug and release DLL artifacts
- a tag-based GitHub Actions release workflow that publishes a packaged release zip

## Quick start

1. Create a new repository from this template on GitHub.
2. Clone it with submodules:

```powershell
git clone --recurse-submodules <your-repo-url>
cd <your-repo-directory>
```

3. Rename the template identifiers:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\Rename-Project.ps1 -ProjectName YourDllName
```

4. Bootstrap vcpkg:

```powershell
.\vendor\vcpkg\bootstrap-vcpkg.bat
```

The template defaults to the Win32 static-library triplet used by this codebase:

```text
x86-windows-static-md
```

5. Build `imgui.lib` from `sc4-render-services`:

```powershell
cmake -S .\vendor\sc4-render-services -B .\vendor\sc4-render-services\build -G "Visual Studio 17 2022" -A Win32
cmake --build .\vendor\sc4-render-services\build --config Release --target imgui
```

6. Configure and build the DLL:

```powershell
cmake --preset vs2022-win32-debug
cmake --build --preset vs2022-win32-debug-build
```

For a release build:

```powershell
cmake --preset vs2022-win32-release
cmake --build --preset vs2022-win32-release-build
```

## Deployment

By default, the DLL target copies the built DLL into:

```text
%USERPROFILE%\Documents\SimCity 4\Plugins
```

The default INI file in `dist/` is copied only if it does not already exist in the Plugins folder, so user changes survive rebuilds.

Disable automatic deployment with:

```powershell
cmake --preset vs2022-win32-debug -DSC4_ENABLE_PLUGIN_DEPLOYMENT=OFF
```

## CI and releases

- `build.yml` runs on pushes to `main`, pull requests, and manual dispatch to validate debug and release builds.
- `release.yml` runs on tags matching `v*` and publishes a GitHub Release containing a zip with the built DLL, default INI, and README.

## Template layout

- `src/dll/`: DLL source, starter director, utilities, and demo panel
- `dist/`: default runtime INI file
- `cmake/`: helper scripts used by the build
- `tools/`: template maintenance helpers such as project renaming
- `vendor/`: git submodules

## Notes

- The template is intentionally Win32-only because SimCity 4 is a 32-bit game.
- `sc4-render-services` must be built before the DLL because this template links against its `imgui.lib`.
- `mINI` is consumed via vcpkg as the `pulzed-mini` port and included as `mini/ini.h`.
