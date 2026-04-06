#include "SC4EffectsExtensionsDirector.hpp"

#include <cIGZFrameWork.h>

#include "imgui.h"
#include "panels/HelloPanel.hpp"
#include "public/ImGuiPanelAdapter.h"
#include "public/ImGuiServiceIds.h"
#include "utils/Logger.h"
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
}

SC4EffectsExtensionsDirector::SC4EffectsExtensionsDirector() = default;

SC4EffectsExtensionsDirector::~SC4EffectsExtensionsDirector() = default;

uint32_t SC4EffectsExtensionsDirector::GetDirectorID() const
{
    return kDirectorId;
}

bool SC4EffectsExtensionsDirector::OnStart(cIGZCOM* pCOM)
{
    cRZMessage2COMDirector::OnStart(pCOM);

    if (auto* framework = RZGetFrameWork()) {
        framework->AddHook(this);
    }

    return true;
}

bool SC4EffectsExtensionsDirector::PreFrameWorkInit()
{
    return true;
}

bool SC4EffectsExtensionsDirector::PreAppInit()
{
    return true;
}

bool SC4EffectsExtensionsDirector::PostAppInit()
{
    InitializeLogger_();

    const auto gameVersion = VersionDetection::GetInstance().GetGameVersion();
    LOG_INFO("PostAppInit");
    LOG_INFO("Detected game version: {}", gameVersion);

    if (mpFrameWork && mpFrameWork->GetSystemService(
        kImGuiServiceID,
        GZIID_cIGZImGuiService,
        reinterpret_cast<void**>(&imguiService_))) {
        panel_ = std::make_unique<HelloPanel>();
        panel_->SetDetectedGameVersion(gameVersion);
        panel_->SetVersionLabel(SC4_TEMPLATE_DLL_VERSION_LABEL);

        Settings settings;
        settings.Load(GetUserPluginsPath_() / "SC4EffectsExtensions.ini");
        panel_->SetVisible(settings.GetStartWindowVisible());

        const ImGuiPanelDesc desc = ImGuiPanelAdapter<HelloPanel>::MakeDesc(
            panel_.get(),
            kPanelId,
            100,
            settings.GetStartWindowVisible());

        if (imguiService_->RegisterPanel(desc)) {
            panelRegistered_ = true;
            LOG_INFO("Registered demo ImGui panel");
        }
        else {
            LOG_WARN("Failed to register demo ImGui panel");
        }
    }
    else {
        LOG_WARN("ImGui service not available");
    }

    return true;
}

bool SC4EffectsExtensionsDirector::PreAppShutdown()
{
    return true;
}

bool SC4EffectsExtensionsDirector::PostAppShutdown()
{
    if (imguiService_ && panelRegistered_) {
        imguiService_->UnregisterPanel(kPanelId);
        panelRegistered_ = false;
    }

    panel_.reset();

    if (imguiService_) {
        imguiService_->Release();
        imguiService_ = nullptr;
    }

    if (auto* framework = RZGetFrameWork()) {
        framework->RemoveHook(this);
    }

    Logger::Shutdown();
    return true;
}

bool SC4EffectsExtensionsDirector::PostSystemServiceShutdown()
{
    return true;
}

bool SC4EffectsExtensionsDirector::AbortiveQuit()
{
    return true;
}

bool SC4EffectsExtensionsDirector::OnInstall()
{
    return true;
}

bool SC4EffectsExtensionsDirector::DoMessage(cIGZMessage2* pMsg)
{
    (void)pMsg;
    return true;
}

std::filesystem::path SC4EffectsExtensionsDirector::GetUserPluginsPath_()
{
    try {
        const auto modulePath = wil::GetModuleFileNameW(wil::GetModuleInstanceHandle());
        return std::filesystem::path(modulePath.get()).parent_path();
    }
    catch (const wil::ResultException&) {
        return {};
    }
}

void SC4EffectsExtensionsDirector::InitializeLogger_()
{
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
