#include "EffectsPanel.hpp"

#include <algorithm>
#include <cstring>
#include <cstdio>
#include <string>

#include "../SC4EffectsExtensionsDirector.hpp"

EffectsPanel::EffectsPanel(SC4EffectsExtensionsDirector& director)
    : director_(director)
{
    const auto trackedState = director_.GetTrackedEffectState();
    trackedState_.active = trackedState.active;
    trackedState_.position[0] = trackedState.position[0];
    trackedState_.position[1] = trackedState.position[1];
    trackedState_.position[2] = trackedState.position[2];
    trackedState_.rotation[0] = trackedState.rotation[0];
    trackedState_.rotation[1] = trackedState.rotation[1];
    trackedState_.rotation[2] = trackedState.rotation[2];
    trackedState_.scale = trackedState.scale;
}

void EffectsPanel::SetDetectedGameVersion(const uint16_t version)
{
    detectedGameVersion_ = version;
}

void EffectsPanel::SetVersionLabel(const char* version)
{
    versionLabel_ = version ? version : "dev";
}

void EffectsPanel::SetVisible(const bool visible)
{
    visible_ = visible;
}

void EffectsPanel::OnVisibleChanged(const bool visible)
{
    visible_ = visible;
}

void EffectsPanel::OnRender()
{
    if (!visible_) {
        return;
    }

    bool open = visible_;
    ImGui::SetNextWindowSize(ImVec2(620.0f, 720.0f), ImGuiCond_FirstUseEver);
    if (ImGui::Begin("SC4 Effects Console", &open)) {
        if (ImGui::BeginTabBar("effects_tabs")) {
            if (ImGui::BeginTabItem("Catalog")) {
                RenderCatalogTab_();
                ImGui::EndTabItem();
            }
            if (ImGui::BeginTabItem("Console")) {
                RenderConsoleTab_();
                ImGui::EndTabItem();
            }
            ImGui::EndTabBar();
        }
    }
    ImGui::End();
    visible_ = open;
}

void EffectsPanel::RenderCatalogTab_()
{
    RenderManualSpawn_();
    ImGui::Separator();
    RenderTrackedEffect_();
    ImGui::Separator();
    RenderEffectsList_();
}

void EffectsPanel::RenderConsoleTab_()
{
    RenderRecentEvents_();
}

void EffectsPanel::RenderManualSpawn_()
{
    ImGui::TextUnformatted("Manual spawn");
    ImGui::InputTextWithHint("##spawn_effect_name", "Effect name", spawnInput_.data(), spawnInput_.size());

    if (ImGui::Button("Spawn")) {
        director_.SpawnEffectByName(spawnInput_.data());
    }

    const std::string lastStatus = director_.GetLastSpawnStatus();
    if (!lastStatus.empty()) {
        ImGui::Spacing();
        ImGui::TextWrapped("%s", lastStatus.c_str());
    }
}

void EffectsPanel::RenderTrackedEffect_()
{
    ImGui::TextUnformatted("Tracked effect");
    ImGui::Checkbox("Auto-apply transform", &autoApplyTrackedTransform_);

    const auto trackedState = director_.GetTrackedEffectState();
    if (trackedState.active) {
        trackedState_.active = true;
    }

    if (trackedState.active) {
        ImGui::Text("Active: %s", trackedState.name.c_str());
    } else {
        ImGui::TextUnformatted("Active: none");
    }

    bool changed = false;
    changed |= ImGui::DragFloat3("Position", trackedState_.position, 1.0f);
    changed |= ImGui::DragFloat3("Rotation XYZ", trackedState_.rotation, 1.0f);
    changed |= ImGui::DragFloat("Scale", &trackedState_.scale, 0.01f, 0.01f, 100.0f, "%.2f");

    if (ImGui::Button("Spawn tracked")) {
        SC4EffectsExtensionsDirector::TrackedEffectState nextState{};
        nextState.position[0] = trackedState_.position[0];
        nextState.position[1] = trackedState_.position[1];
        nextState.position[2] = trackedState_.position[2];
        nextState.rotation[0] = trackedState_.rotation[0];
        nextState.rotation[1] = trackedState_.rotation[1];
        nextState.rotation[2] = trackedState_.rotation[2];
        nextState.scale = trackedState_.scale;
        director_.SpawnTrackedEffectByName(spawnInput_.data(), nextState);
    }

    ImGui::SameLine();
    if (ImGui::Button("Apply transform")) {
        SC4EffectsExtensionsDirector::TrackedEffectState nextState{};
        nextState.position[0] = trackedState_.position[0];
        nextState.position[1] = trackedState_.position[1];
        nextState.position[2] = trackedState_.position[2];
        nextState.rotation[0] = trackedState_.rotation[0];
        nextState.rotation[1] = trackedState_.rotation[1];
        nextState.rotation[2] = trackedState_.rotation[2];
        nextState.scale = trackedState_.scale;
        director_.UpdateTrackedEffectTransform(nextState);
    }

    ImGui::SameLine();
    if (ImGui::Button("Stop tracked")) {
        director_.StopTrackedEffect();
    }

    if (changed && autoApplyTrackedTransform_ && trackedState.active) {
        SC4EffectsExtensionsDirector::TrackedEffectState nextState{};
        nextState.position[0] = trackedState_.position[0];
        nextState.position[1] = trackedState_.position[1];
        nextState.position[2] = trackedState_.position[2];
        nextState.rotation[0] = trackedState_.rotation[0];
        nextState.rotation[1] = trackedState_.rotation[1];
        nextState.rotation[2] = trackedState_.rotation[2];
        nextState.scale = trackedState_.scale;
        director_.UpdateTrackedEffectTransform(nextState);
    }
}

void EffectsPanel::RenderEffectsList_()
{
    ImGui::TextUnformatted("Catalog");
    ImGui::InputTextWithHint("##effect_filter", "Filter effects", filterInput_.data(), filterInput_.size());
    ImGui::SameLine();
    if (ImGui::Button("Refresh catalog")) {
        director_.RefreshKnownEffects();
    }

    const auto effects = director_.GetKnownEffectsSnapshot();
    const std::string filter = filterInput_.data();

    ImGui::BeginChild("effects_catalog", ImVec2(0.0f, 260.0f), true);
    for (const std::string& effectName : effects) {
        if (!filter.empty() && effectName.find(filter) == std::string::npos) {
            continue;
        }

        if (ImGui::Selectable(effectName.c_str(), false)) {
            std::snprintf(spawnInput_.data(), spawnInput_.size(), "%s", effectName.c_str());
        }
    }
    ImGui::EndChild();
}

void EffectsPanel::RenderRecentEvents_()
{
    ImGui::Text("Console (%zu lines)", director_.GetRecentEventCount());
    ImGui::SameLine();
    if (ImGui::Button("Clear console")) {
        director_.ClearRecentEvents();
    }

    const auto recentEvents = director_.GetRecentEventsSnapshot();

    ImGui::BeginChild("recent_effect_events", ImVec2(0.0f, 0.0f), true);
    for (const auto& event : recentEvents) {
        if (event.severity == SC4EffectsExtensionsDirector::EventSeverity::Error) {
            ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.93f, 0.28f, 0.24f, 1.0f));
        } else if (event.severity == SC4EffectsExtensionsDirector::EventSeverity::Warning) {
            ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.95f, 0.69f, 0.20f, 1.0f));
        }

        ImGui::TextWrapped("%s", event.text.c_str());

        if (event.severity != SC4EffectsExtensionsDirector::EventSeverity::Info) {
            ImGui::PopStyleColor();
        }
    }
    ImGui::EndChild();
}
