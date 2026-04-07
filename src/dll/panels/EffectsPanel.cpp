#include "EffectsPanel.hpp"

#include <cstdio>
#include <memory>

#include "TextEditor.h"
#include "../SC4EffectsExtensionsDirector.hpp"

namespace
{
const TextEditor::LanguageDefinition& GetSc4FxLanguageDefinition()
{
    static TextEditor::LanguageDefinition languageDefinition = [] {
        TextEditor::LanguageDefinition definition;
        definition.mName = "SC4 FX";
        definition.mCaseSensitive = false;
        definition.mAutoIndentation = true;
        definition.mCommentStart = "/*";
        definition.mCommentEnd = "*/";
        definition.mSingleLineComment = "//";

        definition.mKeywords = {
            "alpha",
            "aspect",
            "attractor",
            "automataEffect",
            "brushEffect",
            "cameraEffect",
            "color",
            "decal",
            "decalEffect",
            "dynamicParticles",
            "effect",
            "effectsResource",
            "emit",
            "flashEffect",
            "length",
            "life",
            "light",
            "loadResource",
            "model",
            "modelID",
            "particleEffect",
            "particles",
            "play",
            "rate",
            "scrubberEffect",
            "sequence",
            "sequenceEffect",
            "shakeEffect",
            "size",
            "soundEffect",
            "source",
            "strength",
            "testEffect",
            "texture",
            "textureID",
            "tintEffect",
            "vector",
            "visualEffect",
            "wait"
        };

        definition.mIdentifiers = {
            {"-draw", {}},
            {"-emitScale", {}},
            {"-epicentre", {}},
            {"-hard", {}},
            {"-hardStart", {}},
            {"-lod", {}},
            {"-lodRange", {}},
            {"-loop", {}},
            {"-noAutoStop", {}},
            {"-noOverlap", {}},
            {"-offset", {}},
            {"-rotate", {}},
            {"-rotateX", {}},
            {"-rotateY", {}},
            {"-rotateZ", {}},
            {"-scale", {}},
            {"-sizeScale", {}},
            {"-sortOffset", {}},
            {"-sourceScale", {}}
        };

        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("L?\\\"(\\\\.|[^\\\"])*\\\"", TextEditor::PaletteIndex::String));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("0[xX][0-9a-fA-F]+", TextEditor::PaletteIndex::Number));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?", TextEditor::PaletteIndex::Number));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("-[a-zA-Z_][a-zA-Z0-9_]*", TextEditor::PaletteIndex::KnownIdentifier));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("[a-zA-Z_][a-zA-Z0-9_]*", TextEditor::PaletteIndex::Identifier));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("[\\[\\]\\{\\}\\!\\%\\^\\&\\*\\(\\)\\-\\+\\=\\~\\|\\<\\>\\?\\/\\;\\,\\.]", TextEditor::PaletteIndex::Punctuation));

        return definition;
    }();

    return languageDefinition;
}
}

EffectsPanel::EffectsPanel(SC4EffectsExtensionsDirector& director)
    : director_(director)
    , editor_(std::make_unique<TextEditor>())
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

    editor_->SetLanguageDefinition(GetSc4FxLanguageDefinition());
    editor_->SetPalette(TextEditor::GetDarkPalette());
    editor_->SetShowWhitespaces(false);
}

EffectsPanel::~EffectsPanel() = default;

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
    ImGui::SetNextWindowSize(ImVec2(1180.0f, 780.0f), ImGuiCond_FirstUseEver);
    if (ImGui::Begin("SC4 Effects Console", &open)) {
        RenderWorkspace_();
    }
    ImGui::End();
    visible_ = open;
}

void EffectsPanel::RenderWorkspace_()
{
    EnsureEditorSelection_();
    editorDirty_ = editor_ && editor_->IsTextChanged();

    const float consoleHeight = 220.0f;
    const float topHeight = std::max(120.0f, ImGui::GetContentRegionAvail().y - consoleHeight - ImGui::GetStyle().ItemSpacing.y);
    const float leftWidth = 360.0f;

    ImGui::BeginChild("workspace_top", ImVec2(0.0f, topHeight), false);
    ImGui::BeginChild("workspace_left", ImVec2(leftWidth, 0.0f), true);
    RenderWorkspaceLeftPane_();
    ImGui::EndChild();

    ImGui::SameLine();

    ImGui::BeginChild("workspace_right", ImVec2(0.0f, 0.0f), true);
    RenderWorkspaceRightPane_();
    ImGui::EndChild();
    ImGui::EndChild();

    ImGui::Spacing();
    ImGui::BeginChild("workspace_console", ImVec2(0.0f, 0.0f), true);
    RenderRecentEvents_();
    ImGui::EndChild();
}

void EffectsPanel::RenderWorkspaceLeftPane_()
{
    RenderManualSpawn_();
    ImGui::Separator();
    RenderTrackedEffect_();
    ImGui::Separator();
    RenderEffectsList_();
}

void EffectsPanel::RenderWorkspaceRightPane_()
{
    RenderEditor_();
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
    if (ImGui::Button("Refresh")) {
        director_.RefreshKnownEffects();
    }

    const auto effects = director_.GetKnownEffectsSnapshot();
    const std::string filter = filterInput_.data();

    ImGui::BeginChild("effects_catalog", ImVec2(0.0f, 0.0f), true);
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

void EffectsPanel::RenderEditor_()
{
    const bool hasFile = selectedFxFileIndex_ >= 0 && selectedFxFileIndex_ < static_cast<int>(fxFiles_.size());

    if (ImGui::Button("Refresh files")) {
        fxFiles_ = director_.GetPluginFxFiles();
        if (selectedFxFileIndex_ >= static_cast<int>(fxFiles_.size())) {
            selectedFxFileIndex_ = fxFiles_.empty() ? -1 : 0;
        }
        LoadSelectedFxFile_();
    }

    ImGui::SameLine();
    ImGui::BeginDisabled(!hasFile);
    if (ImGui::Button("Reload file")) {
        LoadSelectedFxFile_();
    }
    ImGui::EndDisabled();

    ImGui::SameLine();
    ImGui::BeginDisabled(!hasFile);
    if (ImGui::Button("Save")) {
        SaveSelectedFxFile_(false);
    }
    ImGui::EndDisabled();

    ImGui::SameLine();
    ImGui::BeginDisabled(!hasFile);
    if (ImGui::Button("Save + Refresh")) {
        SaveSelectedFxFile_(true);
    }
    ImGui::EndDisabled();

    if (!loadedFxFilePath_.empty()) {
        ImGui::SameLine();
        ImGui::TextUnformatted(editorDirty_ ? "modified" : "saved");
    }

    ImGui::Separator();

    ImGui::BeginChild("fx_file_list", ImVec2(260.0f, 0.0f), true);
    for (int i = 0; i < static_cast<int>(fxFiles_.size()); ++i) {
        const auto label = fxFiles_[i].filename().string();
        if (ImGui::Selectable(label.c_str(), selectedFxFileIndex_ == i)) {
            selectedFxFileIndex_ = i;
            LoadSelectedFxFile_();
        }
        if (ImGui::IsItemHovered()) {
            ImGui::SetTooltip("%s", fxFiles_[i].string().c_str());
        }
    }
    ImGui::EndChild();

    ImGui::SameLine();

    ImGui::BeginChild("fx_editor_host", ImVec2(0.0f, 0.0f), false);
    if (loadedFxFilePath_.empty()) {
        ImGui::TextUnformatted("No .fx file selected.");
    } else {
        ImGui::TextWrapped("%s", loadedFxFilePath_.string().c_str());
        editor_->Render("##fx_editor", ImVec2(-1.0f, -1.0f), false);

        const bool editorFocused = ImGui::IsWindowFocused(ImGuiFocusedFlags_ChildWindows);
        const bool ctrlPressed = ImGui::GetIO().KeyCtrl;
        const bool shiftPressed = ImGui::GetIO().KeyShift;
        if (hasFile && editorFocused && ctrlPressed && ImGui::IsKeyPressed(ImGuiKey_S, false)) {
            SaveSelectedFxFile_(shiftPressed);
        }
    }
    ImGui::EndChild();
}

void EffectsPanel::RenderRecentEvents_()
{
    ImGui::Text("Console (%zu lines)", director_.GetRecentEventCount());
    ImGui::SameLine();
    if (ImGui::Button("Clear")) {
        director_.ClearRecentEvents();
    }

    const auto recentEvents = director_.GetRecentEventsSnapshot();

    ImGui::BeginChild("recent_effect_events", ImVec2(0.0f, 0.0f), true);
    for (const auto& event : recentEvents) {
        if (event.severity == SC4EffectsExtensionsDirector::EventSeverity::Success) {
            ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.20f, 0.72f, 0.33f, 1.0f));
        } else if (event.severity == SC4EffectsExtensionsDirector::EventSeverity::Error) {
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

void EffectsPanel::EnsureEditorSelection_()
{
    if (fxFiles_.empty()) {
        fxFiles_ = director_.GetPluginFxFiles();
        if (!fxFiles_.empty() && selectedFxFileIndex_ < 0) {
            selectedFxFileIndex_ = 0;
            LoadSelectedFxFile_();
        }
    }
}

void EffectsPanel::LoadSelectedFxFile_()
{
    loadedFxFilePath_.clear();
    editorDirty_ = false;

    if (selectedFxFileIndex_ < 0 || selectedFxFileIndex_ >= static_cast<int>(fxFiles_.size())) {
        if (editor_) {
            editor_->SetText({});
        }
        return;
    }

    std::string contents;
    if (!director_.ReadPluginFxFile(fxFiles_[selectedFxFileIndex_], contents)) {
        if (editor_) {
            editor_->SetText({});
        }
        return;
    }

    loadedFxFilePath_ = fxFiles_[selectedFxFileIndex_];
    editor_->SetText(contents);
}

bool EffectsPanel::SaveSelectedFxFile_(const bool refreshCatalog)
{
    if (!editor_ || selectedFxFileIndex_ < 0 || selectedFxFileIndex_ >= static_cast<int>(fxFiles_.size())) {
        return false;
    }

    if (!director_.WritePluginFxFile(fxFiles_[selectedFxFileIndex_], editor_->GetText())) {
        return false;
    }

    editorDirty_ = false;
    if (refreshCatalog) {
        director_.RefreshKnownEffects();
    }

    return true;
}
