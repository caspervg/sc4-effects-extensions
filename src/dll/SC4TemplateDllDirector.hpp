#pragma once

#include <cRZMessage2COMDirector.h>
#include <filesystem>
#include <memory>

#include "public/cIGZImGuiService.h"

class HelloPanel;
class cIGZMessage2;
class cIGZCOM;

class SC4TemplateDllDirector final : public cRZMessage2COMDirector
{
public:
    SC4TemplateDllDirector();
    ~SC4TemplateDllDirector() override;

    [[nodiscard]] uint32_t GetDirectorID() const override;
    bool OnStart(cIGZCOM* pCOM) override;
    bool PreFrameWorkInit() override;
    bool PreAppInit() override;
    bool PostAppInit() override;
    bool PreAppShutdown() override;
    bool PostAppShutdown() override;
    bool PostSystemServiceShutdown() override;
    bool AbortiveQuit() override;
    bool OnInstall() override;
    bool DoMessage(cIGZMessage2* pMsg) override;

private:
    static std::filesystem::path GetUserPluginsPath_();
    void InitializeLogger_();

private:
    cIGZImGuiService* imguiService_ = nullptr;
    std::unique_ptr<HelloPanel> panel_;
    bool panelRegistered_ = false;
};
