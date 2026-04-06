#pragma once

#include <filesystem>

#include <spdlog/common.h>

class Settings
{
public:
    Settings();

    void Load(const std::filesystem::path& settingsFilePath);

    [[nodiscard]] spdlog::level::level_enum GetLogLevel() const noexcept;
    [[nodiscard]] bool GetLogToFile() const noexcept;
    [[nodiscard]] bool GetStartWindowVisible() const noexcept;

private:
    spdlog::level::level_enum logLevel_;
    bool logToFile_;
    bool startWindowVisible_;
};

