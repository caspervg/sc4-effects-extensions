#include "EffectsGameCommands.hpp"

#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

#include "GZServPtrs.h"
#include "SC4EffectsExtensionsDirector.hpp"
#include "cIGZCommandParameterSet.h"
#include "cIGZCommandServer.h"
#include "cIGZMessage2.h"
#include "cIGZMessage2Standard.h"
#include "cIGZMessageServer2.h"
#include "cIGZString.h"
#include "cIGZVariant.h"
#include "cRZBaseString.h"
#include "utils/Logger.h"

namespace {
constexpr uint32_t kCommandStatus = 0xE5C2B9B0u;
constexpr uint32_t kCommandLoadFx = 0xE5C2B9B1u;
constexpr uint32_t kCommandPreviewStart = 0xE5C2B9B2u;
constexpr uint32_t kCommandPreviewTransform = 0xE5C2B9B3u;
constexpr uint32_t kCommandPreviewStop = 0xE5C2B9B4u;

constexpr cIGZCommandServer::cGZCommandInfo kCommands[] = {
    {kCommandStatus, "EffectsStatus", nullptr},
    {kCommandLoadFx, "EffectsLoadFx", nullptr},
    {kCommandPreviewStart, "EffectsPreviewStart", nullptr},
    {kCommandPreviewTransform, "EffectsPreviewTransform", nullptr},
    {kCommandPreviewStop, "EffectsPreviewStop", nullptr},
};

std::vector<std::string> GetArguments(cIGZCommandParameterSet* input)
{
    std::vector<std::string> result;
    if (!input) return result;
    result.reserve(input->GetParameterCount());
    for (uint32_t index = 0; index < input->GetParameterCount(); ++index) {
        cIGZVariant* const value = input->GetParameter(index);
        if (!value) continue;
        cRZBaseString text;
        if (value->GetValString(text)) {
            result.emplace_back(text.ToChar() ? text.ToChar() : "");
        }
    }
    return result;
}

std::string JoinArguments(const std::vector<std::string>& args)
{
    std::string result;
    for (const auto& arg : args) {
        if (!result.empty()) result.push_back(' ');
        result += arg;
    }
    return result;
}

bool ParseFloat(const std::string& text, float& value)
{
    char* end = nullptr;
    value = std::strtof(text.c_str(), &end);
    return end && end != text.c_str() && *end == '\0';
}

void SetResult(cIGZCommandParameterSet* output, const bool success, const std::string& message)
{
    if (!output) return;
    output->SetParameterCount(0);
    output->SetParameterCount(1);
    if (cIGZVariant* const value = output->GetParameter(0)) {
        value->SetValString(cRZBaseString(message));
    }
    output->SetStatusParameterValue(success ? 0 : 1);
}
}

EffectsGameCommands::EffectsGameCommands(SC4EffectsExtensionsDirector& director) : director_(director) {}
EffectsGameCommands::~EffectsGameCommands() { Uninstall(); }

bool EffectsGameCommands::Install()
{
    cIGZCommandServerPtr commandServer;
    cIGZMessageServer2Ptr messageServer;
    if (!commandServer || !messageServer) return false;

    commandServer_ = commandServer;
    commandServer_->AddRef();
    messageServer_ = messageServer;
    messageServer_->AddRef();
    if (!commandServer_->RegisterCommands(const_cast<cIGZCommandServer::cGZCommandInfo*>(kCommands), std::size(kCommands))) {
        Uninstall();
        return false;
    }
    for (const auto& command : kCommands) {
        if (!messageServer_->AddNotification(&director_, command.dwCommandID)) {
            Uninstall();
            return false;
        }
        ++notificationCount_;
    }

    LOG_INFO("registered {} effects game commands", std::size(kCommands));
    return true;
}

void EffectsGameCommands::Uninstall() noexcept
{
    if (messageServer_) {
        for (uint32_t index = 0; index < notificationCount_; ++index) {
            messageServer_->RemoveNotification(&director_, kCommands[index].dwCommandID);
        }
        notificationCount_ = 0;
        messageServer_->Release();
        messageServer_ = nullptr;
    }
    if (commandServer_) {
        commandServer_->UnregisterCommands(const_cast<cIGZCommandServer::cGZCommandInfo*>(kCommands), std::size(kCommands));
        commandServer_->Release();
        commandServer_ = nullptr;
    }
}

bool EffectsGameCommands::HandleMessage(cIGZMessage2* message)
{
    if (!message) return false;
    const uint32_t commandId = message->GetType();
    bool recognized = false;
    for (const auto& command : kCommands) recognized = recognized || command.dwCommandID == commandId;
    if (!recognized) return false;

    auto* const standard = static_cast<cIGZMessage2Standard*>(message);
    Execute(
        commandId,
        static_cast<cIGZCommandParameterSet*>(standard->GetVoid1()),
        static_cast<cIGZCommandParameterSet*>(standard->GetVoid2()));
    return true;
}

int32_t EffectsGameCommands::Execute(
    const uint32_t commandId,
    cIGZCommandParameterSet* input,
    cIGZCommandParameterSet* output)
{
    const auto args = GetArguments(input);
    std::string message;
    bool success = false;

    switch (commandId) {
    case kCommandStatus: {
        const auto tracked = director_.GetTrackedEffectState();
        message = "city=" + std::to_string(director_.IsCityLoaded()) +
                  " hooks=" + std::to_string(director_.IsEffectsHookInstalled()) +
                  " effects=" + std::to_string(director_.GetKnownEffectCount()) +
                  " tracked=" + (tracked.active ? tracked.name : "-");
        success = true;
        break;
    }
    case kCommandLoadFx:
        if (args.empty()) {
            message = "Usage: EffectsLoadFx <absolute .fx path>";
        } else {
            success = director_.LoadFxFile(std::filesystem::path(JoinArguments(args)), message);
        }
        break;
    case kCommandPreviewStart: {
        if (args.empty() || (args.size() != 1 && args.size() != 8)) {
            message = "Usage: EffectsPreviewStart <name> [x y z rx ry rz scale]";
            break;
        }
        auto state = director_.GetTrackedEffectState();
        if (args.size() == 8) {
            float* values[] = {&state.position[0], &state.position[1], &state.position[2],
                               &state.rotation[0], &state.rotation[1], &state.rotation[2], &state.scale};
            for (size_t i = 0; i < std::size(values); ++i) {
                if (!ParseFloat(args[i + 1], *values[i])) {
                    message = "Preview transform contains an invalid number.";
                    SetResult(output, false, message);
                    return 1;
                }
            }
        }
        success = director_.SpawnTrackedEffectByName(args[0].c_str(), state);
        message = director_.GetLastSpawnStatus();
        break;
    }
    case kCommandPreviewTransform: {
        if (args.size() != 7) {
            message = "Usage: EffectsPreviewTransform <x> <y> <z> <rx> <ry> <rz> <scale>";
            break;
        }
        auto state = director_.GetTrackedEffectState();
        float* values[] = {&state.position[0], &state.position[1], &state.position[2],
                           &state.rotation[0], &state.rotation[1], &state.rotation[2], &state.scale};
        success = true;
        for (size_t i = 0; i < std::size(values); ++i) success = success && ParseFloat(args[i], *values[i]);
        if (success) success = director_.UpdateTrackedEffectTransform(state);
        message = success ? director_.GetLastSpawnStatus() : "Preview transform contains an invalid number.";
        break;
    }
    case kCommandPreviewStop:
        director_.StopTrackedEffect();
        success = true;
        message = "Preview stopped.";
        break;
    default:
        return 2;
    }

    SetResult(output, success, message);
    return success ? 0 : 1;
}
