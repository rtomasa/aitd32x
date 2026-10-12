// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/types.hpp"

// Call only after the caller's near-plane test. Keep exact signed quotients;
// world coordinates clamp to +/-4096, presentation/effects remain unclamped.
Point RenderProject(const Vec3 &vertex,int focal_x,int focal_y,Point center,bool clamp=true);
