#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "imgui.h"
#include "public/ImGuiPanel.h"

class SC4EffectsExtensionsDirector;

class EffectsPanel final : public ImGuiPanel
{
public:
    explicit EffectsPanel(SC4EffectsExtensionsDirector& director);

    void SetDetectedGameVersion(uint16_t version);
    void SetVersionLabel(const char* version);
    void SetVisible(bool visible);

    void OnRender() override;
    void OnVisibleChanged(bool visible) override;

private:
    struct TrackedTransformUiState {
        bool active = false;
        float position[3] = {512.0f, 280.0f, 512.0f};
        float rotation[3] = {0.0f, 0.0f, 0.0f};
        float scale = 1.0f;
    };

    void RenderCatalogTab_();
    void RenderConsoleTab_();
    void RenderManualSpawn_();
    void RenderTrackedEffect_();
    void RenderEffectsList_();
    void RenderRecentEvents_();

private:
    SC4EffectsExtensionsDirector& director_;
    bool visible_ = true;
    uint16_t detectedGameVersion_ = 0;
    std::string versionLabel_ = "dev";
    std::array<char, 128> spawnInput_{};
    std::array<char, 128> filterInput_{};
    TrackedTransformUiState trackedState_{};
    bool autoApplyTrackedTransform_ = true;
};
