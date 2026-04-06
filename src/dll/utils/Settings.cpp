#include "Settings.h"

#include <algorithm>
#include <cctype>
#include <exception>
#include <string>

#include "Logger.h"
#include "mini/ini.h"

namespace {
    constexpr auto kDefaultLogLevel = spdlog::level::info;
    constexpr bool kDefaultLogToFile = true;
    constexpr bool kDefaultStartWindowVisible = true;
    constexpr auto kSectionName = "SC4TemplateDll";

    std::string ToLower(std::string value)
    {
        std::ranges::transform(value, value.begin(), [](const unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        return value;
    }

    spdlog::level::level_enum ParseLogLevel(const std::string& value, bool& valid)
    {
        const std::string normalized = ToLower(value);

        if (normalized == "trace") { valid = true; return spdlog::level::trace; }
        if (normalized == "debug") { valid = true; return spdlog::level::debug; }
        if (normalized == "info") { valid = true; return spdlog::level::info; }
        if (normalized == "warn" || normalized == "warning") { valid = true; return spdlog::level::warn; }
        if (normalized == "error") { valid = true; return spdlog::level::err; }
        if (normalized == "critical") { valid = true; return spdlog::level::critical; }
        if (normalized == "off") { valid = true; return spdlog::level::off; }

        valid = false;
        return kDefaultLogLevel;
    }

    bool ParseBool(const std::string& value, bool& valid)
    {
        const std::string normalized = ToLower(value);

        if (normalized == "true" || normalized == "1" || normalized == "yes") {
            valid = true;
            return true;
        }
        if (normalized == "false" || normalized == "0" || normalized == "no") {
            valid = true;
            return false;
        }

        valid = false;
        return false;
    }
}

Settings::Settings()
    : logLevel_(kDefaultLogLevel)
    , logToFile_(kDefaultLogToFile)
    , startWindowVisible_(kDefaultStartWindowVisible)
{
}

void Settings::Load(const std::filesystem::path& settingsFilePath)
{
    *this = Settings();

    try {
        const mINI::INIFile file(settingsFilePath.string());
        mINI::INIStructure ini;

        if (!file.read(ini) || !ini.has(kSectionName)) {
            return;
        }

        const auto section = ini.get(kSectionName);

        if (section.has("LogLevel")) {
            bool valid = false;
            logLevel_ = ParseLogLevel(section.get("LogLevel"), valid);
            if (!valid) {
                logLevel_ = kDefaultLogLevel;
                LOG_WARN("Invalid LogLevel in {}", settingsFilePath.string());
            }
        }

        if (section.has("LogToFile")) {
            bool valid = false;
            logToFile_ = ParseBool(section.get("LogToFile"), valid);
            if (!valid) {
                logToFile_ = kDefaultLogToFile;
                LOG_WARN("Invalid LogToFile in {}", settingsFilePath.string());
            }
        }

        if (section.has("StartWindowVisible")) {
            bool valid = false;
            startWindowVisible_ = ParseBool(section.get("StartWindowVisible"), valid);
            if (!valid) {
                startWindowVisible_ = kDefaultStartWindowVisible;
                LOG_WARN("Invalid StartWindowVisible in {}", settingsFilePath.string());
            }
        }
    }
    catch (const std::exception& e) {
        LOG_ERROR("Failed to read settings from {}: {}", settingsFilePath.string(), e.what());
        *this = Settings();
    }
}

spdlog::level::level_enum Settings::GetLogLevel() const noexcept
{
    return logLevel_;
}

bool Settings::GetLogToFile() const noexcept
{
    return logToFile_;
}

bool Settings::GetStartWindowVisible() const noexcept
{
    return startWindowVisible_;
}

