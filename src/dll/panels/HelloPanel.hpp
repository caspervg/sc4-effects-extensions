#pragma once

#include <cstdint>
#include <string>

#include "imgui.h"
#include "public/ImGuiPanel.h"

class HelloPanel final : public ImGuiPanel
{
public:
    void SetDetectedGameVersion(uint16_t version);
    void SetVersionLabel(const char* version);
    void SetVisible(bool visible);

    void OnRender() override;
    void OnVisibleChanged(bool visible) override;

private:
    bool visible_ = true;
    uint16_t detectedGameVersion_ = 0;
    std::string versionLabel_ = "dev";
};

