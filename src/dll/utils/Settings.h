#pragma once

#include <filesystem>
#include <string>

#include <spdlog/common.h>

class Settings
{
public:
    Settings();

    void Load(const std::filesystem::path& settingsFilePath);

    [[nodiscard]] spdlog::level::level_enum GetLogLevel() const noexcept;
    [[nodiscard]] bool GetLogToFile() const noexcept;
    [[nodiscard]] bool GetStartWindowVisible() const noexcept;
    [[nodiscard]] bool GetLoadPluginFxRecursively() const noexcept;
    [[nodiscard]] std::filesystem::path GetPluginFxRoot() const;
    [[nodiscard]] std::filesystem::path GetPackedEffectsOutputPath() const;

private:
    spdlog::level::level_enum logLevel_;
    bool logToFile_;
    bool startWindowVisible_;
    bool loadPluginFxRecursively_;
    std::string pluginFxRoot_;
    std::string packedEffectsOutputPath_;
};

