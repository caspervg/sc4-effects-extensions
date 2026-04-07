#pragma once

#include <cmath>
#include <cstdint>

#include "cS3DVector3.h"

class cS3DTransform {
public:
    uint8_t opCount = 0;
    uint8_t flags = 0;
    uint8_t reserved1 = 0;
    uint8_t reserved2 = 0;
    float matrix[9] = {
        1.0f, 0.0f, 0.0f,
        0.0f, 1.0f, 0.0f,
        0.0f, 0.0f, 1.0f,
    };
    cS3DVector3 translation{};
    float scale = 1.0f;
};

struct EffectTransformParams {
    float position[3] = {0.0f, 0.0f, 0.0f};
    float rotation[3] = {0.0f, 0.0f, 0.0f};
    float scale = 1.0f;
};

namespace EffectsTransformUtil {
inline constexpr float kPi = 3.14159265358979323846f;

inline float DegreesToRadians(const float value) noexcept {
    return value * (kPi / 180.0f);
}

inline void Multiply3x3(const float* lhs, const float* rhs, float* out) noexcept {
    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
            out[row * 3 + col] =
                (lhs[row * 3 + 0] * rhs[0 * 3 + col]) +
                (lhs[row * 3 + 1] * rhs[1 * 3 + col]) +
                (lhs[row * 3 + 2] * rhs[2 * 3 + col]);
        }
    }
}

inline void BuildRotationMatrixXYZ(const float pitchDegrees, const float yawDegrees, const float rollDegrees, float* out) noexcept {
    const float pitch = DegreesToRadians(pitchDegrees);
    const float yaw = DegreesToRadians(yawDegrees);
    const float roll = DegreesToRadians(rollDegrees);

    const float cx = std::cos(pitch);
    const float sx = std::sin(pitch);
    const float cy = std::cos(yaw);
    const float sy = std::sin(yaw);
    const float cz = std::cos(roll);
    const float sz = std::sin(roll);

    const float rotX[9] = {
        1.0f, 0.0f, 0.0f,
        0.0f, cx,   -sx,
        0.0f, sx,   cx,
    };
    const float rotY[9] = {
        cy,   0.0f, sy,
        0.0f, 1.0f, 0.0f,
        -sy,  0.0f, cy,
    };
    const float rotZ[9] = {
        cz,   -sz,  0.0f,
        sz,   cz,   0.0f,
        0.0f, 0.0f, 1.0f,
    };

    float temp[9]{};
    Multiply3x3(rotZ, rotY, temp);
    Multiply3x3(temp, rotX, out);
}

inline void Apply(cS3DTransform& transform, const EffectTransformParams& params) noexcept {
    transform.translation = cS3DVector3(params.position[0], params.position[1], params.position[2]);
    BuildRotationMatrixXYZ(params.rotation[0], params.rotation[1], params.rotation[2], transform.matrix);
    transform.scale = params.scale;

    transform.flags = 0x01;
    transform.opCount = 1;
    if (params.scale != 1.0f) {
        transform.flags |= 0x02;
        ++transform.opCount;
    }
    if (params.rotation[0] != 0.0f || params.rotation[1] != 0.0f || params.rotation[2] != 0.0f) {
        transform.flags |= 0x04;
        ++transform.opCount;
    }
}
}
