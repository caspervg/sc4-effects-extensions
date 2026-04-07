#pragma once

#include <functional>
#include <memory>
#include <string>
#include <string_view>

#include <spdlog/spdlog.h>

class Logger
{
public:
    using ConsoleCallback = std::function<void(spdlog::level::level_enum, std::string_view)>;

    static std::shared_ptr<spdlog::logger> Get();
    static void Initialize(const std::string& logName = "SC4EffectsExtensions",
                           const std::string& userDir = "",
                           bool logToFile = true);
    static void SetLevel(spdlog::level::level_enum logLevel);
    static void SetConsoleCallback(ConsoleCallback callback);
    static void DispatchConsoleMessage(spdlog::level::level_enum level, std::string_view message);
    static void Shutdown();

private:
    static std::shared_ptr<spdlog::logger> s_logger;
    static ConsoleCallback s_consoleCallback;
    static std::string s_logName;
    static bool s_initialized;
};

#define LOG_TRACE(...) Logger::Get()->trace(__VA_ARGS__)
#define LOG_DEBUG(...) Logger::Get()->debug(__VA_ARGS__)
#define LOG_INFO(...) Logger::Get()->info(__VA_ARGS__)
#define LOG_WARN(...) Logger::Get()->warn(__VA_ARGS__)
#define LOG_ERROR(...) Logger::Get()->error(__VA_ARGS__)
#define LOG_CRITICAL(...) Logger::Get()->critical(__VA_ARGS__)

