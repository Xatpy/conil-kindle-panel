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
local original_setup = Screensaver.setup

local function fetch()
    if not NetworkMgr:isConnected() then return end
    local ok, config = pcall(dofile, config_path)
    if not ok or type(config) ~= "table" or type(config.url) ~= "string" then return end
    if not config.url:match("^https?://") then return end
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
    local function uint32(pos)
        local a, b, c, d = data:byte(pos, pos + 3)
        return ((a * 256 + b) * 256 + c) * 256 + d
    end
    if uint32(17) ~= 1072 or uint32(21) ~= 1448 then return end
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
        if renamed then logger.info("conil: sleep image updated") end
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
