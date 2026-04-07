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
        RenderOverview_();
        ImGui::Separator();
        RenderManualSpawn_();
        ImGui::Separator();
        RenderTrackedEffect_();
        ImGui::Separator();
        RenderDebugTools_();
        ImGui::Separator();
        RenderCatalogSources_();
        ImGui::Separator();
        RenderEffectsList_();
        ImGui::Separator();
        RenderRecentEvents_();
    }
    ImGui::End();
    visible_ = open;
}

void EffectsPanel::RenderOverview_() const
{
    ImGui::Text("DLL version: %s", versionLabel_.c_str());
    ImGui::Text("Detected game version: %u", detectedGameVersion_);
    ImGui::Text("City loaded: %s", director_.IsCityLoaded() ? "yes" : "no");
    ImGui::Text("Legacy parser/resource hooks: %s", director_.IsEffectsHookInstalled() ? "installed" : "not installed");
    ImGui::Text("Catalog entries: %zu", director_.GetKnownEffectCount());
    ImGui::TextWrapped(
        "This panel is manager-first now: it keeps the hook log as a console, but the main list is a validated runtime catalog probe against the live effects manager.");

    const std::string stats = director_.GetEffectsStatsString();
    if (!stats.empty()) {
        ImGui::Spacing();
        ImGui::TextUnformatted("Manager stats:");
        ImGui::BeginChild("effects_stats", ImVec2(0.0f, 110.0f), true);
        ImGui::TextWrapped("%s", stats.c_str());
        ImGui::EndChild();
    }
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

void EffectsPanel::RenderDebugTools_()
{
    ImGui::TextUnformatted("Debug tools");
    if (ImGui::Button("Dump manager +0x98 hex")) {
        director_.DumpManagerMemory();
    }
    ImGui::SameLine();
    ImGui::TextUnformatted("Writes raw memory lines into the console below.");
}

void EffectsPanel::RenderEffectsList_()
{
    ImGui::TextUnformatted("Merged effects catalog");
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

void EffectsPanel::RenderCatalogSources_()
{
    const auto sources = director_.GetCatalogSourcesSnapshot();
    ImGui::Text("Catalog sources (%zu)", sources.size());
    ImGui::BeginChild("effects_catalog_sources", ImVec2(0.0f, 150.0f), true);
    for (int i = 0; i < static_cast<int>(sources.size()); ++i) {
        const auto& source = sources[i];
        char label[160]{};
        std::snprintf(label, sizeof(label), "%s (%zu)", source.label.c_str(), source.names.size());
        if (ImGui::Selectable(label, selectedCatalogSource_ == i)) {
            selectedCatalogSource_ = i;
        }
    }
    ImGui::EndChild();

    if (selectedCatalogSource_ >= 0 && selectedCatalogSource_ < static_cast<int>(sources.size())) {
        const auto& source = sources[selectedCatalogSource_];
        ImGui::TextWrapped("%s", source.label.c_str());
        ImGui::BeginChild("effects_catalog_source_entries", ImVec2(0.0f, 160.0f), true);
        for (const std::string& effectName : source.names) {
            if (filterInput_[0] != '\0' && effectName.find(filterInput_.data()) == std::string::npos) {
                continue;
            }
            if (ImGui::Selectable(effectName.c_str(), false)) {
                std::snprintf(spawnInput_.data(), spawnInput_.size(), "%s", effectName.c_str());
            }
        }
        ImGui::EndChild();
    }
}

void EffectsPanel::RenderRecentEvents_()
{
    ImGui::Text("Console (%zu lines)", director_.GetRecentEventCount());
    ImGui::SameLine();
    if (ImGui::Button("Clear console")) {
        director_.ClearRecentEvents();
    }

    const auto recentEvents = director_.GetRecentEventsSnapshot();

    ImGui::BeginChild("recent_effect_events", ImVec2(0.0f, 180.0f), true);
    for (const std::string& line : recentEvents) {
        ImGui::TextWrapped("%s", line.c_str());
    }
    ImGui::EndChild();
}
