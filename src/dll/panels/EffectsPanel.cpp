#include "EffectsPanel.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <initializer_list>
#include <memory>
#include <optional>
#include <regex>
#include <string.h>
#include <string>

#include "TextEditor.h"
#include "../SC4EffectsExtensionsDirector.hpp"

namespace
{
std::string NormalizeEditorToken(std::string value)
{
    std::transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char ch) {
            return static_cast<char>(std::toupper(ch));
        });
    return value;
}

std::optional<int> TryExtractLineNumberForFile(const std::string& text, const std::filesystem::path& filePath)
{
    if (text.empty() || filePath.empty()) {
        return std::nullopt;
    }

    const std::string fullPath = filePath.string();
    const std::string fileName = filePath.filename().string();

    const std::regex fileLinePattern(R"(([^:\r\n]+\.fx)[(: ]+([0-9]+))", std::regex_constants::icase);
    for (std::sregex_iterator it(text.begin(), text.end(), fileLinePattern), end; it != end; ++it) {
        const std::string matchedPath = (*it)[1].str();
        if (_stricmp(matchedPath.c_str(), fullPath.c_str()) == 0 || _stricmp(matchedPath.c_str(), fileName.c_str()) == 0) {
            return std::max(1, std::stoi((*it)[2].str()));
        }
    }

    const std::regex genericLinePattern(R"(\bline\s+([0-9]+)\b)", std::regex_constants::icase);
    std::smatch genericMatch;
    if ((text.find(fullPath) != std::string::npos || text.find(fileName) != std::string::npos)
        && std::regex_search(text, genericMatch, genericLinePattern)) {
        return std::max(1, std::stoi(genericMatch[1].str()));
    }

    return std::nullopt;
}

std::string ToggleSc4BlockComment(std::string text)
{
    const size_t first = text.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "#<\n#>";
    }

    const size_t last = text.find_last_not_of(" \t\r\n");
    const bool hasOpen = first + 2 <= text.size() && text.compare(first, 2, "#<") == 0;
    const bool hasClose = last != std::string::npos && last >= 1 && text.compare(last - 1, 2, "#>") == 0;

    if (hasOpen && hasClose) {
        text.erase(last - 1, 2);
        text.erase(first, 2);

        if (first < text.size() && text[first] == '\n') {
            text.erase(first, 1);
        }
        if (!text.empty()) {
            const size_t closePos = text.find_last_not_of(" \t\r\n");
            if (closePos != std::string::npos && closePos + 1 < text.size() && text[closePos + 1] == '\n') {
                text.erase(closePos + 1, 1);
            }
        }

        return text;
    }

    return "#<\n" + text + "\n#>";
}

const TextEditor::LanguageDefinition& GetSc4FxLanguageDefinition()
{
    static TextEditor::LanguageDefinition languageDefinition = [] {
        TextEditor::LanguageDefinition definition;
        definition.mName = "SC4 FX";
        definition.mCaseSensitive = false;
        definition.mAutoIndentation = true;
        definition.mCommentStart = "#<";
        definition.mCommentEnd = "#>";
        definition.mSingleLineComment.clear();
        definition.mPreprocChar = '\0';

        const auto addKeywords = [&definition](std::initializer_list<const char*> keywords) {
            for (const char* keyword : keywords) {
                definition.mKeywords.insert(NormalizeEditorToken(keyword));
            }
        };

        const auto addIdentifiers = [&definition](std::initializer_list<const char*> identifiers, const char* declaration) {
            for (const char* identifier : identifiers) {
                TextEditor::Identifier id;
                id.mDeclaration = declaration;
                definition.mIdentifiers.insert(std::make_pair(NormalizeEditorToken(identifier), id));
            }
        };

        addKeywords({
            "alpha", "alpha255", "align", "amplitude", "aspect", "automataEffect", "brushEffect",
            "brushID", "camera", "cameraEffect", "chainEffect", "color", "color255", "collide",
            "collision", "colour", "colour255", "create", "decal", "decalEffect", "define",
            "demolishEffect", "dynamicParticle", "dynamicParticleEffect", "effect", "effectBase",
            "effectGroup", "effectID", "effectsResource", "emit", "end", "enddef", "eval",
            "flashEffect", "force", "frequency", "friction", "gameEffect", "inject", "instance",
            "length", "life", "light", "loadResource", "maintain", "mass", "messageTrigger",
            "model", "modelID", "namespace", "option", "optionGroup", "particleEffect",
            "particleSequence", "particles", "play", "property", "randomWalk", "rate",
            "rotate", "rule", "scrubberEffect", "select", "sequence", "sequenceEffect",
            "set", "setc", "setf", "seti", "setPriority", "setv3", "shake", "shakeAspect",
            "shakeEffect", "size", "soundEffect", "soundID", "source", "strength", "stretch",
            "table", "terrainRepel", "testEffect", "texture", "textureID", "timedEffect",
            "tintEffect", "vendor", "visualEffect", "wait", "warp", "zoom"
        });

        addIdentifiers({
            "alpha", "alpha255", "align", "amplitude", "aspect", "automataEffect", "brushEffect",
            "brushID", "camera", "cameraEffect", "chainEffect", "color", "color255", "collide",
            "collision", "colour", "colour255", "create", "decal", "decalEffect", "define",
            "demolishEffect", "dynamicParticle", "dynamicParticleEffect", "effect", "effectBase",
            "effectGroup", "effectID", "effectsResource", "emit", "end", "enddef", "eval",
            "flashEffect", "force", "frequency", "friction", "gameEffect", "inject", "instance",
            "length", "life", "light", "loadResource", "maintain", "mass", "messageTrigger",
            "model", "modelID", "namespace", "particleEffect", "particleSequence", "particles",
            "play", "randomWalk", "rate", "rotate", "scrubberEffect", "select", "sequence",
            "sequenceEffect", "set", "setc", "setf", "seti", "setPriority", "setv3", "shake",
            "shakeAspect", "shakeEffect", "size", "soundEffect", "soundID", "source", "strength",
            "stretch", "table", "terrainRepel", "testEffect", "texture", "textureID",
            "timedEffect", "tintEffect", "visualEffect", "wait", "warp", "zoom"
        }, "SC4 FX keyword");

        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("L?\\\"(\\\\.|[^\\\"])*\\\"", TextEditor::PaletteIndex::String));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("0[xX][0-9a-fA-F]+", TextEditor::PaletteIndex::Number));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?", TextEditor::PaletteIndex::Number));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("\\$\\{?[a-zA-Z_][a-zA-Z0-9_]*(?::[a-zA-Z_][a-zA-Z0-9_]*)?\\}?", TextEditor::PaletteIndex::PreprocIdentifier));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("%\\{?[a-zA-Z_][a-zA-Z0-9_]*(?::[a-zA-Z_][a-zA-Z0-9_]*)?\\}?", TextEditor::PaletteIndex::Preprocessor));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("-[a-zA-Z_][a-zA-Z0-9_]*", TextEditor::PaletteIndex::KnownIdentifier));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("[a-zA-Z_][a-zA-Z0-9_]*", TextEditor::PaletteIndex::Identifier));
        definition.mTokenRegexStrings.push_back(
            std::make_pair<std::string, TextEditor::PaletteIndex>("[\\[\\]\\{\\}\\!\\%\\^\\&\\*\\(\\)\\-\\+\\=\\~\\|\\<\\>\\?\\/\\;\\,\\.\\:]", TextEditor::PaletteIndex::Punctuation));

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
    editor_->SetTabSize(2);
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

    ImGui::BeginChild("workspace_top", ImVec2(0.0f, topHeight), false);
    RenderWorkspaceRightPane_();
    ImGui::EndChild();

    ImGui::Spacing();
    ImGui::BeginChild("workspace_console", ImVec2(0.0f, 0.0f), true);
    RenderRecentEvents_();
    ImGui::EndChild();
}

void EffectsPanel::RenderWorkspaceRightPane_()
{
    RenderManualSpawn_();
    ImGui::Separator();
    RenderTrackedEffect_();
    ImGui::Separator();
    RenderEditor_();
}

void EffectsPanel::RenderManualSpawn_()
{
    ImGui::TextUnformatted("Spawn");
    ImGui::SameLine();
    ImGui::SetNextItemWidth(280.0f);
    ImGui::InputTextWithHint("##spawn_effect_name", "Effect name", spawnInput_.data(), spawnInput_.size());

    const auto effects = director_.GetKnownEffectsSnapshot();
    const std::string filter = filterInput_.data();
    std::string selectedLabel = spawnInput_.data();
    if (selectedLabel.empty()) {
        selectedLabel = "<select parsed effect>";
    }

    ImGui::SameLine();
    ImGui::SetNextItemWidth(260.0f);
    if (ImGui::BeginCombo("##parsed_effects", selectedLabel.c_str(), ImGuiComboFlags_HeightLarge)) {
        ImGui::SetNextItemWidth(-1.0f);
        ImGui::InputTextWithHint("##effect_filter", "Filter effects", filterInput_.data(), filterInput_.size());
        ImGui::Separator();

        int visibleCount = 0;
        for (const std::string& effectName : effects) {
            if (!filter.empty() && effectName.find(filter) == std::string::npos) {
                continue;
            }

            ++visibleCount;
            const bool selected = selectedLabel == effectName;
            if (ImGui::Selectable(effectName.c_str(), selected)) {
                std::snprintf(spawnInput_.data(), spawnInput_.size(), "%s", effectName.c_str());
            }
            if (selected) {
                ImGui::SetItemDefaultFocus();
            }
        }

        if (visibleCount == 0) {
            ImGui::TextDisabled("No matching effects");
        }

        ImGui::EndCombo();
    }

    ImGui::SameLine();
    if (ImGui::Button("Spawn")) {
        director_.SpawnEffectByName(spawnInput_.data());
    }

    ImGui::SameLine();
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
    if (ImGui::Button("Refresh catalog")) {
        director_.RefreshKnownEffects();
    }

    ImGui::SameLine();
    ImGui::TextDisabled("%d parsed", static_cast<int>(effects.size()));

    const std::string lastStatus = director_.GetLastSpawnStatus();
    if (!lastStatus.empty()) {
        ImGui::SameLine();
        ImGui::TextWrapped("%s", lastStatus.c_str());
    }
}

void EffectsPanel::RenderTrackedEffect_()
{
    const auto trackedState = director_.GetTrackedEffectState();
    if (trackedState.active) {
        trackedState_.active = true;
    }

    ImGui::TextUnformatted("Tracked");
    ImGui::SameLine();
    if (trackedState.active) {
        ImGui::Text("Active: %s", trackedState.name.c_str());
    } else {
        ImGui::TextUnformatted("Active: none");
    }

    ImGui::SameLine();
    ImGui::Checkbox("Auto-apply", &autoApplyTrackedTransform_);

    bool changed = false;
    ImGui::SetNextItemWidth(250.0f);
    changed |= ImGui::DragFloat3("Pos", trackedState_.position, 1.0f);
    ImGui::SameLine();
    ImGui::SetNextItemWidth(250.0f);
    changed |= ImGui::DragFloat3("Rot", trackedState_.rotation, 1.0f);
    ImGui::SameLine();
    ImGui::SetNextItemWidth(110.0f);
    changed |= ImGui::DragFloat("Scale", &trackedState_.scale, 0.01f, 0.01f, 100.0f, "%.2f");

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

void EffectsPanel::RenderEditor_()
{
    const bool hasFile = selectedFxFileIndex_ >= 0 && selectedFxFileIndex_ < static_cast<int>(fxFiles_.size());
    const std::string selectedFileLabel = loadedFxFilePath_.empty()
        ? "<select .fx file>"
        : loadedFxFilePath_.filename().string();

    if (ImGui::Button("Refresh files")) {
        SaveCurrentEditorState_();
        fxFiles_ = director_.GetPluginFxFiles();
        if (selectedFxFileIndex_ >= static_cast<int>(fxFiles_.size())) {
            selectedFxFileIndex_ = fxFiles_.empty() ? -1 : 0;
        }
        LoadSelectedFxFile_();
    }

    ImGui::SameLine();
    ImGui::SetNextItemWidth(260.0f);
    if (ImGui::BeginCombo("##fx_file_selector", selectedFileLabel.c_str())) {
        for (int i = 0; i < static_cast<int>(fxFiles_.size()); ++i) {
            const auto label = fxFiles_[i].filename().string();
            const bool selected = selectedFxFileIndex_ == i;
            if (ImGui::Selectable(label.c_str(), selected)) {
                selectedFxFileIndex_ = i;
                LoadSelectedFxFile_();
            }
            if (ImGui::IsItemHovered()) {
                ImGui::SetTooltip("%s", fxFiles_[i].string().c_str());
            }
            if (selected) {
                ImGui::SetItemDefaultFocus();
            }
        }
        ImGui::EndCombo();
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
        SaveSelectedFxFile_(true);
    }
    ImGui::EndDisabled();

    if (!loadedFxFilePath_.empty()) {
        ImGui::SameLine();
        ImGui::TextUnformatted(editorDirty_ ? "modified" : "saved");
    }

    ImGui::Separator();

    ImGui::BeginChild("fx_editor_host", ImVec2(0.0f, 0.0f), false);
    if (loadedFxFilePath_.empty()) {
        ImGui::TextUnformatted("No .fx file selected.");
    } else {
        ImGui::TextWrapped("%s", loadedFxFilePath_.string().c_str());
        editor_->Render("##fx_editor", ImVec2(-1.0f, -1.0f), false);

        const bool editorFocused = ImGui::IsWindowFocused(ImGuiFocusedFlags_ChildWindows);
        const bool ctrlPressed = ImGui::GetIO().KeyCtrl;
        if (hasFile && editorFocused && ctrlPressed && ImGui::IsKeyPressed(ImGuiKey_S, false)) {
            SaveSelectedFxFile_(true);
        }
        if (editorFocused && ctrlPressed && ImGui::IsKeyPressed(ImGuiKey_Slash, false) && editor_->HasSelection()) {
            const std::string previousClipboard = ImGui::GetClipboardText() ? ImGui::GetClipboardText() : "";
            const std::string selectedText = editor_->GetSelectedText();
            editor_->Cut();
            editor_->InsertText(ToggleSc4BlockComment(selectedText));
            ImGui::SetClipboardText(previousClipboard.c_str());
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

void EffectsPanel::SaveCurrentEditorState_()
{
    if (!editor_ || loadedFxFilePath_.empty()) {
        return;
    }

    const auto cursor = editor_->GetCursorPosition();
    editorFileStates_[loadedFxFilePath_.native()] = EditorFileState{cursor.mLine, cursor.mColumn};
}

void EffectsPanel::RestoreEditorState_(const std::filesystem::path& path)
{
    if (!editor_ || path.empty()) {
        return;
    }

    const auto it = editorFileStates_.find(path.native());
    if (it == editorFileStates_.end()) {
        editor_->SetCursorPosition(TextEditor::Coordinates(0, 0));
        return;
    }

    editor_->SetCursorPosition(TextEditor::Coordinates(it->second.cursorLine, it->second.cursorColumn));
}

void EffectsPanel::ClearEditorDiagnostics_()
{
    if (!editor_) {
        return;
    }

    editor_->SetErrorMarkers({});
    editor_->SetBreakpoints({});
}

void EffectsPanel::ApplyRefreshDiagnostics_(const size_t eventCountBeforeRefresh)
{
    ClearEditorDiagnostics_();

    if (!editor_ || loadedFxFilePath_.empty()) {
        return;
    }

    const auto recentEvents = director_.GetRecentEventsSnapshot();
    const size_t eventCountAfterRefresh = director_.GetRecentEventCount();
    const size_t maxNewEvents = eventCountAfterRefresh > eventCountBeforeRefresh
        ? std::min(recentEvents.size(), eventCountAfterRefresh - eventCountBeforeRefresh)
        : recentEvents.size();

    TextEditor::ErrorMarkers markers;
    std::optional<int> firstLine;

    for (size_t i = 0; i < maxNewEvents && i < recentEvents.size(); ++i) {
        const auto& event = recentEvents[i];
        if (event.severity != SC4EffectsExtensionsDirector::EventSeverity::Error) {
            continue;
        }

        const auto lineNumber = TryExtractLineNumberForFile(event.text, loadedFxFilePath_);
        if (!lineNumber.has_value()) {
            continue;
        }

        const int zeroBasedLine = *lineNumber - 1;
        if (zeroBasedLine < 0) {
            continue;
        }

        markers.emplace(zeroBasedLine, event.text);
        if (!firstLine.has_value() || zeroBasedLine < *firstLine) {
            firstLine = zeroBasedLine;
        }
    }

    editor_->SetErrorMarkers(markers);
    if (firstLine.has_value()) {
        editor_->SetCursorPosition(TextEditor::Coordinates(*firstLine, 0));
    }
}

void EffectsPanel::LoadSelectedFxFile_()
{
    SaveCurrentEditorState_();
    loadedFxFilePath_.clear();
    editorDirty_ = false;
    ClearEditorDiagnostics_();

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
    RestoreEditorState_(loadedFxFilePath_);
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
    SaveCurrentEditorState_();

    if (refreshCatalog) {
        const size_t eventCountBeforeRefresh = director_.GetRecentEventCount();
        director_.RefreshKnownEffects();
        ApplyRefreshDiagnostics_(eventCountBeforeRefresh);
    } else {
        ClearEditorDiagnostics_();
    }

    return true;
}
