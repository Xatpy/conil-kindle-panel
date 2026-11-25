-- Conil: refresh the configured sleep image before KOReader draws it.
-- No scheduled wakes, no Wi-Fi activation, no changes to the stock framework.
local Device = require("device")
if not Device:isKindle() then return end
local Screensaver = require("ui/screensaver")
local NetworkMgr = require("ui/network/manager")
local socketutil = require("socketutil")
local http = require("socket.http")
local RenderImage = require("ui/renderimage")
local logger = require("logger")
local config_path = "/mnt/us/koreader/settings/conil-config.lua"
local target = "/mnt/us/koreader/conil.png"
local marker_path = target .. ".last-update"
local original_setup = Screensaver.setup

local function conil_day()
    -- Europe/Madrid calendar day, independent of the Kindle's system timezone.
    local now = os.time()
    local utc = os.date("!*t", now)
    local dst = utc.month > 3 and utc.month < 10
    if utc.month == 3 or utc.month == 10 then
        local last_sunday = 31 - ((utc.wday - 1 + 31 - utc.day) % 7)
        if utc.month == 3 then
            dst = utc.day > last_sunday or (utc.day == last_sunday and utc.hour >= 1)
        else
            dst = utc.day < last_sunday or (utc.day == last_sunday and utc.hour < 1)
        end
    end
    return os.date("!%Y-%m-%d", now + (dst and 7200 or 3600))
end

local function uint32(data, pos)
    local a, b, c, d = data:byte(pos, pos + 3)
    if not d then return nil end
    return ((a * 256 + b) * 256 + c) * 256 + d
end

local function image_day(data)
    local pos = 9
    while pos + 11 <= #data do
        local length = uint32(data, pos)
        if not length or length > #data - pos - 11 then return nil end
        if data:sub(pos + 4, pos + 7) == "tEXt" then
            local day = data:sub(pos + 8, pos + 7 + length):match("^ConilDate%z(%d%d%d%d%-%d%d%-%d%d)$")
            if day then return day end
        end
        pos = pos + length + 12
    end
end

local function fetch()
    local ok, config = pcall(dofile, config_path)
    if not ok or type(config) ~= "table" or type(config.url) ~= "string" then return end
    if not config.url:match("^https?://") then return end
    local today = conil_day()
    local marker = io.open(marker_path, "r")
    if marker then
        local day, url = marker:read("*l"), marker:read("*l")
        marker:close()
        if day == today and url == config.url then
            local image = io.open(target, "rb")
            if image then image:close(); return end
        end
    end
    if not NetworkMgr:isConnected() then return end
    local chunks, size = {}, 0
    local block_timeout, total_timeout = socketutil.block_timeout, socketutil.total_timeout
    socketutil:set_timeout(2, 5)
    local success, result, status = pcall(http.request, {
        url = config.url,
        redirect = false,
        headers = { ["Cache-Control"] = "no-cache" },
        sink = function(chunk)
            if chunk then
                size = size + #chunk
                if size > 1024 * 1024 then return nil, "image too large" end
                chunks[#chunks + 1] = chunk
            end
            return 1
        end,
    })
    socketutil:set_timeout(block_timeout, total_timeout)
    if not success or not result or tonumber(status) ~= 200 then
        logger.warn("conil: retaining previous sleep image", status)
        return
    end
    local data = table.concat(chunks)
    if data:sub(1, 8) ~= "\137PNG\r\n\26\n" then return end
    if #data < 24 or data:sub(13, 16) ~= "IHDR" then return end
    if uint32(data, 17) ~= 1072 or uint32(data, 21) ~= 1448 then return end
    if image_day(data) ~= today then
        logger.info("conil: daily edition not ready; retry on a later sleep")
        return
    end
    -- Decode first: never replace the last usable image with an HTML error or a
    -- truncated PNG. Size is capped above to avoid exhausting Kindle memory.
    local decoded, bb = pcall(RenderImage.renderImageData, RenderImage, data, #data)
    if not decoded or not bb then return end
    bb:free()
    local file = io.open(target .. ".tmp", "wb")
    if not file then return end
    local written = file:write(data)
    local closed = file:close()
    if written and closed then
        local renamed = os.rename(target .. ".tmp", target)
        if renamed then
            logger.info("conil: daily sleep image updated", today)
            local mark = io.open(marker_path .. ".tmp", "w")
            if mark then
                local saved = mark:write(today, "\n", config.url, "\n")
                local complete = mark:close()
                if saved and complete then os.rename(marker_path .. ".tmp", marker_path) end
                os.remove(marker_path .. ".tmp")
            end
        end
    end
    os.remove(target .. ".tmp")
end

Screensaver.setup = function(self, event, ...)
    if not event then
        local ok, err = pcall(fetch)
        if not ok then logger.warn("conil: sleep refresh failed", err) end
    end
    return original_setup(self, event, ...)
end
