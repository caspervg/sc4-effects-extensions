#include "EffectsBootstrapHooks.hpp"

#include <array>
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

#include "cISC4App.h"
#include "cIGZFileSystem.h"
#include "cRZBaseString.h"
#include "utils/Logger.h"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <Windows.h>

namespace {
constexpr uint16_t kSupportedGameVersionForEffectsHooks = 641;
constexpr size_t kInlineHookJumpByteCount = 5;
constexpr size_t kInlineHookMaxPrologueBytes = 12;
constexpr uintptr_t kEffectsBootstrapLoadRva = 0x001945B0;
constexpr uintptr_t kEffectsParseQueuedFilesRva = 0x0018E4E0;
constexpr uintptr_t kEffectsParserCtorRva = 0x0019EEC0;
constexpr ptrdiff_t kEffectsParserResourceSaveEnabledOffset = 0xA4;
constexpr ptrdiff_t kEffectsParserSaveEnableInterfaceOffset = 0x4EC;
constexpr ptrdiff_t kEffectsBootstrapParserInterfaceOffset = 0xC78;
constexpr ptrdiff_t kEffectsBootstrapParserObjectOffset = 0xC7C;
constexpr size_t kEffectsParserEnableResourceSavingVtableIndex = 1;

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

uintptr_t ResolvePatchAddress(uintptr_t address) noexcept
{
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

bool InstallInlineHook(InlineHook& hook) noexcept
{
    if (hook.installed) return true;

    const auto moduleBase = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    if (!moduleBase) return false;

    hook.patchAddress = ResolvePatchAddress(moduleBase + hook.rva);
    auto* target = reinterpret_cast<uint8_t*>(hook.patchAddress);
    if (!target) return false;
    if (std::memcmp(target, hook.expected.data(), hook.byteCount) != 0) return false;

    std::memcpy(hook.original.data(), target, hook.byteCount);
    auto* trampoline = static_cast<uint8_t*>(
        VirtualAlloc(nullptr, hook.byteCount + kInlineHookJumpByteCount, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE));
    if (!trampoline) return false;

    std::memcpy(trampoline, target, hook.byteCount);
    trampoline[hook.byteCount] = 0xE9;
    const auto trampRel = static_cast<int32_t>(
        reinterpret_cast<intptr_t>(target + hook.byteCount) -
        (reinterpret_cast<intptr_t>(trampoline + hook.byteCount) + kInlineHookJumpByteCount));
    std::memcpy(trampoline + hook.byteCount + 1, &trampRel, sizeof(trampRel));

    DWORD oldProtect = 0;
    if (!VirtualProtect(target, hook.byteCount, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        VirtualFree(trampoline, 0, MEM_RELEASE);
        return false;
    }

    target[0] = 0xE9;
    const auto hookRel = static_cast<int32_t>(
        reinterpret_cast<intptr_t>(hook.hookFn) -
        (reinterpret_cast<intptr_t>(target) + kInlineHookJumpByteCount));
    std::memcpy(target + 1, &hookRel, sizeof(hookRel));
    for (size_t i = kInlineHookJumpByteCount; i < hook.byteCount; ++i) {
        target[i] = 0x90;
    }

    FlushInstructionCache(GetCurrentProcess(), target, hook.byteCount);
    DWORD restoredProtect = 0;
    VirtualProtect(target, hook.byteCount, oldProtect, &restoredProtect);

    hook.trampoline = trampoline;
    hook.installed = true;
    return true;
}

void UninstallInlineHook(InlineHook& hook) noexcept
{
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

    if (hook.trampoline) {
        VirtualFree(hook.trampoline, 0, MEM_RELEASE);
    }

    hook.trampoline = nullptr;
    hook.patchAddress = 0;
    hook.installed = false;
}

uint8_t ReadParserByte(const int parser, const ptrdiff_t offset) noexcept
{
    return parser ? *reinterpret_cast<const uint8_t*>(parser + offset) : 0;
}

bool HasFxExtension(const std::filesystem::path& path)
{
    const auto extension = path.extension().string();
    if (extension.size() != 3) return false;
    return std::tolower(static_cast<unsigned char>(extension[0])) == '.' &&
           std::tolower(static_cast<unsigned char>(extension[1])) == 'f' &&
           std::tolower(static_cast<unsigned char>(extension[2])) == 'x';
}
}

class EffectsBootstrapHooks::Impl
{
public:
    explicit Impl(Callbacks callbacks)
        : callbacks(std::move(callbacks))
        , bootstrapLoadHook{"EffectsBootstrap::LoadAllEffects", kEffectsBootstrapLoadRva, 9, {0x83, 0xEC, 0x64, 0x53, 0x55, 0x56, 0x57, 0x8B, 0xE9, 0x00, 0x00, 0x00}, reinterpret_cast<void*>(&HookEffectsBootstrapLoad)}
        , parseQueuedFilesHook{"EffectsParser::ParseQueuedFiles", kEffectsParseQueuedFilesRva, 9, {0x56, 0x8B, 0xF1, 0x8B, 0x8E, 0x78, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00}, reinterpret_cast<void*>(&HookEffectsParseQueuedFiles)}
        , parserCtorHook{"EffectsParser::Ctor", kEffectsParserCtorRva, 8, {0x8B, 0x44, 0x24, 0x04, 0x53, 0x56, 0x33, 0xDB}, reinterpret_cast<void*>(&HookEffectsParserCtor)}
        , fileExistsHook{"EffectsBootstrap::FileExists", 0x00519E96, 6, {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, reinterpret_cast<void*>(&HookFileExistsForEffectsBootstrap)}
    {
    }

    void ConfigureRecursiveLoading(const bool enabled, std::filesystem::path root)
    {
        loadPluginFxRecursively = enabled;
        pluginFxRoot = std::move(root);
    }

    bool Install(const uint16_t gameVersion) noexcept
    {
        if (gameVersion != kSupportedGameVersionForEffectsHooks) {
            LOG_WARN("Skipping legacy effects resource hooks: unsupported game version {}", gameVersion);
            return false;
        }

        g_activeImpl = this;

        const bool bootstrapLoadOk = InstallInlineHook(bootstrapLoadHook);
        const bool parseQueuedFilesOk = InstallInlineHook(parseQueuedFilesHook);
        const bool parserCtorOk = InstallInlineHook(parserCtorHook);
        const bool fileExistsOk = InstallInlineHook(fileExistsHook);

        if (bootstrapLoadOk) originalEffectsBootstrapLoad = reinterpret_cast<EffectsBootstrapLoadFn>(bootstrapLoadHook.trampoline);
        if (parseQueuedFilesOk) originalEffectsParseQueuedFiles = reinterpret_cast<EffectsParseQueuedFilesFn>(parseQueuedFilesHook.trampoline);
        if (parserCtorOk) originalEffectsParserCtor = reinterpret_cast<EffectsParserCtorFn>(parserCtorHook.trampoline);
        if (fileExistsOk) originalFileExistsForEffectsBootstrap = reinterpret_cast<FileExistsFn>(fileExistsHook.trampoline);

        if (!bootstrapLoadOk || !parserCtorOk) {
            Uninstall();
            return false;
        }

        if (!parseQueuedFilesOk) {
            LOG_WARN("Proceeding without ParseQueuedFiles hook; extra plugin .fx injection is disabled");
            originalEffectsParseQueuedFiles = nullptr;
        }
        if (!fileExistsOk) {
            LOG_WARN("Proceeding without bootstrap file-exists override; extra plugin .fx files may still require main.fx");
            originalFileExistsForEffectsBootstrap = nullptr;
        }

        installed = true;
        return true;
    }

    void Uninstall() noexcept
    {
        UninstallInlineHook(bootstrapLoadHook);
        UninstallInlineHook(parseQueuedFilesHook);
        UninstallInlineHook(parserCtorHook);
        UninstallInlineHook(fileExistsHook);

        originalEffectsBootstrapLoad = nullptr;
        originalEffectsParseQueuedFiles = nullptr;
        originalEffectsParserCtor = nullptr;
        originalFileExistsForEffectsBootstrap = nullptr;
        inEffectsBootstrapLoad = false;
        installed = false;

        if (g_activeImpl == this) {
            g_activeImpl = nullptr;
        }
    }

    void EmitInfo(std::string_view line) const
    {
        if (callbacks.onInfoEvent) {
            callbacks.onInfoEvent(line);
        }
        LOG_INFO("{}", line);
    }

    void EmitParserError(std::string_view line) const
    {
        if (callbacks.onParserError) {
            callbacks.onParserError(line);
        }
        LOG_ERROR("{}", line);
    }

    std::vector<std::filesystem::path> EnumeratePluginFxFiles() const
    {
        std::vector<std::filesystem::path> files;
        if (!loadPluginFxRecursively || pluginFxRoot.empty()) return files;

        std::error_code ec;
        if (!std::filesystem::exists(pluginFxRoot, ec) || ec) return files;

        for (std::filesystem::recursive_directory_iterator it(pluginFxRoot, ec), end; it != end; it.increment(ec)) {
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

    void QueueExtraPluginFxFilesOnParserInterface(void* fileParser) const noexcept
    {
        if (!loadPluginFxRecursively || !fileParser) return;

        auto* const vtable = *reinterpret_cast<void***>(fileParser);
        if (!vtable || !vtable[0x18 / sizeof(void*)]) {
            LOG_WARN("Plugin .fx queue skipped: AddInputFilePath slot is unavailable");
            return;
        }

        const auto files = EnumeratePluginFxFiles();
        if (files.empty()) {
            LOG_INFO("Plugin .fx queue: no extra .fx files found under '{}'", pluginFxRoot.string());
            return;
        }

        const auto addInputFilePath = reinterpret_cast<FileParserAddInputFilePathFn>(vtable[0x18 / sizeof(void*)]);
        for (const auto& path : files) {
            const auto pathString = path.string();
            addInputFilePath(fileParser, pathString.c_str(), 3);
            LOG_INFO("Plugin .fx queue: {}", pathString);
        }

        LOG_INFO("Plugin .fx queue: queued {} extra .fx files from '{}'", files.size(), pluginFxRoot.string());
    }

    void LogFileParserErrorConsole(void* fileParser) const noexcept
    {
        if (!fileParser) return;

        auto* const vtable = *reinterpret_cast<void***>(fileParser);
        if (!vtable || !vtable[0x28 / sizeof(void*)]) return;

        const auto getLastErrorString = reinterpret_cast<FileParserGetLastErrorStringFn>(vtable[0x28 / sizeof(void*)]);
        const char* const error = getLastErrorString(fileParser);
        if (!error || !*error) return;

        std::string errorText("Effects parser: ");
        errorText += error;
        EmitParserError(errorText);
    }

    void CallEffectsParserEnableResourceSaving(const int parser) const noexcept
    {
        if (!parser) return;
        const auto interfaceThis = reinterpret_cast<void*>(static_cast<uintptr_t>(parser) + kEffectsParserSaveEnableInterfaceOffset);
        auto** const vtable = interfaceThis ? *reinterpret_cast<void***>(interfaceThis) : nullptr;
        if (!vtable) return;
        const auto fn = reinterpret_cast<EffectsParserEnableResourceSavingFn>(vtable[kEffectsParserEnableResourceSavingVtableIndex]);
        if (!fn) return;
        fn(interfaceThis);
    }

    static void __fastcall HookEffectsBootstrapLoad(void* pThis, void*) noexcept
    {
        if (!g_activeImpl) return;

        auto* const bootstrap = reinterpret_cast<uint8_t*>(pThis);
        void* const fileParserInterface = *reinterpret_cast<void* const*>(bootstrap + kEffectsBootstrapParserInterfaceOffset);
        void* const parserInterface = *reinterpret_cast<void* const*>(bootstrap + kEffectsBootstrapParserObjectOffset);
        if (parserInterface) {
            const auto parser = static_cast<int>(
                reinterpret_cast<uintptr_t>(reinterpret_cast<uint8_t*>(parserInterface) - kEffectsParserSaveEnableInterfaceOffset));
            g_activeImpl->EmitInfo(
                "LoadAllEffects saveEnabled=" +
                std::to_string(static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset))));
            LOG_INFO(
                "LoadAllEffects parserIfc=0x{:08X} vtbl=0x{:08X} parserObjIfc=0x{:08X} vtbl=0x{:08X}",
                static_cast<uint32_t>(reinterpret_cast<uintptr_t>(fileParserInterface)),
                fileParserInterface ? static_cast<uint32_t>(reinterpret_cast<uintptr_t>(*reinterpret_cast<void**>(fileParserInterface))) : 0u,
                static_cast<uint32_t>(reinterpret_cast<uintptr_t>(parserInterface)),
                static_cast<uint32_t>(reinterpret_cast<uintptr_t>(*reinterpret_cast<void**>(parserInterface))));
        }

        g_activeImpl->inEffectsBootstrapLoad = true;
        if (g_activeImpl->originalEffectsBootstrapLoad) {
            g_activeImpl->originalEffectsBootstrapLoad(pThis);
        }
        g_activeImpl->inEffectsBootstrapLoad = false;
    }

    static void __fastcall HookEffectsParseQueuedFiles(const int pThis, void*) noexcept
    {
        if (!g_activeImpl) return;

        void* parserInterface = nullptr;
        void* effectsParserInterface = nullptr;
        if (g_activeImpl->inEffectsBootstrapLoad) {
            const auto* const bootstrap = reinterpret_cast<const uint8_t*>(pThis);
            parserInterface = *reinterpret_cast<void* const*>(bootstrap + kEffectsBootstrapParserInterfaceOffset);
            effectsParserInterface = *reinterpret_cast<void* const*>(bootstrap + kEffectsBootstrapParserObjectOffset);
            LOG_INFO(
                "ParseQueuedFiles during bootstrap: manager=0x{:08X} parserIfc=0x{:08X}",
                static_cast<uint32_t>(pThis),
                static_cast<uint32_t>(reinterpret_cast<uintptr_t>(parserInterface)));
            if (effectsParserInterface) {
                const auto parser = static_cast<int>(
                    reinterpret_cast<uintptr_t>(reinterpret_cast<uint8_t*>(effectsParserInterface) - kEffectsParserSaveEnableInterfaceOffset));
                const auto before = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
                g_activeImpl->CallEffectsParserEnableResourceSaving(parser);
                const auto after = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
                g_activeImpl->EmitInfo("ParseQueuedFiles saveEnabled " + std::to_string(before) + " -> " + std::to_string(after));
            }
            g_activeImpl->QueueExtraPluginFxFilesOnParserInterface(parserInterface);
        }

        if (g_activeImpl->originalEffectsParseQueuedFiles) {
            g_activeImpl->originalEffectsParseQueuedFiles(pThis, nullptr);
        }

        if (!parserInterface) {
            const auto* const bootstrap = reinterpret_cast<const uint8_t*>(pThis);
            parserInterface = *reinterpret_cast<void* const*>(bootstrap + kEffectsBootstrapParserInterfaceOffset);
        }
        g_activeImpl->LogFileParserErrorConsole(parserInterface);
    }

    static bool __cdecl HookFileExistsForEffectsBootstrap(int* path) noexcept
    {
        if (!g_activeImpl) return false;

        const bool exists = g_activeImpl->originalFileExistsForEffectsBootstrap
            ? g_activeImpl->originalFileExistsForEffectsBootstrap(path)
            : false;
        if (exists) {
            return true;
        }

        if (!g_activeImpl->inEffectsBootstrapLoad || !g_activeImpl->loadPluginFxRecursively) {
            return false;
        }

        const auto files = g_activeImpl->EnumeratePluginFxFiles();
        if (files.empty()) {
            return false;
        }

        LOG_INFO("Forcing bootstrap file-exists branch because {} extra plugin .fx files were found", files.size());
        return true;
    }

    static void* __fastcall HookEffectsParserCtor(void* pThis, void*, const int ctorArg) noexcept
    {
        if (!g_activeImpl) return pThis;

        void* result = pThis;
        if (g_activeImpl->originalEffectsParserCtor) {
            result = g_activeImpl->originalEffectsParserCtor(pThis, ctorArg);
        }

        if (result && ctorArg != 0) {
            const auto parser = static_cast<int>(reinterpret_cast<uintptr_t>(result));
            const auto before = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
            g_activeImpl->CallEffectsParserEnableResourceSaving(parser);
            const auto after = static_cast<unsigned>(ReadParserByte(parser, kEffectsParserResourceSaveEnabledOffset));
            g_activeImpl->EmitInfo("EffectsParser::Ctor saveEnabled " + std::to_string(before) + " -> " + std::to_string(after));
        }

        return result;
    }

    static inline Impl* g_activeImpl = nullptr;

    Callbacks callbacks;
    InlineHook bootstrapLoadHook;
    InlineHook parseQueuedFilesHook;
    InlineHook parserCtorHook;
    InlineHook fileExistsHook;
    EffectsBootstrapLoadFn originalEffectsBootstrapLoad = nullptr;
    EffectsParseQueuedFilesFn originalEffectsParseQueuedFiles = nullptr;
    EffectsParserCtorFn originalEffectsParserCtor = nullptr;
    FileExistsFn originalFileExistsForEffectsBootstrap = nullptr;
    std::filesystem::path pluginFxRoot;
    bool loadPluginFxRecursively = false;
    bool inEffectsBootstrapLoad = false;
    bool installed = false;
};

EffectsBootstrapHooks::EffectsBootstrapHooks(Callbacks callbacks)
    : callbacks_(std::move(callbacks))
    , impl_(new Impl(callbacks_))
{
}

EffectsBootstrapHooks::~EffectsBootstrapHooks()
{
    impl_->Uninstall();
    delete impl_;
}

void EffectsBootstrapHooks::ConfigureRecursiveLoading(const bool enabled, std::filesystem::path rootPath)
{
    impl_->ConfigureRecursiveLoading(enabled, std::move(rootPath));
}

bool EffectsBootstrapHooks::Install(const uint16_t gameVersion) noexcept
{
    return impl_->Install(gameVersion);
}

void EffectsBootstrapHooks::Uninstall() noexcept
{
    impl_->Uninstall();
}
