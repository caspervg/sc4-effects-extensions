#pragma once

#include <filesystem>
#include <functional>
#include <string_view>

class EffectsBootstrapHooks final
{
public:
    struct Callbacks {
        std::function<void(std::string_view)> onInfoEvent;
        std::function<void(std::string_view)> onParserError;
    };

    explicit EffectsBootstrapHooks(Callbacks callbacks);
    ~EffectsBootstrapHooks();

    EffectsBootstrapHooks(const EffectsBootstrapHooks&) = delete;
    EffectsBootstrapHooks& operator=(const EffectsBootstrapHooks&) = delete;

    void ConfigureRecursiveLoading(bool enabled, std::filesystem::path rootPath);
    bool Install(uint16_t gameVersion) noexcept;
    void Uninstall() noexcept;

private:
    class Impl;

    Callbacks callbacks_;
    Impl* impl_ = nullptr;
};
