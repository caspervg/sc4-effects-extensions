#include "HelloPanel.hpp"

void HelloPanel::SetDetectedGameVersion(const uint16_t version)
{
    detectedGameVersion_ = version;
}

void HelloPanel::SetVersionLabel(const char* version)
{
    versionLabel_ = version ? version : "dev";
}

void HelloPanel::SetVisible(const bool visible)
{
    visible_ = visible;
}

void HelloPanel::OnVisibleChanged(const bool visible)
{
    visible_ = visible;
}

void HelloPanel::OnRender()
{
    if (!visible_) {
        return;
    }

    bool open = visible_;
    ImGui::SetNextWindowSize(ImVec2(420.0f, 0.0f), ImGuiCond_FirstUseEver);
    if (ImGui::Begin("SC4 Template DLL", &open)) {
        ImGui::TextUnformatted("Starter panel from the template repository.");
        ImGui::Separator();
        ImGui::Text("DLL version: %s", versionLabel_.c_str());
        ImGui::Text("Detected game version: %u", detectedGameVersion_);
        ImGui::Spacing();
        ImGui::TextWrapped("Replace this panel and the director hooks with your plugin-specific logic.");
    }
    ImGui::End();
    visible_ = open;
}
