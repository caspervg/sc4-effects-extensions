#include "Logger.h"

#include <cstdlib>
#include <filesystem>
#include <vector>

#include "spdlog/sinks/basic_file_sink.h"
#include "spdlog/sinks/msvc_sink.h"

std::shared_ptr<spdlog::logger> Logger::Get()
{
    if (!s_initialized) {
        Initialize();
    }
    return s_logger;
}

void Logger::Initialize(const std::string& logName, const std::string& userDir, const bool logToFile)
{
    if (s_initialized && s_logger) {
        return;
    }

    s_logName = logName;

    try {
        std::vector<spdlog::sink_ptr> sinks;
        sinks.push_back(std::make_shared<spdlog::sinks::msvc_sink_mt>());

        std::filesystem::path logDir;
        if (!userDir.empty()) {
            logDir = std::filesystem::path(userDir);
        }
        else {
            const char* userProfileEnv = std::getenv("USERPROFILE");
            const std::string userProfile = userProfileEnv ? userProfileEnv : "";
            if (!userProfile.empty()) {
                logDir = std::filesystem::path(userProfile) / "Documents" / "SimCity 4";
            }
        }

        if (logToFile && !logDir.empty()) {
            std::filesystem::create_directories(logDir);
            const std::string logPath = (logDir / (s_logName + ".log")).string();
            sinks.push_back(std::make_shared<spdlog::sinks::basic_file_sink_mt>(logPath, true));
        }

        s_logger = std::make_shared<spdlog::logger>(s_logName, sinks.begin(), sinks.end());
        spdlog::set_default_logger(s_logger);
        s_logger->set_level(spdlog::level::info);
        s_logger->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%l] %v");
        s_logger->flush_on(spdlog::level::info);
        s_initialized = true;
    }
    catch (const std::exception&) {
        auto consoleSink = std::make_shared<spdlog::sinks::msvc_sink_mt>();
        s_logger = std::make_shared<spdlog::logger>(s_logName, consoleSink);
        spdlog::set_default_logger(s_logger);
        s_logger->set_level(spdlog::level::info);
        s_initialized = true;
    }
}

void Logger::SetLevel(const spdlog::level::level_enum logLevel)
{
    if (s_logger) {
        s_logger->set_level(logLevel);
        s_logger->flush_on(logLevel);
    }
}

void Logger::Shutdown()
{
    if (s_logger) {
        s_logger->flush();
        s_logger.reset();
    }
    spdlog::shutdown();
    s_initialized = false;
}

std::shared_ptr<spdlog::logger> Logger::s_logger = nullptr;
std::string Logger::s_logName = "SC4TemplateDll";
bool Logger::s_initialized = false;

