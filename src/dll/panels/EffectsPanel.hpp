#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "imgui.h"
#include "public/ImGuiPanel.h"

class SC4EffectsExtensionsDirector;
class TextEditor;

class EffectsPanel final : public ImGuiPanel
{
public:
    explicit EffectsPanel(SC4EffectsExtensionsDirector& director);
    ~EffectsPanel() override;

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

    struct EditorFileState {
        int cursorLine = 0;
        int cursorColumn = 0;
    };

    void RenderWorkspace_();
    void RenderWorkspaceRightPane_();
    void RenderManualSpawn_();
    void RenderTrackedEffect_();
    void RenderEditor_();
    void RenderRecentEvents_();
    void EnsureEditorSelection_();
    void SaveCurrentEditorState_();
    void LoadSelectedFxFile_();
    bool SaveSelectedFxFile_(bool refreshCatalog);
    void RestoreEditorState_(const std::filesystem::path& path);
    void ClearEditorDiagnostics_();
    void ApplyRefreshDiagnostics_(size_t eventCountBeforeRefresh);

private:
    SC4EffectsExtensionsDirector& director_;
    bool visible_ = true;
    uint16_t detectedGameVersion_ = 0;
    std::string versionLabel_ = "dev";
    std::array<char, 128> spawnInput_{};
    std::array<char, 128> filterInput_{};
    TrackedTransformUiState trackedState_{};
    bool autoApplyTrackedTransform_ = true;
    std::vector<std::filesystem::path> fxFiles_{};
    int selectedFxFileIndex_ = -1;
    std::filesystem::path loadedFxFilePath_;
    std::unordered_map<std::wstring, EditorFileState> editorFileStates_{};
    std::unique_ptr<TextEditor> editor_;
    bool editorDirty_ = false;
};
