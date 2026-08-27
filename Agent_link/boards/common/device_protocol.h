#pragma once

#include <cstddef>
#include <cstdint>

class Board;

// Routes one complete UTF-8 JSON object received from the App.
// The Agent Link custom command id is intentionally assigned by the App protocol owner.
bool HandleDeviceJson(const uint8_t* payload, size_t len, Board& board);
