#pragma once

#include <cstdint>

class VersionDetection
{
public:
    static VersionDetection& GetInstance();

    [[nodiscard]] uint16_t GetGameVersion() const noexcept;

private:
    VersionDetection();

    uint16_t gameVersion_;
};

