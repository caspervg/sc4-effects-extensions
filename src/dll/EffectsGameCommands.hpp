#pragma once

#include <cstdint>
#include <memory>

class SC4EffectsExtensionsDirector;
class cIGZCommandParameterSet;
class cIGZCommandServer;
class cIGZMessage2;
class cIGZMessageServer2;

class EffectsGameCommands final
{
public:
    explicit EffectsGameCommands(SC4EffectsExtensionsDirector& director);
    ~EffectsGameCommands();

    EffectsGameCommands(const EffectsGameCommands&) = delete;
    EffectsGameCommands& operator=(const EffectsGameCommands&) = delete;

    bool Install();
    bool HandleMessage(cIGZMessage2* message);

private:
    void Uninstall() noexcept;
    int32_t Execute(uint32_t commandId, cIGZCommandParameterSet* input, cIGZCommandParameterSet* output);

    SC4EffectsExtensionsDirector& director_;
    cIGZCommandServer* commandServer_ = nullptr;
    cIGZMessageServer2* messageServer_ = nullptr;
    uint32_t notificationCount_ = 0;
};
