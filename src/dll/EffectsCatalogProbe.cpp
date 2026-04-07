#include "EffectsCatalogProbe.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>

#include "cISC4EffectsManager.h"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <Windows.h>

namespace {
constexpr size_t kMaxHashBucketCount = 32768;

bool IsReadableRange(const void* address, const size_t size) noexcept
{
    if (!address || size == 0) return false;

    MEMORY_BASIC_INFORMATION mbi{};
    if (VirtualQuery(address, &mbi, sizeof(mbi)) != sizeof(mbi)) return false;
    if (mbi.State != MEM_COMMIT) return false;
    if ((mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) != 0) return false;

    const auto start = reinterpret_cast<uintptr_t>(address);
    const auto end = start + size;
    const auto regionStart = reinterpret_cast<uintptr_t>(mbi.BaseAddress);
    const auto regionEnd = regionStart + mbi.RegionSize;

    return end >= start && end <= regionEnd;
}

bool TryReadUint32(const void* address, uint32_t& out) noexcept
{
    if (!IsReadableRange(address, sizeof(uint32_t))) return false;

    __try {
        out = *reinterpret_cast<const uint32_t*>(address);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool IsPlausibleEffectNameChar(const unsigned char ch) noexcept
{
    return std::isalnum(ch) || ch == '_' || ch == '-' || ch == '.' || ch == '/';
}

bool TryReadStringSpan(const uint32_t begin, const uint32_t end, std::string& out) noexcept
{
    out.clear();
    if (begin == 0 || end < begin) return false;

    const size_t length = static_cast<size_t>(end - begin);
    if (length == 0 || length > 128) return false;
    if (!IsReadableRange(reinterpret_cast<const void*>(begin), length)) return false;

    const auto* text = reinterpret_cast<const char*>(begin);
    for (size_t i = 0; i < length; ++i) {
        char ch = 0;
        __try {
            ch = text[i];
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            return false;
        }
        if (!IsPlausibleEffectNameChar(static_cast<unsigned char>(ch))) return false;
    }

    out.assign(text, length);
    return true;
}
}

EffectsCatalogSnapshot EffectsCatalogProbe::ProbePrimaryHash(cISC4EffectsManager* const effectsManager) noexcept
{
    EffectsCatalogSnapshot snapshot{};
    if (!effectsManager) return snapshot;

    auto* const manager = reinterpret_cast<const uint8_t*>(effectsManager);
    auto* const collection = manager + 0x98;

    uint32_t bucketsBegin = 0;
    uint32_t bucketsEnd = 0;
    if (!TryReadUint32(collection + 0x4, bucketsBegin)) return snapshot;
    if (!TryReadUint32(collection + 0x8, bucketsEnd)) return snapshot;
    if (bucketsBegin == 0 || bucketsEnd <= bucketsBegin) return snapshot;

    const size_t bucketCount = (bucketsEnd - bucketsBegin) / sizeof(uint32_t);
    if (bucketCount == 0 || bucketCount > kMaxHashBucketCount) return snapshot;
    if (!IsReadableRange(reinterpret_cast<const void*>(bucketsBegin), bucketCount * sizeof(uint32_t))) return snapshot;

    snapshot.names.reserve(bucketCount);
    for (size_t bucketIndex = 0; bucketIndex < bucketCount; ++bucketIndex) {
        uint32_t node = 0;
        if (!TryReadUint32(reinterpret_cast<const void*>(bucketsBegin + (bucketIndex * sizeof(uint32_t))), node)) continue;

        size_t chainDepth = 0;
        while (node && chainDepth < 8192) {
            uint32_t next = 0;
            uint32_t strBegin = 0;
            uint32_t strEnd = 0;
            if (!TryReadUint32(reinterpret_cast<const void*>(node), next)) break;
            if (!TryReadUint32(reinterpret_cast<const void*>(node + 4), strBegin)) break;
            if (!TryReadUint32(reinterpret_cast<const void*>(node + 8), strEnd)) break;

            std::string name;
            if (TryReadStringSpan(strBegin, strEnd, name) && effectsManager->HasVisualEffect(name.c_str())) {
                snapshot.names.push_back(std::move(name));
            }

            node = next;
            ++chainDepth;
        }
    }

    std::sort(snapshot.names.begin(), snapshot.names.end());
    snapshot.names.erase(std::unique(snapshot.names.begin(), snapshot.names.end()), snapshot.names.end());

    if (snapshot.names.size() >= 8) {
        EffectsCatalogSource source{};
        source.label = "Primary collection object +0x98 (hash at +0x04)";
        source.vectorOffset = 0x9C;
        source.elementSize = 0x0C;
        source.stringOffset = 0x04;
        source.names = snapshot.names;
        snapshot.sources.push_back(std::move(source));
    } else {
        snapshot.names.clear();
    }

    return snapshot;
}
