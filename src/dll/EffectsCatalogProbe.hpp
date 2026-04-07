#pragma once

#include <cstddef>
#include <string>
#include <vector>

class cISC4EffectsManager;

struct EffectsCatalogSource
{
    std::string label;
    ptrdiff_t vectorOffset = 0;
    size_t elementSize = 0;
    size_t stringOffset = 0;
    std::vector<std::string> names;
};

struct EffectsCatalogSnapshot
{
    std::vector<EffectsCatalogSource> sources;
    std::vector<std::string> names;
};

class EffectsCatalogProbe final
{
public:
    static EffectsCatalogSnapshot ProbePrimaryHash(cISC4EffectsManager* effectsManager) noexcept;
};
