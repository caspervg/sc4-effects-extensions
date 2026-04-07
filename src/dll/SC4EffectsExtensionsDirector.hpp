#pragma once

#include <cstddef>
#include <deque>
#include <cRZMessage2COMDirector.h>
#include <filesystem>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include "public/cIGZImGuiService.h"

class EffectsPanel;
class cIGZMessage2;
class cIGZCOM;
class cIGZDBSegmentPackedFile;
class cIGZMessageServer2;
class cIGZMessage2Standard;
class cISC4City;
class cISC4EffectsManager;
class cISC4VisualEffect;

class SC4EffectsExtensionsDirector final : public cRZMessage2COMDirector
{
public:
    struct EffectsCatalogSource {
        std::string label;
        ptrdiff_t vectorOffset = 0;
        size_t elementSize = 0;
        size_t stringOffset = 0;
        std::vector<std::string> names;
    };

    struct TrackedEffectState {
        bool active = false;
        std::string name;
        float position[3] = {512.0f, 280.0f, 512.0f};
        float rotation[3] = {0.0f, 0.0f, 0.0f};
        float scale = 1.0f;
        bool dirty = false;
    };

    SC4EffectsExtensionsDirector();
    ~SC4EffectsExtensionsDirector() override;

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

    [[nodiscard]] bool IsCityLoaded() const;
    [[nodiscard]] bool IsEffectsHookInstalled() const;
    [[nodiscard]] size_t GetRecentEventCount() const;
    [[nodiscard]] size_t GetKnownEffectCount() const;
    [[nodiscard]] std::vector<std::string> GetRecentEventsSnapshot() const;
    [[nodiscard]] std::vector<std::string> GetKnownEffectsSnapshot() const;
    [[nodiscard]] std::vector<EffectsCatalogSource> GetCatalogSourcesSnapshot() const;
    [[nodiscard]] std::string GetEffectsStatsString() const;
    [[nodiscard]] std::string GetLastSpawnStatus() const;
    [[nodiscard]] TrackedEffectState GetTrackedEffectState() const;

    void ClearRecentEvents();
    bool SpawnEffectByName(const char* effectName);
    bool SpawnTrackedEffectByName(const char* effectName, const TrackedEffectState& state);
    bool UpdateTrackedEffectTransform(const TrackedEffectState& state);
    void StopTrackedEffect();
    void RecordHookEvent(std::string_view line);
    bool RefreshKnownEffects();
    bool DumpManagerMemory();

private:
    void PostCityInit_(const cIGZMessage2Standard* pStandardMsg);
    void PreCityShutdown_();
    static std::filesystem::path GetUserPluginsPath_();
    void InitializeLogger_();
    void PushEventLine_(std::string line);
    void DumpKnownEffectsToLog_(const std::vector<std::string>& names, const std::vector<EffectsCatalogSource>& sources) const;
    bool RefreshKnownEffects_();
    bool EnsurePackedEffectsSaveSegment_();
    void ReleasePackedEffectsSaveSegment_() noexcept;

private:
    cIGZImGuiService* imguiService_ = nullptr;
    cIGZMessageServer2* messageServer2_ = nullptr;
    cISC4City* city_ = nullptr;
    cISC4EffectsManager* effectsManager_ = nullptr;
    cISC4VisualEffect* trackedEffect_ = nullptr;
    cIGZDBSegmentPackedFile* packedEffectsSegment_ = nullptr;
    std::unique_ptr<EffectsPanel> panel_;
    bool panelRegistered_ = false;
    bool effectsHookInstalled_ = false;
    bool packedEffectsSegmentRegistered_ = false;
    mutable std::mutex effectsMutex_;
    std::deque<std::string> recentEvents_;
    std::vector<std::string> knownEffects_;
    std::vector<EffectsCatalogSource> catalogSources_;
    std::string lastSpawnStatus_;
    TrackedEffectState trackedEffectState_;
    std::filesystem::path packedEffectsOutputPath_;
};
