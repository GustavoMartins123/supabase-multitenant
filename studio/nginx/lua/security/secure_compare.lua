local has_bit, bit = pcall(require, "bit")

local M = {}

local function fallback_bxor(left, right)
    local result = 0
    local place = 1
    for _ = 1, 8 do
        local left_bit = left % 2
        local right_bit = right % 2
        if left_bit ~= right_bit then
            result = result + place
        end
        left = math.floor(left / 2)
        right = math.floor(right / 2)
        place = place * 2
    end
    return result
end

local function byte_xor(left, right)
    if has_bit then
        return bit.bxor(left, right)
    end
    return fallback_bxor(left, right)
end

function M.equals(left, right)
    if type(left) ~= "string" or type(right) ~= "string" or #left ~= #right then
        return false
    end

    local difference = 0
    for index = 1, #left do
        difference = difference + byte_xor(
            left:byte(index),
            right:byte(index)
        )
    end
    return difference == 0
end

return M
