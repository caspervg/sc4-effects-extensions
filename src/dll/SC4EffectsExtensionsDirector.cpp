#include "SC4EffectsExtensionsDirector.hpp"

#include <array>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cIGZFrameWork.h>
#include <filesystem>
#include <cstdio>
#include <cstring>

#include "GZServPtrs.h"
#include "cGZPersistResourceKey.h"
#include "cIGZCOM.h"
#include "cIGZDBSegmentPackedFile.h"
#include "cIGZMessage2Standard.h"
#include "cIGZMessageServer2.h"
#include "cIGZPersistDBSegment.h"
#include "cIGZPersistResourceManager.h"
#include "cIGZFileSystem.h"
#include "cISC4App.h"
#include "cISC4City.h"
#include "cISC4EffectsManager.h"
#include "cISC4VisualEffect.h"
#include "cRZBaseString.h"
#include "panels/EffectsPanel.hpp"
#include "public/ImGuiPanelAdapter.h"
#include "public/ImGuiServiceIds.h"
#include "utils/Logger.h"
#include "utils/EffectsTransform.h"
#include "utils/Settings.h"
#include "utils/VersionDetection.h"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <Windows.h>
#include <wil/win32_helpers.h>

namespace {
constexpr uint32_t kDirectorId = 0xE5C2B9A7u;
constexpr uint32_t kPanelId = 0xCA510001u;
constexpr uint32_t kSC4MessagePostCityInit = 0x26D31EC1u;
constexpr uint32_t kSC4MessagePreCityShutdown = 0x26D31EC2u;
constexpr size_t kInlineHookJumpByteCount = 5;
constexpr size_t kInlineHookMaxPrologueBytes = 12;
constexpr uint16_t kSupportedGameVersionForCatalogProbe = 641;
constexpr uint16_t kSupportedGameVersionForEffectsHooks = 641;
constexpr uintptr_t kEffectsBootstrapLoadRva = 0x001945B0;
constexpr uintptr_t kEffectsParseQueuedFilesRva = 0x0018E4E0;
constexpr uintptr_t kEffectsParserCtorRva = 0x0019EEC0;
constexpr ptrdiff_t kEffectsParserResourceSaveEnabledOffset = 0xA4;
constexpr ptrdiff_t kEffectsParserResourcePtrOffset = 0x94;
constexpr ptrdiff_t kEffectsParserPackedKeyTypeOffset = 0x98;
constexpr ptrdiff_t kEffectsParserPackedKeyGroupOffset = 0x9C;
constexpr ptrdiff_t kEffectsParserPackedKeyInstanceOffset = 0xA0;
constexpr ptrdiff_t kEffectsParserSaveEnableInterfaceOffset = 0x4EC;
constexpr ptrdiff_t kEffectsBootstrapParserInterfaceOffset = 0xC78;
constexpr ptrdiff_t kEffectsBootstrapParserObjectOffset = 0xC7C;
constexpr size_t kEffectsParserEnableResourceSavingVtableIndex = 1;
constexpr ptrdiff_t kParserBlockStackBeginOffset = 0x30;
constexpr ptrdiff_t kParserBlockStackEndOffset = 0x34;
constexpr uint32_t kPackedEffectsResourceType = 0xEA5118B0u;
constexpr uint32_t kPackedEffectsResourceGroup = 0xEA5118B1u;
constexpr size_t kMaxCatalogEffectCount = 8192;
constexpr size_t kMaxHashBucketCount = 32768;

struct MsvcStringLayout {
    union {
        char inlineBuffer[16];
        const char* heapBuffer;
    };
    uint32_t length;
    uint32_t capacity;
};

struct CatalogProbeResult {
    std::vector<SC4EffectsExtensionsDirector::EffectsCatalogSource> sources;
    std::vector<std::string> names;
};

using EffectsBootstrapLoadFn = void(__thiscall*)(void*);
using EffectsParseQueuedFilesFn = void(__fastcall*)(int, void*);
using EffectsParserCtorFn = void*(__thiscall*)(void*, int);
using EffectsParserEnableResourceSavingFn = void(__fastcall*)(void*);
using FileParserAddInputFilePathFn = void(__thiscall*)(void*, const char*, uint32_t);
using FileParserGetLastErrorStringFn = const char*(__thiscall*)(void*);
using FileExistsFn = bool(__cdecl*)(int*);

struct InlineHook {
    const char* name;
    uintptr_t rva;
    size_t byteCount;
    std::array<uint8_t, kInlineHookMaxPrologueBytes> expected;
    void* hookFn;
    uintptr_t patchAddress = 0;
    void* trampoline = nullptr;
    std::array<uint8_t, kInlineHookMaxPrologueBytes> original{};
    bool installed = false;
};

void __fastcall HookEffectsBootstrapLoad(void* pThis, void*) noexcept;
void __fastcall HookEffectsParseQueuedFiles(int pThis, void*) noexcept;
void* __fastcall HookEffectsParserCtor(void* pThis, void*, int ctorArg) noexcept;
bool __cdecl HookFileExistsForEffectsBootstrap(int* path) noexcept;

SC4EffectsExtensionsDirector* g_activeDirector = nullptr;
EffectsBootstrapLoadFn g_originalEffectsBootstrapLoad = nullptr;
EffectsParseQueuedFilesFn g_originalEffectsParseQueuedFiles = nullptr;
EffectsParserCtorFn g_originalEffectsParserCtor = nullptr;
FileExistsFn g_originalFileExistsForEffectsBootstrap = nullptr;
bool g_loadPluginFxRecursively = false;
std::filesystem::path g_pluginFxRoot;
bool g_inEffectsBootstrapLoad = false;

InlineHook g_effectsBootstrapLoadHook{"EffectsBootstrap::LoadAllEffects", kEffectsBootstrapLoadRva, 9, {0x83, 0xEC, 0x64, 0x53, 0x55, 0x56, 0x57, 0x8B, 0xE9, 0x00, 0x00, 0x00}, reinterpret_cast<void*>(&HookEffectsBootstrapLoad)};
InlineHook g_effectsParseQueuedFilesHook{"EffectsParser::ParseQueuedFiles", kEffectsParseQueuedFilesRva, 9, {0x56, 0x8B, 0xF1, 0x8B, 0x8E, 0x78, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00}, reinterpret_cast<void*>(&HookEffectsParseQueuedFiles)};
InlineHook g_effectsParserCtorHook{"EffectsParser::Ctor", kEffectsParserCtorRva, 8, {0x8B, 0x44, 0x24, 0x04, 0x53, 0x56, 0x33, 0xDB}, reinterpret_cast<void*>(&HookEffectsParserCtor)};
InlineHook g_effectsFileExistsHook{"EffectsBootstrap::FileExists", 0x00519E96, 6, {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, reinterpret_cast<void*>(&HookFileExistsForEffectsBootstrap)};

void ApplyTrackedTransformState(cS3DTransform& transform, const SC4EffectsExtensionsDirector::TrackedEffectState& state) noexcept {
    EffectTransformParams params{};
    params.position[0] = state.position[0];
    params.position[1] = state.position[1];
    params.position[2] = state.position[2];
    params.rotation[0] = state.rotation[0];
    params.rotation[1] = state.rotation[1];
    params.rotation[2] = state.rotation[2];
    params.scale = state.scale;
    EffectsTransformUtil::Apply(transform, params);
}

void EmitHookEvent(const std::string& line) {
    if (g_activeDirector) {
        g_activeDirector->RecordHookEvent(line);
    }
    LOG_INFO(line);
}

uintptr_t ResolvePatchAddress(uintptr_t address) noexcept {
    uintptr_t current = address;
    for (int i = 0; i < 6; ++i) {
        const auto* p = reinterpret_cast<const uint8_t*>(current);
        if (p[0] == 0xE9) {
            current = current + 5 + *reinterpret_cast<const int32_t*>(p + 1);
            continue;
        }
        if (p[0] == 0xEB) {
            current = current + 2 + static_cast<int8_t>(p[1]);
            continue;
        }
        if (p[0] == 0xFF && p[1] == 0x25) {
            current = *reinterpret_cast<const uintptr_t*>(*reinterpret_cast<const uintptr_t*>(p + 2));
            continue;
        }
        break;
    }
    return current;
}

bool InstallInlineHook(InlineHook& hook) noexcept {
    if (hook.installed) return true;
    const auto moduleBase = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    if (!moduleBase) return false;
    hook.patchAddress = ResolvePatchAddress(moduleBase + hook.rva);
    auto* target = reinterpret_cast<uint8_t*>(hook.patchAddress);
    if (!target) return false;
    if (std::memcmp(target, hook.expected.data(), hook.byteCount) != 0) return false;
    std::memcpy(hook.original.data(), target, hook.byteCount);
    auto* trampoline = static_cast<uint8_t*>(VirtualAlloc(nullptr, hook.byteCount + kInlineHookJumpByteCount, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE));
    if (!trampoline) return false;
    std::memcpy(trampoline, target, hook.byteCount);
    trampoline[hook.byteCount] = 0xE9;
    const auto trampRel = static_cast<int32_t>(reinterpret_cast<intptr_t>(target + hook.byteCount) - (reinterpret_cast<intptr_t>(trampoline + hook.byteCount) + kInlineHookJumpByteCount));
    std::memcpy(trampoline + hook.byteCount + 1, &trampRel, sizeof(trampRel));
    DWORD oldProtect = 0;
    if (!VirtualProtect(target, hook.byteCount, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        VirtualFree(trampoline, 0, MEM_RELEASE);
        return false;
    }
    target[0] = 0xE9;
    const auto hookRel = static_cast<int32_t>(reinterpret_cast<intptr_t>(hook.hookFn) - (reinterpret_cast<intptr_t>(target) + kInlineHookJumpByteCount));
    std::memcpy(target + 1, &hookRel, sizeof(hookRel));
    for (size_t i = kInlineHookJumpByteCount; i < hook.byteCount; ++i) target[i] = 0x90;
    FlushInstructionCache(GetCurrentProcess(), target, hook.byteCount);
    DWORD restoredProtect = 0;
    VirtualProtect(target, hook.byteCount, oldProtect, &restoredProtect);
    hook.trampoline = trampoline;
    hook.installed = true;
    return true;
}

void UninstallInlineHook(InlineHook& hook) noexcept {
    if (!hook.installed) return;
    auto* target = reinterpret_cast<uint8_t*>(hook.patchAddress);
    if (target) {
        DWORD oldProtect = 0;
        if (VirtualProtect(target, hook.byteCount, PAGE_EXECUTE_READWRITE, &oldProtect)) {
            std::memcpy(target, hook.original.data(), hook.byteCount);
            FlushInstructionCache(GetCurrentProcess(), target, hook.byteCount);
            DWORD restoredProtect = 0;
            VirtualProtect(target, hook.byteCount, oldProtect, &restoredProtect);
        }
    }
    if (hook.trampoline) VirtualFree(hook.trampoline, 0, MEM_RELEASE);
    hook.trampoline = nullptr;
    hook.patchAddress = 0;
    hook.installed = false;
}

uint8_t ReadParserByte(int parser, ptrdiff_t offset) noexcept { return parser ? *reinterpret_cast<const uint8_t*>(parser + offset) : 0; }
uint32_t ReadParserDword(int parser, ptrdiff_t offset) noexcept { return parser ? *reinterpret_cast<const uint32_t*>(parser + offset) : 0; }
int GetRZStringVectorSize(const int* pVector) noexcept {
    if (!pVector) return -1;
    const auto begin = pVector[0];
    const auto end = pVector[1];
    return (begin && end >= begin) ? (end - begin) / 0x14 : -1;
}
int GetParserBlockDepth(int parser) noexcept {
    const auto begin = ReadParserDword(parser, kParserBlockStackBeginOffset);
    const auto end = ReadParserDword(parser, kParserBlockStackEndOffset);
    return (begin && end >= begin) ? static_cast<int>((end - begin) / sizeof(uint32_t)) : -1;
}
uint32_t ResolveConcreteParser(void* pParserInterface) noexcept {
    if (!pParserInterface) return 0;
    const auto vtable = *reinterpret_cast<void***>(pParserInterface);
    if (!vtable || !vtable[0x28 / sizeof(void*)]) return 0;
    using ResolveFn = uint32_t(__thiscall*)(void*);
    return reinterpret_cast<ResolveFn>(vtable[0x28 / sizeof(void*)])(pParserInterface);
}

bool IsReadableRange(const void* pAddress, const size_t size) noexcept {
    if (!pAddress || size == 0) return false;
    MEMORY_BASIC_INFORMATION mbi{};
    if (VirtualQuery(pAddress, &mbi, sizeof(mbi)) != sizeof(mbi)) return false;
    if (mbi.State != MEM_COMMIT) return false;
    if ((mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) != 0) return false;
    const auto start = reinterpret_cast<uintptr_t>(pAddress);
    const auto end = start + size;
    const auto regionStart = reinterpret_cast<uintptr_t>(mbi.BaseAddress);
    const auto regionEnd = regionStart + mbi.RegionSize;
    return end >= start && end <= regionEnd;
}

bool IsPlausibleEffectNameChar(const unsigned char ch) noexcept {
    return std::isalnum(ch) || ch == '_' || ch == '-' || ch == '.' || ch == '/';
}

bool HasFxExtension(const std::filesystem::path& path) {
    const auto extension = path.extension().string();
    if (extension.size() != 3) return false;
    return std::tolower(static_cast<unsigned char>(extension[0])) == '.' &&
           std::tolower(static_cast<unsigned char>(extension[1])) == 'f' &&
           std::tolower(static_cast<unsigned char>(extension[2])) == 'x';
}

std::vector<std::filesystem::path> EnumeratePluginFxFiles() {
    std::vector<std::filesystem::path> files;
    if (!g_loadPluginFxRecursively || g_pluginFxRoot.empty()) return files;

    std::error_code ec;
    if (!std::filesystem::exists(g_pluginFxRoot, ec) || ec) return files;

    for (std::filesystem::recursive_directory_iterator it(g_pluginFxRoot, ec), end; it != end; it.increment(ec)) {
        if (ec) break;
        if (!it->is_regular_file(ec) || ec) continue;

        const auto path = it->path();
        if (!HasFxExtension(path)) continue;
        if (_stricmp(path.filename().string().c_str(), "main.fx") == 0) continue;
        files.push_back(path);
    }

    std::sort(files.begin(), files.end());
    return files;
}

std::filesystem::path GetGameUserPluginDirectory() {
    cISC4AppPtr app;
    if (app) {
        cRZBaseString path;
        if (app->GetUserPluginDirectory(path)) {
            const char* pText = path.ToChar();
            if (pText && *pText) {
                return std::filesystem::path(pText);
            }
        }
    }

    cIGZFileSystemPtr fileSystem;
    if (fileSystem) {
        const char* pText = fileSystem->PlugInDirectory();
        if (pText && *pText) {
            return std::filesystem::path(pText);
        }
    }

    return {};
}

std::filesystem::path GetDefaultPackedEffectsOutputPath() {
    const auto pluginsPath = GetGameUserPluginDirectory();
    if (!pluginsPath.empty()) {
        const auto parentPath = pluginsPath.parent_path();
        if (!parentPath.empty()) {
            return parentPath / "SC4EffectsExtensions.PackedEffects.dat";
        }
        return pluginsPath / "SC4EffectsExtensions.PackedEffects.dat";
    }
    return {};
}

void QueueExtraPluginFxFilesOnParserInterface(void* pFileParser) noexcept {
    if (!g_loadPluginFxRecursively || !pFileParser) return;

    if (!pFileParser) {
        LOG_WARN("Plugin .fx queue skipped: file parser interface is null");
        return;
    }

    auto* const vtable = *reinterpret_cast<void***>(pFileParser);
    if (!vtable || !vtable[0x18 / sizeof(void*)]) {
        LOG_WARN("Plugin .fx queue skipped: AddInputFilePath slot is unavailable");
        return;
    }

    const auto files = EnumeratePluginFxFiles();
    if (files.empty()) {
        LOG_INFO("Plugin .fx queue: no extra .fx files found under '{}'", g_pluginFxRoot.string());
        return;
    }

    const auto addInputFilePath = reinterpret_cast<FileParserAddInputFilePathFn>(vtable[0x18 / sizeof(void*)]);
    size_t queuedCount = 0;
    for (const auto& path : files) {
        const auto pathString = path.string();
        addInputFilePath(pFileParser, pathString.c_str(), 3);
        LOG_INFO("Plugin .fx queue: {}", pathString);
        ++queuedCount;
    }

    LOG_INFO("Plugin .fx queue: queued {} extra .fx files from '{}'", queuedCount, g_pluginFxRoot.string());
}

void LogFileParserErrorConsole(void* pFileParser) noexcept {
    if (!pFileParser) {
        return;
    }

    auto* const vtable = *reinterpret_cast<void***>(pFileParser);
    if (!vtable || !vtable[0x28 / sizeof(void*)]) {
        return;
    }

    const auto getLastErrorString = reinterpret_cast<FileParserGetLastErrorStringFn>(vtable[0x28 / sizeof(void*)]);
    const char* const pError = getLastErrorString(pFileParser);
    if (!pError || !*pError) {
        return;
    }

    std::string errorText(pError);
    LOG_ERROR("Effects parser console: {}", errorText);
    if (g_activeDirector) {
        g_activeDirector->RecordConsoleEvent(
            SC4EffectsExtensionsDirector::EventSeverity::Error,
            "Effects parser: " + errorText);
    }
}

bool LooksLikeEffectName(const std::string_view text) noexcept {
    if (text.empty() || text.size() > 128) return false;
    for (const unsigned char ch : text) {
        if (!IsPlausibleEffectNameChar(ch)) return false;
    }
    return true;
}

bool TryReadMsvcStringLayout(const void* pAddress, MsvcStringLayout& out) noexcept {
    if (!IsReadableRange(pAddress, sizeof(MsvcStringLayout))) return false;

    __try {
        out = *reinterpret_cast<const MsvcStringLayout*>(pAddress);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool TryReadVectorTriplet(
    const uint8_t* pBase,
    const ptrdiff_t offset,
    uint32_t& begin,
    uint32_t& end,
    uint32_t& capacity) noexcept
{
    if (!IsReadableRange(pBase + offset, sizeof(uint32_t) * 3)) return false;

    __try {
        begin = *reinterpret_cast<const uint32_t*>(pBase + offset);
        end = *reinterpret_cast<const uint32_t*>(pBase + offset + 4);
        capacity = *reinterpret_cast<const uint32_t*>(pBase + offset + 8);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool TryReadUint32(const void* pAddress, uint32_t& out) noexcept {
    if (!IsReadableRange(pAddress, sizeof(uint32_t))) return false;
    __try {
        out = *reinterpret_cast<const uint32_t*>(pAddress);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool TryReadCStringPointer(const void* pAddress, const size_t maxLength, std::string& out) noexcept {
    out.clear();
    if (!IsReadableRange(pAddress, sizeof(const char*))) return false;

    const char* pText = nullptr;
    __try {
        pText = *reinterpret_cast<const char* const*>(pAddress);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }

    if (!pText || !IsReadableRange(pText, 1)) return false;

    size_t length = 0;
    while (length < maxLength) {
        char ch = 0;
        __try {
            ch = pText[length];
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            return false;
        }
        if (ch == '\0') break;
        if (!IsPlausibleEffectNameChar(static_cast<unsigned char>(ch))) return false;
        ++length;
    }

    if (length == 0 || length >= maxLength) return false;
    out.assign(pText, length);
    return true;
}

bool TryReadByte(const void* pAddress, uint8_t& out) noexcept {
    if (!IsReadableRange(pAddress, sizeof(uint8_t))) return false;
    __try {
        out = *reinterpret_cast<const uint8_t*>(pAddress);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

void AppendHexBytesLine(
    std::vector<std::string>& lines,
    const char* label,
    const uint8_t* pBase,
    const size_t offset,
    const size_t length) noexcept
{
    char line[256]{};
    int written = std::snprintf(line, sizeof(line), "%s +0x%03zX:", label, offset);
    if (written < 0) return;

    for (size_t i = 0; i < length && static_cast<size_t>(written) + 4 < sizeof(line); ++i) {
        uint8_t value = 0;
        if (!TryReadByte(pBase + offset + i, value)) {
            written += std::snprintf(line + written, sizeof(line) - static_cast<size_t>(written), " ??");
            continue;
        }
        written += std::snprintf(line + written, sizeof(line) - static_cast<size_t>(written), " %02X", value);
    }

    lines.emplace_back(line);
}

void AppendNodeDump(
    std::vector<std::string>& lines,
    const uint32_t nodeAddress,
    const size_t bucketIndex,
    const size_t chainIndex) noexcept
{
    char header[160]{};
    std::snprintf(
        header,
        sizeof(header),
        "bucket[%zu] node[%zu]=%08X",
        bucketIndex,
        chainIndex,
        nodeAddress);
    lines.emplace_back(header);

    const auto* const pNode = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(nodeAddress));
    for (size_t offset = 0; offset < 0x20; offset += 0x10) {
        AppendHexBytesLine(lines, "node", pNode, offset, 0x10);
    }
}

std::vector<std::string> ProbeDoMessageHashNames(cISC4EffectsManager* pEffectsManager) noexcept {
    std::vector<std::string> names;
    if (!pEffectsManager) return names;

    auto* const pManager = reinterpret_cast<const uint8_t*>(pEffectsManager);
    uint32_t bucketsBegin = 0;
    uint32_t bucketsEnd = 0;
    uint32_t bucketState = 0;
    uint32_t recordBase = 0;

    if (!TryReadUint32(pManager + 0xD10, bucketsBegin)) return names;
    if (!TryReadUint32(pManager + 0xD14, bucketsEnd)) return names;
    if (!TryReadUint32(pManager + 0xD1C, bucketState)) return names;
    if (!TryReadUint32(pManager + 0x188, recordBase)) return names;

    if (bucketState == 0 || bucketsBegin == 0 || bucketsEnd <= bucketsBegin || recordBase == 0) return names;

    const size_t bucketCount = (bucketsEnd - bucketsBegin) / sizeof(uint32_t);
    if (bucketCount == 0 || bucketCount > kMaxHashBucketCount) return names;
    if (!IsReadableRange(reinterpret_cast<const void*>(bucketsBegin), bucketCount * sizeof(uint32_t))) return names;

    for (size_t bucketIndex = 0; bucketIndex < bucketCount; ++bucketIndex) {
        uint32_t node = 0;
        if (!TryReadUint32(reinterpret_cast<const void*>(bucketsBegin + (bucketIndex * sizeof(uint32_t))), node)) continue;

        size_t chainDepth = 0;
        while (node && chainDepth < 2048) {
            uint32_t next = 0;
            uint32_t effectIndex = 0;
            if (!TryReadUint32(reinterpret_cast<const void*>(node), next)) break;
            if (!TryReadUint32(reinterpret_cast<const void*>(node + 8), effectIndex)) break;

            std::string name;
            const auto recordAddr = static_cast<uintptr_t>(recordBase) + (static_cast<uintptr_t>(effectIndex) * 0x10) + 4;
            if (TryReadCStringPointer(reinterpret_cast<const void*>(recordAddr), 128, name) &&
                pEffectsManager->HasVisualEffect(name.c_str())) {
                names.push_back(std::move(name));
            }

            node = next;
            ++chainDepth;
        }
    }

    std::sort(names.begin(), names.end());
    names.erase(std::unique(names.begin(), names.end()), names.end());
    return names;
}

bool TryReadStringSpan(const uint32_t begin, const uint32_t end, std::string& out) noexcept {
    out.clear();
    if (begin == 0 || end < begin) return false;
    const size_t length = static_cast<size_t>(end - begin);
    if (length == 0 || length > 128) return false;
    if (!IsReadableRange(reinterpret_cast<const void*>(begin), length)) return false;

    const auto* pText = reinterpret_cast<const char*>(begin);
    for (size_t i = 0; i < length; ++i) {
        char ch = 0;
        __try {
            ch = pText[i];
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            return false;
        }
        if (!IsPlausibleEffectNameChar(static_cast<unsigned char>(ch))) return false;
    }

    out.assign(pText, length);
    return true;
}

std::vector<std::string> ProbePrimaryCollectionHashNames(cISC4EffectsManager* pEffectsManager) noexcept {
    std::vector<std::string> names;
    if (!pEffectsManager) return names;

    auto* const pManager = reinterpret_cast<const uint8_t*>(pEffectsManager);
    auto* const pCollection = pManager + 0x98;

    uint32_t bucketsBegin = 0;
    uint32_t bucketsEnd = 0;
    if (!TryReadUint32(pCollection + 0x4, bucketsBegin)) return names;
    if (!TryReadUint32(pCollection + 0x8, bucketsEnd)) return names;
    if (bucketsBegin == 0 || bucketsEnd <= bucketsBegin) return names;

    const size_t bucketCount = (bucketsEnd - bucketsBegin) / sizeof(uint32_t);
    if (bucketCount == 0 || bucketCount > kMaxHashBucketCount) return names;
    if (!IsReadableRange(reinterpret_cast<const void*>(bucketsBegin), bucketCount * sizeof(uint32_t))) return names;

    for (size_t bucketIndex = 0; bucketIndex < bucketCount; ++bucketIndex) {
        uint32_t node = 0;
        if (!TryReadUint32(reinterpret_cast<const void*>(bucketsBegin + (bucketIndex * sizeof(uint32_t))), node)) continue;

        size_t chainDepth = 0;
        while (node && chainDepth < 8192) {
            uint32_t next = 0;
            uint32_t strBegin = 0;
            uint32_t strEnd = 0;
            if (!TryReadUint32(reinterpret_cast<const void*>(node), next)) break;
            if (!TryReadUint32(reinterpret_cast<const void*>(node + 4), strBegin)) break;
            if (!TryReadUint32(reinterpret_cast<const void*>(node + 8), strEnd)) break;

            std::string name;
            if (TryReadStringSpan(strBegin, strEnd, name) && pEffectsManager->HasVisualEffect(name.c_str())) {
                names.push_back(std::move(name));
            }

            node = next;
            ++chainDepth;
        }
    }

    std::sort(names.begin(), names.end());
    names.erase(std::unique(names.begin(), names.end()), names.end());
    return names;
}

bool TryReadMsvcString(const void* pAddress, std::string& out) noexcept {
    out.clear();
    MsvcStringLayout value{};
    if (!TryReadMsvcStringLayout(pAddress, value)) return false;
    if (value.length == 0 || value.length > 128) return false;

    const char* pText = nullptr;
    if (value.capacity <= 15) {
        pText = value.inlineBuffer;
    } else {
        if (!value.heapBuffer || !IsReadableRange(value.heapBuffer, value.length)) return false;
        pText = value.heapBuffer;
    }

    std::string candidate(pText, value.length);
    if (!LooksLikeEffectName(candidate)) return false;
    out = std::move(candidate);
    return true;
}

CatalogProbeResult ProbeKnownEffectsFromManager(cISC4EffectsManager* pEffectsManager) noexcept {
    CatalogProbeResult result{};
    if (!pEffectsManager) return result;

    auto names = ProbePrimaryCollectionHashNames(pEffectsManager);
    if (names.size() >= 8) {
        SC4EffectsExtensionsDirector::EffectsCatalogSource source{};
        source.label = "Primary collection object +0x98 (hash at +0x04)";
        source.vectorOffset = 0x9C;
        source.elementSize = 0x0C;
        source.stringOffset = 0x04;
        source.names = names;
        result.sources.push_back(source);
        result.names = std::move(names);
    }

    return result;
}

std::string DescribeDBSegment(cIGZPersistDBSegment* pSegment) {
    if (!pSegment) return "segment=null";
    cRZBaseString path;
    pSegment->GetPath(path);
    const char* pPath = path.ToChar();
    char buffer[512]{};
    std::snprintf(buffer, sizeof(buffer), "segment=0x%08X id=0x%08X open=%d path='%s'",
                  static_cast<uint32_t>(reinterpret_cast<uintptr_t>(pSegment)),
                  pSegment->GetSegmentID(),
                  pSegment->IsOpen() ? 1 : 0,
                  pPath ? pPath : "");
    return buffer;
}

void CallEffectsParserEnableResourceSaving(int parser) noexcept {
    if (!parser) return;
    const auto interfaceThis = reinterpret_cast<void*>(static_cast<uintptr_t>(parser) + kEffectsParserSaveEnableInterfaceOffset);
    auto** const vtable = interfaceThis ? *reinterpret_cast<void***>(interfaceThis) : nullptr;
    if (!vtable) return;
    const auto fn = reinterpret_cast<EffectsParserEnableResourceSavingFn>(vtable[kEffectsParserEnableResourceSavingVtableIndex]);
    if (!fn) return;
    fn(interfaceThis);
}

void __fastcall HookEffectsBootstrapLoad(void* const pThis, void* const) noexcept {
    auto* const pBootstrap = reinterpret_cast<uint8_t*>(pThis);
    void* const pFileParserInterface = *reinterpret_cast<void* const*>(pBootstrap + kEffectsBootstrapParserInterfaceOffset);
    void* const pParserInterface = *reinterpret_cast<void* const*>(pBootstrap + kEffectsBootstrapParserObjectOffset);
    if (pParserInterface) {
        const auto parser = static_cast<int>(reinterpret_cast<uintptr_t>(reinterpret_cast<uint8_t*>(pParserInterface) - kEffectsParserSaveEnableInterfaceOffset));
        EmitHookEvent("LoadAllEffects saveEnabled=" + std::to_string(static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset))));
        LOG_INFO("LoadAllEffects parserIfc=0x{:08X} vtbl=0x{:08X} parserObjIfc=0x{:08X} vtbl=0x{:08X}",
                 static_cast<uint32_t>(reinterpret_cast<uintptr_t>(pFileParserInterface)),
                 pFileParserInterface ? static_cast<uint32_t>(reinterpret_cast<uintptr_t>(*reinterpret_cast<void**>(pFileParserInterface))) : 0u,
                 static_cast<uint32_t>(reinterpret_cast<uintptr_t>(pParserInterface)),
                 static_cast<uint32_t>(reinterpret_cast<uintptr_t>(*reinterpret_cast<void**>(pParserInterface))));
    }
    g_inEffectsBootstrapLoad = true;
    if (g_originalEffectsBootstrapLoad) g_originalEffectsBootstrapLoad(pThis);
    g_inEffectsBootstrapLoad = false;
}

void __fastcall HookEffectsParseQueuedFiles(const int pThis, void* const) noexcept {
    void* pParserInterface = nullptr;
    void* pEffectsParserInterface = nullptr;
    if (g_inEffectsBootstrapLoad) {
        const auto* const pBootstrap = reinterpret_cast<const uint8_t*>(pThis);
        pParserInterface = *reinterpret_cast<void* const*>(pBootstrap + kEffectsBootstrapParserInterfaceOffset);
        pEffectsParserInterface = *reinterpret_cast<void* const*>(pBootstrap + kEffectsBootstrapParserObjectOffset);
        LOG_INFO("ParseQueuedFiles during bootstrap: manager=0x{:08X} parserIfc=0x{:08X}",
                 static_cast<uint32_t>(pThis),
                 static_cast<uint32_t>(reinterpret_cast<uintptr_t>(pParserInterface)));
        if (pEffectsParserInterface) {
            const auto parser = static_cast<int>(
                reinterpret_cast<uintptr_t>(reinterpret_cast<uint8_t*>(pEffectsParserInterface) - kEffectsParserSaveEnableInterfaceOffset));
            const auto before = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
            CallEffectsParserEnableResourceSaving(parser);
            const auto after = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
            EmitHookEvent("ParseQueuedFiles saveEnabled " + std::to_string(before) + " -> " + std::to_string(after));
        }
        QueueExtraPluginFxFilesOnParserInterface(pParserInterface);
    }
    if (g_originalEffectsParseQueuedFiles) {
        g_originalEffectsParseQueuedFiles(pThis, nullptr);
    }
    if (!pParserInterface) {
        const auto* const pBootstrap = reinterpret_cast<const uint8_t*>(pThis);
        pParserInterface = *reinterpret_cast<void* const*>(pBootstrap + kEffectsBootstrapParserInterfaceOffset);
    }
    LogFileParserErrorConsole(pParserInterface);
}

bool __cdecl HookFileExistsForEffectsBootstrap(int* const path) noexcept {
    const bool exists = g_originalFileExistsForEffectsBootstrap ? g_originalFileExistsForEffectsBootstrap(path) : false;
    if (exists) {
        return true;
    }

    if (!g_inEffectsBootstrapLoad || !g_loadPluginFxRecursively) {
        return false;
    }

    const auto files = EnumeratePluginFxFiles();
    if (files.empty()) {
        return false;
    }

    LOG_INFO("Forcing bootstrap file-exists branch because {} extra plugin .fx files were found", files.size());
    return true;
}

void* __fastcall HookEffectsParserCtor(void* const pThis, void* const, const int ctorArg) noexcept {
    void* result = pThis;
    if (g_originalEffectsParserCtor) result = g_originalEffectsParserCtor(pThis, ctorArg);
    if (result && ctorArg != 0) {
        const auto parser = static_cast<int>(reinterpret_cast<uintptr_t>(result));
        const auto before = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
        CallEffectsParserEnableResourceSaving(parser);
        const auto after = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
        EmitHookEvent("EffectsParser::Ctor saveEnabled " + std::to_string(before) + " -> " + std::to_string(after));
    }
    return result;
}

bool InstallEffectsResourceHooks() noexcept {
    const auto gameVersion = VersionDetection::GetInstance().GetGameVersion();
    if (gameVersion != kSupportedGameVersionForEffectsHooks) {
        LOG_WARN("Skipping legacy effects resource hooks: unsupported game version {}", gameVersion);
        return false;
    }

    const bool bootstrapLoadOk = InstallInlineHook(g_effectsBootstrapLoadHook);
    const bool parseQueuedFilesOk = InstallInlineHook(g_effectsParseQueuedFilesHook);
    const bool parserCtorOk = InstallInlineHook(g_effectsParserCtorHook);
    const bool fileExistsOk = InstallInlineHook(g_effectsFileExistsHook);

    if (bootstrapLoadOk) g_originalEffectsBootstrapLoad = reinterpret_cast<EffectsBootstrapLoadFn>(g_effectsBootstrapLoadHook.trampoline);
    if (parseQueuedFilesOk) g_originalEffectsParseQueuedFiles = reinterpret_cast<EffectsParseQueuedFilesFn>(g_effectsParseQueuedFilesHook.trampoline);
    if (parserCtorOk) g_originalEffectsParserCtor = reinterpret_cast<EffectsParserCtorFn>(g_effectsParserCtorHook.trampoline);
    if (fileExistsOk) g_originalFileExistsForEffectsBootstrap = reinterpret_cast<FileExistsFn>(g_effectsFileExistsHook.trampoline);

    if (!bootstrapLoadOk || !parserCtorOk) {
        UninstallInlineHook(g_effectsBootstrapLoadHook);
        if (parseQueuedFilesOk) {
            UninstallInlineHook(g_effectsParseQueuedFilesHook);
        }
        UninstallInlineHook(g_effectsParserCtorHook);
        if (fileExistsOk) {
            UninstallInlineHook(g_effectsFileExistsHook);
        }
        g_originalEffectsBootstrapLoad = nullptr;
        g_originalEffectsParseQueuedFiles = nullptr;
        g_originalEffectsParserCtor = nullptr;
        g_originalFileExistsForEffectsBootstrap = nullptr;
        return false;
    }

    if (!parseQueuedFilesOk) {
        LOG_WARN("Proceeding without ParseQueuedFiles hook; extra plugin .fx injection is disabled");
        g_originalEffectsParseQueuedFiles = nullptr;
    }
    if (!fileExistsOk) {
        LOG_WARN("Proceeding without bootstrap file-exists override; extra plugin .fx files may still require main.fx");
        g_originalFileExistsForEffectsBootstrap = nullptr;
    }

    return true;
}

void UninstallEffectsResourceHooks() noexcept {
    UninstallInlineHook(g_effectsBootstrapLoadHook);
    UninstallInlineHook(g_effectsParseQueuedFilesHook);
    UninstallInlineHook(g_effectsParserCtorHook);
    UninstallInlineHook(g_effectsFileExistsHook);
    g_originalEffectsBootstrapLoad = nullptr;
    g_originalEffectsParseQueuedFiles = nullptr;
    g_originalEffectsParserCtor = nullptr;
    g_originalFileExistsForEffectsBootstrap = nullptr;
}
}

SC4EffectsExtensionsDirector::SC4EffectsExtensionsDirector() = default;
SC4EffectsExtensionsDirector::~SC4EffectsExtensionsDirector() = default;

uint32_t SC4EffectsExtensionsDirector::GetDirectorID() const { return kDirectorId; }

bool SC4EffectsExtensionsDirector::OnStart(cIGZCOM* pCOM) {
    cRZMessage2COMDirector::OnStart(pCOM);
    if (auto* framework = RZGetFrameWork()) framework->AddHook(this);
    return true;
}

bool SC4EffectsExtensionsDirector::PreFrameWorkInit() { return true; }
bool SC4EffectsExtensionsDirector::PreAppInit() { return true; }

bool SC4EffectsExtensionsDirector::PostAppInit() {
    InitializeLogger_();
    const auto gameVersion = VersionDetection::GetInstance().GetGameVersion();
    LOG_INFO("PostAppInit");
    LOG_INFO("Detected game version: {}", gameVersion);

    effectsHookInstalled_ = InstallEffectsResourceHooks();
    PushEventLine_(
        effectsHookInstalled_ ? "effects hooks installed" : "failed to install effects hooks",
        effectsHookInstalled_ ? EventSeverity::Info : EventSeverity::Warning);

    cIGZMessageServer2Ptr pMS2;
    if (pMS2) {
        pMS2->AddNotification(this, kSC4MessagePostCityInit);
        pMS2->AddNotification(this, kSC4MessagePreCityShutdown);
        messageServer2_ = pMS2;
        messageServer2_->AddRef();
    }

    Settings settings;
    settings.Load(GetUserPluginsPath_() / "SC4EffectsExtensions.ini");
    g_loadPluginFxRecursively = settings.GetLoadPluginFxRecursively();
    g_pluginFxRoot = settings.GetPluginFxRoot();
    packedEffectsOutputPath_ = settings.GetPackedEffectsOutputPath();
    if (g_pluginFxRoot.empty()) {
        g_pluginFxRoot = GetGameUserPluginDirectory();
    }
    if (g_pluginFxRoot.empty()) {
        g_pluginFxRoot = GetUserPluginsPath_();
    }
    if (packedEffectsOutputPath_.empty()) {
        packedEffectsOutputPath_ = GetDefaultPackedEffectsOutputPath();
    }
    LOG_INFO("Plugin .fx recursive loading: enabled={} root='{}'", g_loadPluginFxRecursively, g_pluginFxRoot.string());
    LOG_INFO("Packed effects output path: '{}'", packedEffectsOutputPath_.string());

    if (!packedEffectsOutputPath_.empty()) {
        if (EnsurePackedEffectsSaveSegment_()) {
            PushEventLine_("packed effects DB segment registered");
        } else {
            PushEventLine_("failed to register packed effects DB segment", EventSeverity::Warning);
        }
    }

    if (mpFrameWork && mpFrameWork->GetSystemService(kImGuiServiceID, GZIID_cIGZImGuiService, reinterpret_cast<void**>(&imguiService_))) {
        panel_ = std::make_unique<EffectsPanel>(*this);
        panel_->SetDetectedGameVersion(gameVersion);
        panel_->SetVersionLabel(SC4_TEMPLATE_DLL_VERSION_LABEL);
        panel_->SetVisible(settings.GetStartWindowVisible());
        const ImGuiPanelDesc desc = ImGuiPanelAdapter<EffectsPanel>::MakeDesc(panel_.get(), kPanelId, 100, settings.GetStartWindowVisible());
        if (imguiService_->RegisterPanel(desc)) panelRegistered_ = true;
    }

    g_activeDirector = this;
    return true;
}

bool SC4EffectsExtensionsDirector::PreAppShutdown() { return true; }

bool SC4EffectsExtensionsDirector::PostAppShutdown() {
    g_activeDirector = nullptr;
    PreCityShutdown_();
    ReleasePackedEffectsSaveSegment_();
    if (messageServer2_) {
        messageServer2_->RemoveNotification(this, kSC4MessagePostCityInit);
        messageServer2_->RemoveNotification(this, kSC4MessagePreCityShutdown);
        messageServer2_->Release();
        messageServer2_ = nullptr;
    }
    if (imguiService_ && panelRegistered_) {
        imguiService_->UnregisterPanel(kPanelId);
        panelRegistered_ = false;
    }
    panel_.reset();
    if (imguiService_) {
        imguiService_->Release();
        imguiService_ = nullptr;
    }
    if (auto* framework = RZGetFrameWork()) framework->RemoveHook(this);
    UninstallEffectsResourceHooks();
    effectsHookInstalled_ = false;
    Logger::Shutdown();
    return true;
}

bool SC4EffectsExtensionsDirector::PostSystemServiceShutdown() { return true; }
bool SC4EffectsExtensionsDirector::AbortiveQuit() { return true; }
bool SC4EffectsExtensionsDirector::OnInstall() { return true; }

bool SC4EffectsExtensionsDirector::DoMessage(cIGZMessage2* pMsg) {
    const auto* pStandardMsg = static_cast<cIGZMessage2Standard*>(pMsg);
    switch (pStandardMsg->GetType()) {
    case kSC4MessagePostCityInit:
        PostCityInit_(pStandardMsg);
        break;
    case kSC4MessagePreCityShutdown:
        PreCityShutdown_();
        break;
    default:
        break;
    }
    return true;
}

bool SC4EffectsExtensionsDirector::IsCityLoaded() const {
    return city_ != nullptr && effectsManager_ != nullptr;
}

bool SC4EffectsExtensionsDirector::IsEffectsHookInstalled() const {
    return effectsHookInstalled_;
}

size_t SC4EffectsExtensionsDirector::GetRecentEventCount() const {
    std::scoped_lock lock(effectsMutex_);
    return recentEvents_.size();
}

size_t SC4EffectsExtensionsDirector::GetKnownEffectCount() const {
    std::scoped_lock lock(effectsMutex_);
    return knownEffects_.size();
}

std::vector<SC4EffectsExtensionsDirector::RecentEvent> SC4EffectsExtensionsDirector::GetRecentEventsSnapshot() const {
    std::scoped_lock lock(effectsMutex_);
    return {recentEvents_.begin(), recentEvents_.end()};
}

std::vector<std::string> SC4EffectsExtensionsDirector::GetKnownEffectsSnapshot() const {
    std::scoped_lock lock(effectsMutex_);
    return knownEffects_;
}

std::vector<SC4EffectsExtensionsDirector::EffectsCatalogSource> SC4EffectsExtensionsDirector::GetCatalogSourcesSnapshot() const {
    std::scoped_lock lock(effectsMutex_);
    return catalogSources_;
}

std::string SC4EffectsExtensionsDirector::GetEffectsStatsString() const {
    if (!effectsManager_) return {};
    cRZBaseString stats;
    effectsManager_->GetStatsString(stats);
    const char* pText = stats.ToChar();
    return pText ? pText : "";
}

std::string SC4EffectsExtensionsDirector::GetLastSpawnStatus() const {
    std::scoped_lock lock(effectsMutex_);
    return lastSpawnStatus_;
}

SC4EffectsExtensionsDirector::TrackedEffectState SC4EffectsExtensionsDirector::GetTrackedEffectState() const {
    std::scoped_lock lock(effectsMutex_);
    return trackedEffectState_;
}

void SC4EffectsExtensionsDirector::ClearRecentEvents() {
    std::scoped_lock lock(effectsMutex_);
    recentEvents_.clear();
}

bool SC4EffectsExtensionsDirector::SpawnEffectByName(const char* effectName) {
    const std::string requestedName = effectName ? effectName : "";
    if (!effectsManager_) {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "No city/effects manager is active.";
        return false;
    }
    if (requestedName.empty()) {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "Enter an effect name first.";
        return false;
    }

    cISC4VisualEffect* pEffect = nullptr;
    const bool created = effectsManager_->CreateVisualEffect(requestedName.c_str(), &pEffect);
    if (!created || !pEffect) {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "CreateVisualEffect failed for '" + requestedName + "'.";
        return false;
    }

    pEffect->Start(cISC4VisualEffect::tTransitionType::Unknown1);
    pEffect->Release();

    {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "Spawned '" + requestedName + "' with default transition.";
    }
    PushEventLine_("manual spawn: " + requestedName);
    return true;
}

bool SC4EffectsExtensionsDirector::SpawnTrackedEffectByName(const char* effectName, const TrackedEffectState& state) {
    const std::string requestedName = effectName ? effectName : "";
    if (!effectsManager_) {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "No city/effects manager is active.";
        return false;
    }
    if (requestedName.empty()) {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "Enter an effect name first.";
        return false;
    }

    StopTrackedEffect();

    cISC4VisualEffect* pEffect = nullptr;
    const bool created = effectsManager_->CreateVisualEffect(requestedName.c_str(), &pEffect);
    if (!created || !pEffect) {
        std::scoped_lock lock(effectsMutex_);
        lastSpawnStatus_ = "CreateVisualEffect failed for '" + requestedName + "'.";
        return false;
    }

    TrackedEffectState nextState = state;
    nextState.active = true;
    nextState.name = requestedName;
    nextState.dirty = false;

    cS3DTransform transform{};
    pEffect->GetEffectTransform(transform);
    ApplyTrackedTransformState(transform, nextState);
    pEffect->SetEffectTransform(transform);
    pEffect->Start(cISC4VisualEffect::tTransitionType::Unknown1);

    {
        std::scoped_lock lock(effectsMutex_);
        trackedEffect_ = pEffect;
        trackedEffectState_ = nextState;
        lastSpawnStatus_ = "Spawned tracked '" + requestedName + "'.";
    }

    PushEventLine_("tracked spawn: " + requestedName);
    return true;
}

bool SC4EffectsExtensionsDirector::UpdateTrackedEffectTransform(const TrackedEffectState& state) {
    cISC4VisualEffect* pTrackedEffect = nullptr;
    TrackedEffectState nextState = state;
    {
        std::scoped_lock lock(effectsMutex_);
        pTrackedEffect = trackedEffect_;
        if (!pTrackedEffect) {
            lastSpawnStatus_ = "No tracked effect is active.";
            trackedEffectState_.active = false;
            return false;
        }
        nextState.active = true;
        nextState.name = trackedEffectState_.name;
    }

    cS3DTransform transform{};
    pTrackedEffect->GetEffectTransform(transform);
    ApplyTrackedTransformState(transform, nextState);
    pTrackedEffect->SetEffectTransform(transform);

    {
        std::scoped_lock lock(effectsMutex_);
        trackedEffectState_ = nextState;
        trackedEffectState_.dirty = false;
        lastSpawnStatus_ = "Updated tracked transform for '" + trackedEffectState_.name + "'.";
    }
    return true;
}

void SC4EffectsExtensionsDirector::StopTrackedEffect() {
    cISC4VisualEffect* pTrackedEffect = nullptr;
    std::string effectName;
    {
        std::scoped_lock lock(effectsMutex_);
        pTrackedEffect = trackedEffect_;
        if (!pTrackedEffect) {
            trackedEffectState_ = TrackedEffectState{};
            return;
        }
        trackedEffect_ = nullptr;
        effectName = trackedEffectState_.name;
        trackedEffectState_ = TrackedEffectState{};
        lastSpawnStatus_ = effectName.empty() ? "Stopped tracked effect." : "Stopped tracked '" + effectName + "'.";
    }

    pTrackedEffect->Stop(cISC4VisualEffect::tTransitionType::Unknown1);
    pTrackedEffect->Release();

    if (!effectName.empty()) {
        PushEventLine_("tracked stop: " + effectName);
    }
}

void SC4EffectsExtensionsDirector::RecordHookEvent(std::string_view line) {
    PushEventLine_(std::string(line));
}

void SC4EffectsExtensionsDirector::RecordConsoleEvent(const EventSeverity severity, std::string_view line) {
    PushEventLine_(std::string(line), severity);
}

bool SC4EffectsExtensionsDirector::RefreshKnownEffects() {
    return RefreshKnownEffects_();
}

bool SC4EffectsExtensionsDirector::DumpManagerMemory() {
    if (!effectsManager_) {
        LOG_INFO("manager dump: no active effects manager");
        PushEventLine_("manager dump: no active effects manager", EventSeverity::Warning);
        return false;
    }

    auto* const pManager = reinterpret_cast<const uint8_t*>(effectsManager_);
    auto* const pCollection = pManager + 0x98;
    uint32_t parserInterfaceValue = 0;
    uint32_t parserObjectValue = 0;
    uint32_t parserBaseValue = 0;
    uint32_t parserInterfaceVtable = 0;
    uint32_t parserObjectVtable = 0;
    std::vector<std::string> lines;
    lines.reserve(48);

    char header[160]{};
    std::snprintf(
        header,
        sizeof(header),
        "manager dump: manager=%p collection(+0x98)=%p parserIfc(+0xC78)=%p parserIface(+0xC7C)=%p; full dump is also in SC4EffectsExtensions.log",
        static_cast<const void*>(pManager),
        static_cast<const void*>(pCollection),
        static_cast<const void*>(pManager + kEffectsBootstrapParserInterfaceOffset),
        static_cast<const void*>(pManager + kEffectsBootstrapParserObjectOffset));
    lines.emplace_back(header);

    uint32_t value = 0;
    if (TryReadUint32(pManager + 0x98, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "manager +0x098 dword = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x4, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x004 mpStart = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x8, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x008 mpEnd   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0xC, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x00C reserved= %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x10, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x010 size?   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x14, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x014 field   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x18, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x018 field   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x1C, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x01C field   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x20, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x020 field   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x24, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x024 field   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pCollection + 0x28, value)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "collection +0x028 field   = %08X", value);
        lines.emplace_back(line);
    }
    if (TryReadUint32(pManager + kEffectsBootstrapParserInterfaceOffset, parserInterfaceValue)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "manager +0x%03X parserIfc = %08X", static_cast<unsigned>(kEffectsBootstrapParserInterfaceOffset), parserInterfaceValue);
        lines.emplace_back(line);
        if (parserInterfaceValue != 0 &&
            TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(parserInterfaceValue)), parserInterfaceVtable))
        {
            std::snprintf(line, sizeof(line), "parserIfc vtable        = %08X", parserInterfaceVtable);
            lines.emplace_back(line);
        }
    }
    if (TryReadUint32(pManager + kEffectsBootstrapParserObjectOffset, parserObjectValue)) {
        char line[160]{};
        std::snprintf(line, sizeof(line), "manager +0x%03X parserIface = %08X", static_cast<unsigned>(kEffectsBootstrapParserObjectOffset), parserObjectValue);
        lines.emplace_back(line);
        if (parserObjectValue != 0 &&
            TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(parserObjectValue)), parserObjectVtable))
        {
            std::snprintf(line, sizeof(line), "parserObj vtable        = %08X", parserObjectVtable);
            lines.emplace_back(line);
        }
        if (parserObjectValue != 0) {
            parserBaseValue = static_cast<uint32_t>(parserObjectValue - kEffectsParserSaveEnableInterfaceOffset);
            std::snprintf(line, sizeof(line), "parser base            = %08X", parserBaseValue);
            lines.emplace_back(line);

            if (TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(parserBaseValue) + kEffectsParserResourcePtrOffset), value)) {
                std::snprintf(line, sizeof(line), "parserObj +0x%03X resourcePtr = %08X", static_cast<unsigned>(kEffectsParserResourcePtrOffset), value);
                lines.emplace_back(line);
            }
            if (TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(parserBaseValue) + kEffectsParserPackedKeyTypeOffset), value)) {
                std::snprintf(line, sizeof(line), "parserObj +0x%03X packedType  = %08X", static_cast<unsigned>(kEffectsParserPackedKeyTypeOffset), value);
                lines.emplace_back(line);
            }
            if (TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(parserBaseValue) + kEffectsParserPackedKeyGroupOffset), value)) {
                std::snprintf(line, sizeof(line), "parserObj +0x%03X packedGroup = %08X", static_cast<unsigned>(kEffectsParserPackedKeyGroupOffset), value);
                lines.emplace_back(line);
            }
            if (TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(parserBaseValue) + kEffectsParserPackedKeyInstanceOffset), value)) {
                std::snprintf(line, sizeof(line), "parserObj +0x%03X packedInst  = %08X", static_cast<unsigned>(kEffectsParserPackedKeyInstanceOffset), value);
                lines.emplace_back(line);
            }
            char saveEnabledLine[160]{};
            std::snprintf(
                saveEnabledLine,
                sizeof(saveEnabledLine),
                "parserObj +0x%03X saveEnabled = %02X",
                static_cast<unsigned>(kEffectsParserResourceSaveEnabledOffset),
                ReadParserByte(static_cast<int>(parserBaseValue), kEffectsParserResourceSaveEnabledOffset));
            lines.emplace_back(saveEnabledLine);
        }
    }

    for (size_t offset = 0; offset < 0x40; offset += 0x10) {
        AppendHexBytesLine(lines, "manager", pManager, offset, 0x10);
    }
    for (size_t offset = 0x80; offset < 0xC0; offset += 0x10) {
        AppendHexBytesLine(lines, "manager", pManager, offset, 0x10);
    }
    for (size_t offset = 0xC70; offset < 0xC90; offset += 0x10) {
        AppendHexBytesLine(lines, "manager", pManager, offset, 0x10);
    }
    for (size_t offset = 0; offset < 0x30; offset += 0x10) {
        AppendHexBytesLine(lines, "collection", pCollection, offset, 0x10);
    }
    if (parserInterfaceValue != 0) {
        const auto* const pParserInterface = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(parserInterfaceValue));
        for (size_t offset = 0; offset < 0x30; offset += 0x10) {
            AppendHexBytesLine(lines, "parserIfc", pParserInterface, offset, 0x10);
        }
        if (parserInterfaceVtable != 0) {
            const auto* const pParserInterfaceVtable = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(parserInterfaceVtable));
            for (size_t offset = 0; offset < 0x30; offset += 0x10) {
                AppendHexBytesLine(lines, "parserIfcVtbl", pParserInterfaceVtable, offset, 0x10);
            }
        }
    }
    if (parserObjectValue != 0) {
        const auto* const pParserObject = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(parserObjectValue));
        for (size_t offset = 0; offset < 0x30; offset += 0x10) {
            AppendHexBytesLine(lines, "parserObj", pParserObject, offset, 0x10);
        }
        if (parserObjectVtable != 0) {
            const auto* const pParserObjectVtable = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(parserObjectVtable));
            for (size_t offset = 0; offset < 0x30; offset += 0x10) {
                AppendHexBytesLine(lines, "parserObjVtbl", pParserObjectVtable, offset, 0x10);
            }
        }
    }
    if (parserBaseValue != 0) {
        const auto* const pParserBase = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(parserBaseValue));
        for (size_t offset = 0x90; offset < 0xB0; offset += 0x10) {
            AppendHexBytesLine(lines, "parserBase", pParserBase, offset, 0x10);
        }
    }

    uint32_t bucketsBegin = 0;
    uint32_t bucketsEnd = 0;
    if (TryReadUint32(pCollection + 0x4, bucketsBegin) &&
        TryReadUint32(pCollection + 0x8, bucketsEnd) &&
        bucketsBegin != 0 &&
        bucketsEnd > bucketsBegin)
    {
        const auto* const pBuckets = reinterpret_cast<const uint8_t*>(static_cast<uintptr_t>(bucketsBegin));
        char bucketLine[160]{};
        std::snprintf(
            bucketLine,
            sizeof(bucketLine),
            "buckets: begin=%08X end=%08X count=%zu",
            bucketsBegin,
            bucketsEnd,
            static_cast<size_t>(bucketsEnd - bucketsBegin) / sizeof(uint32_t));
        lines.emplace_back(bucketLine);

        for (size_t offset = 0; offset < 0x20; offset += 0x10) {
            AppendHexBytesLine(lines, "buckets", pBuckets, offset, 0x10);
        }

        size_t nonEmptyBucketCount = 0;
        for (size_t bucketIndex = 0; bucketIndex < 64 && nonEmptyBucketCount < 6; ++bucketIndex) {
            uint32_t node = 0;
            const auto bucketAddress = static_cast<uintptr_t>(bucketsBegin) + (bucketIndex * sizeof(uint32_t));
            if (!TryReadUint32(reinterpret_cast<const void*>(bucketAddress), node) || node == 0) {
                continue;
            }

            ++nonEmptyBucketCount;

            char bucketNodeLine[160]{};
            std::snprintf(
                bucketNodeLine,
                sizeof(bucketNodeLine),
                "bucket[%zu] head=%08X",
                bucketIndex,
                node);
            lines.emplace_back(bucketNodeLine);

            uint32_t current = node;
            for (size_t chainIndex = 0; chainIndex < 3 && current != 0; ++chainIndex) {
                AppendNodeDump(lines, current, bucketIndex, chainIndex);

                uint32_t field4 = 0;
                uint32_t field8 = 0;
                uint32_t fieldC = 0;
                uint32_t field10 = 0;
                if (TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(current) + 0x4), field4) &&
                    TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(current) + 0x8), field8) &&
                    TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(current) + 0xC), fieldC) &&
                    TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(current) + 0x10), field10))
                {
                    char nodeFields[192]{};
                    std::snprintf(
                        nodeFields,
                        sizeof(nodeFields),
                        "node fields: a=%08X b=%08X c=%08X id=%08X",
                        field4,
                        field8,
                        fieldC,
                        field10);
                    lines.emplace_back(nodeFields);

                    std::string spanText;
                    if (TryReadStringSpan(field4, field8, spanText)) {
                        lines.emplace_back("node span[a,b]: " + spanText);
                    }
                    if (TryReadStringSpan(field8, fieldC, spanText)) {
                        lines.emplace_back("node span[b,c]: " + spanText);
                    }

                    std::string pointedText;
                    if (TryReadCStringPointer(reinterpret_cast<const void*>(static_cast<uintptr_t>(current) + 0x14), 64, pointedText)) {
                        lines.emplace_back("node cstr[+0x14]: " + pointedText);
                    }
                }

                uint32_t next = 0;
                if (!TryReadUint32(reinterpret_cast<const void*>(static_cast<uintptr_t>(current)), next)) {
                    break;
                }
                current = next;
            }
        }

        if (nonEmptyBucketCount == 0) {
            lines.emplace_back("bucket scan: first 64 buckets are empty");
        }
    }

    for (std::string& line : lines) {
        LOG_INFO(line);
        PushEventLine_(std::move(line));
    }
    return true;
}

void SC4EffectsExtensionsDirector::PostCityInit_(const cIGZMessage2Standard* pStandardMsg) {
    PreCityShutdown_();
    city_ = static_cast<cISC4City*>(pStandardMsg->GetVoid1());
    if (!city_) return;
    city_->AddRef();
    effectsManager_ = city_->GetEffectsManager();
    if (!effectsManager_) return;
    effectsManager_->AddRef();
    PushEventLine_("city init: acquired effects manager");
    RefreshKnownEffects_();
}

void SC4EffectsExtensionsDirector::PreCityShutdown_() {
    StopTrackedEffect();
    {
        std::scoped_lock lock(effectsMutex_);
        knownEffects_.clear();
        catalogSources_.clear();
    }
    if (effectsManager_) {
        effectsManager_->Release();
        effectsManager_ = nullptr;
    }
    if (city_) {
        city_->Release();
        city_ = nullptr;
    }
}

std::filesystem::path SC4EffectsExtensionsDirector::GetUserPluginsPath_() {
    auto pluginsPath = GetGameUserPluginDirectory();
    if (!pluginsPath.empty()) {
        return pluginsPath;
    }

    try {
        const auto modulePath = wil::GetModuleFileNameW(wil::GetModuleInstanceHandle());
        return std::filesystem::path(modulePath.get()).parent_path();
    } catch (const wil::ResultException&) {
        return {};
    }
}

void SC4EffectsExtensionsDirector::InitializeLogger_() {
    const auto pluginsPath = GetUserPluginsPath_();
    const auto logPath = pluginsPath.parent_path();
    const auto settingsPath = pluginsPath / "SC4EffectsExtensions.ini";

    Logger::Initialize("SC4EffectsExtensions", logPath.string(), false);
    Settings settings;
    settings.Load(settingsPath);
    Logger::Shutdown();
    Logger::Initialize("SC4EffectsExtensions", logPath.string(), settings.GetLogToFile());
    Logger::SetLevel(settings.GetLogLevel());
    LOG_INFO("Using settings file: {}", settingsPath.string());
}

void SC4EffectsExtensionsDirector::PushEventLine_(std::string line, const EventSeverity severity) {
    constexpr size_t kMaxRecentEvents = 96;
    std::scoped_lock lock(effectsMutex_);
    recentEvents_.push_front(RecentEvent{severity, std::move(line)});
    while (recentEvents_.size() > kMaxRecentEvents) {
        recentEvents_.pop_back();
    }
}

void SC4EffectsExtensionsDirector::DumpKnownEffectsToLog_(
    const std::vector<std::string>& names,
    const std::vector<EffectsCatalogSource>& sources) const
{
    LOG_INFO("effects catalog dump begin: {} merged effects from {} sources", names.size(), sources.size());
    for (const auto& source : sources) {
        LOG_INFO(
            "effects catalog source: label=\"{}\" count={} offset=0x{:X} elem=0x{:X} string=0x{:X}",
            source.label,
            source.names.size(),
            static_cast<unsigned int>(source.vectorOffset),
            static_cast<unsigned int>(source.elementSize),
            static_cast<unsigned int>(source.stringOffset));
    }
    for (const std::string& name : names) {
        LOG_INFO("effects catalog entry: {}", name);
    }
    LOG_INFO("effects catalog dump end");
}

bool SC4EffectsExtensionsDirector::RefreshKnownEffects_() {
    if (!effectsManager_) return false;
    if (VersionDetection::GetInstance().GetGameVersion() != kSupportedGameVersionForCatalogProbe) return false;

    const CatalogProbeResult probe = ProbeKnownEffectsFromManager(effectsManager_);
    if (probe.names.empty()) {
        PushEventLine_("catalog probe: no validated effect list found", EventSeverity::Warning);
        return false;
    }

    {
        std::scoped_lock lock(effectsMutex_);
        knownEffects_ = probe.names;
        catalogSources_ = probe.sources;
    }

    char buffer[160]{};
    std::snprintf(
        buffer,
        sizeof(buffer),
        "catalog probe: %zu effects from %zu validated tables",
        probe.names.size(),
        probe.sources.size());
    DumpKnownEffectsToLog_(probe.names, probe.sources);
    PushEventLine_(buffer);
    return true;
}

bool SC4EffectsExtensionsDirector::EnsurePackedEffectsSaveSegment_() {
    if (packedEffectsSegmentRegistered_ && packedEffectsSegment_) {
        return true;
    }
    if (packedEffectsOutputPath_.empty()) {
        LOG_WARN("Packed effects DB segment setup skipped: output path is empty");
        return false;
    }

    cIGZPersistResourceManagerPtr pRM;
    if (!pRM) {
        LOG_WARN("Packed effects DB segment setup skipped: persist resource manager unavailable");
        return false;
    }

    cIGZPersistDBSegment* existingSegment = nullptr;
    if (pRM->FindDBSegment(kPackedEffectsResourceGroup, &existingSegment) && existingSegment) {
        const uint32_t existingSegmentId = existingSegment->GetSegmentID();
        existingSegment->Release();
        if (existingSegmentId == kPackedEffectsResourceGroup) {
            packedEffectsSegmentRegistered_ = true;
            LOG_INFO("Packed effects DB segment already registered for id=0x{:08X}", kPackedEffectsResourceGroup);
            return true;
        }
    }

    if (!packedEffectsSegment_) {
        cIGZCOM* const pCOM = GZCOM();
        if (!pCOM) {
            LOG_WARN("Packed effects DB segment setup failed: GZCOM unavailable");
            return false;
        }

        void* pObject = nullptr;
        if (!pCOM->GetClassObject(
                GZCLSID_cGZDBSegmentPackedFile,
                GZIID_cIGZDBSegmentPackedFile,
                &pObject) ||
            !pObject)
        {
            LOG_WARN("Packed effects DB segment setup failed: could not create packed-file segment object");
            return false;
        }

        packedEffectsSegment_ = static_cast<cIGZDBSegmentPackedFile*>(pObject);
        if (!packedEffectsSegment_->Init()) {
            LOG_WARN("Packed effects DB segment setup failed: packed-file Init() failed");
            packedEffectsSegment_->Release();
            packedEffectsSegment_ = nullptr;
            return false;
        }
    }

    cIGZPersistDBSegment* const pSegment = packedEffectsSegment_->AsIGZPersistDBSegment();
    if (!pSegment) {
        LOG_WARN("Packed effects DB segment setup failed: no persist segment interface");
        ReleasePackedEffectsSaveSegment_();
        return false;
    }

    std::error_code ec;
    const auto parentPath = packedEffectsOutputPath_.parent_path();
    if (!parentPath.empty()) {
        std::filesystem::create_directories(parentPath, ec);
    }
    const bool outputExists = std::filesystem::exists(packedEffectsOutputPath_, ec);

    const cRZBaseString outputPathString(packedEffectsOutputPath_.string());
    LOG_INFO(
        "Packed effects DB segment setup: path='{}' exists={}",
        packedEffectsOutputPath_.string(),
        outputExists);

    if (!packedEffectsSegment_->SetPath(outputPathString)) {
        LOG_WARN(
            "Packed effects DB segment setup failed: SetPath failed for '{}'",
            packedEffectsOutputPath_.string());
        ReleasePackedEffectsSaveSegment_();
        return false;
    }
    if (!pSegment->SetSegmentID(kPackedEffectsResourceGroup)) {
        LOG_WARN(
            "Packed effects DB segment setup failed: SetSegmentID(0x{:08X}) failed",
            kPackedEffectsResourceGroup);
        ReleasePackedEffectsSaveSegment_();
        return false;
    }
    if (!pSegment->Open(true, true)) {
        LOG_WARN(
            "Packed effects DB segment setup failed: Open(read=true, write=true) failed for '{}'",
            packedEffectsOutputPath_.string());
        ReleasePackedEffectsSaveSegment_();
        return false;
    }
    if (!pRM->RegisterDBSegmentBack(*pSegment)) {
        LOG_WARN(
            "Packed effects DB segment setup failed: RegisterDBSegmentBack failed for '{}'",
            packedEffectsOutputPath_.string());
        ReleasePackedEffectsSaveSegment_();
        return false;
    }

    packedEffectsSegmentRegistered_ = true;
    LOG_INFO(
        "Registered packed effects DB segment id=0x{:08X} path='{}'",
        kPackedEffectsResourceGroup,
        packedEffectsOutputPath_.string());
    return true;
}

void SC4EffectsExtensionsDirector::ReleasePackedEffectsSaveSegment_() noexcept {
    cIGZPersistDBSegment* const pSegment = packedEffectsSegment_ ? packedEffectsSegment_->AsIGZPersistDBSegment() : nullptr;

    if (packedEffectsSegmentRegistered_ && pSegment) {
        cIGZPersistResourceManagerPtr pRM;
        if (pRM) {
            pRM->UnregisterDBSegment(*pSegment);
        }
        packedEffectsSegmentRegistered_ = false;
    }

    if (pSegment && pSegment->IsOpen()) {
        pSegment->Flush();
        pSegment->Close();
    }

    if (packedEffectsSegment_) {
        packedEffectsSegment_->Shutdown();
        packedEffectsSegment_->Release();
        packedEffectsSegment_ = nullptr;
    }
}
