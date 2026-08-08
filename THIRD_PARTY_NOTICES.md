# Third-party notices

SC4 Effects Extensions uses the following third-party software. The listed
copyrights and licenses belong to their respective owners.

## LGPL components

### gzcom-dll

`gzcom-dll` is licensed under the GNU Lesser General Public License, version
2.1 or (at your option) any later version. Its source files are compiled into
`SC4EffectsExtensions.dll`. The unmodified upstream license is in
[`vendor/gzcom-dll/LICENSE`](vendor/gzcom-dll/LICENSE) and is included in DLL
release archives as `LICENSE-gzcom-dll`.

### sc4-render-services

`sc4-render-services` is licensed under the GNU Lesser General Public License,
version 2.1. It is a separate runtime dependency and is not included in the
SC4 Effects Extensions plugin archive. Its license is in
`vendor/sc4-render-services/LICENSE.txt`.

## MIT components

The DLL uses or links against these MIT-licensed components:

- ImGuiColorTextEdit — Copyright (c) 2017 BalazsJako
- spdlog — Copyright (c) 2016-present Gabi Melman and spdlog contributors
- {fmt} — Copyright (c) 2012-present Victor Zverovich and {fmt} contributors
- mINI — Copyright (c) 2018 Danijel Durakovic
- Windows Implementation Library (WIL) — Copyright (c) Microsoft Corporation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

The EFFDIR Editor's packaged dependencies are recorded in the CycloneDX SBOM
shipped beside each release archive. Their own distributions retain their
license files and notices.
