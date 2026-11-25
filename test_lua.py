"""Exercise the real sleep hook under Lua 5.1 with device/network/filesystem doubles."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from panel import TZ

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None


@unittest.skipIf(LuaRuntime is None, "Instala requirements-dev.txt para las pruebas Lua")
class SleepHookTests(unittest.TestCase):
    def run_hook(self, mode="success", connected=True, event=None, now=None, png_day=None):
        now = now or datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
        lua = LuaRuntime()
        state = lua.execute(r'''
            local s = {calls=0, requests=0, written=false, renamed=false, decoded=false, files={}}
            local modules = {}
            modules.device = {isKindle=function() return true end}
            modules["ui/screensaver"] = {setup=function(self,event) s.calls=s.calls+1; s.event=event; return "original" end}
            modules["ui/network/manager"] = {isConnected=function() return s.connected end}
            modules.socketutil = {block_timeout=9, total_timeout=21, set_timeout=function(self,b,t) self.block_timeout=b; self.total_timeout=t end}
            modules.logger = {warn=function() end, info=function() end}
            local function uint32(n) return string.char(0,0,math.floor(n/256),n%256) end
            local function chunk(tag,payload) return uint32(#payload)..tag..payload.."0000" end
            local function png()
                return "\137PNG\r\n\26\n" .. chunk("IHDR",string.char(0,0,4,48,0,0,5,168,8,0,0,0,0))
                    .. chunk("tEXt","ConilDate\0"..s.png_day) .. chunk("IEND","")
            end
            modules["socket.http"] = {request=function(options)
                s.requests=s.requests+1
                if s.mode=="timeout" then error("timeout") end
                options.sink(s.mode=="invalid" and "<html>error</html>" or png())
                options.sink(nil)
                return 1,200
            end}
            modules["ui/renderimage"] = {renderImageData=function()
                s.decoded=true
                if s.mode=="decode-failure" then return nil end
                return {free=function() s.freed=true end}
            end}
            require=function(name) assert(modules[name],name); return modules[name] end
            dofile=function() return {url=s.config_url} end
            io.open=function(path,mode)
                if mode=="r" or mode=="rb" then
                    local data=s.files[path]
                    if not data then return nil end
                    local pos=1
                    return {read=function()
                        local line,finish=data:match("([^\n]*)\n()",pos)
                        pos=finish or #data+1
                        return line
                    end,close=function() return true end}
                end
                return {write=function(self,...)
                    s.files[path]=table.concat({...})
                    if path==s.target..".tmp" then s.written=true end
                    return self
                end,close=function() return true end}
            end
            os.time=function() return s.now end
            os.rename=function(src,dst)
                s.files[dst]=s.files[src];s.files[src]=nil
                if dst==s.target then s.renamed=true end
                return true
            end
            os.remove=function(path) s.files[path]=nil end
            s.modules=modules
            return s
        ''')
        state.mode = mode; state.connected = connected
        state.now = now.timestamp()
        state.png_day = png_day or now.astimezone(TZ).date().isoformat()
        state.config_url = "https://example.org/conil.png"
        state.target = "/mnt/us/koreader/conil.png"
        lua.execute((Path(__file__).parent / "kindle/2-conil-sleepscreen.lua").read_text())
        state.sleep = lua.eval("function(hook) return function(event) return hook({},event) end end")(state.modules["ui/screensaver"].setup)
        self.assertEqual(state.sleep(event), "original")
        self.assertEqual(state.calls, 1)
        self.assertEqual(state.modules.socketutil.block_timeout, 9)
        self.assertEqual(state.modules.socketutil.total_timeout, 21)
        return state

    def test_success_decodes_then_replaces_image(self):
        state = self.run_hook()
        self.assertTrue(state.decoded)
        self.assertTrue(state.freed)
        self.assertTrue(state.renamed)

    def test_timeout_and_invalid_image_do_not_mark_day_as_done(self):
        for mode in ("timeout", "invalid", "decode-failure"):
            with self.subTest(mode=mode):
                state = self.run_hook(mode)
                self.assertFalse(state.written)
                self.assertFalse(state.renamed)
                self.assertIsNone(state.files[state.target + ".last-update"])
                state.mode = "success"
                state.sleep(None)
                self.assertEqual(state.requests, 2)
                self.assertTrue(state.renamed)

    def test_no_download_offline_or_during_reboot(self):
        self.assertEqual(self.run_hook(connected=False).requests, 0)
        state = self.run_hook(event="reboot")
        self.assertEqual(state.requests, 0)
        self.assertEqual(state.event, "reboot")

    def test_second_sleep_same_day_makes_no_request(self):
        state = self.run_hook()
        state.sleep(None)
        self.assertEqual(state.requests, 1)
        self.assertEqual(state.calls, 2)

    def test_yesterdays_edition_is_retried_later(self):
        state = self.run_hook(png_day="2026-11-24")
        self.assertFalse(state.renamed)
        self.assertIsNone(state.files[state.target + ".last-update"])
        state.png_day = "2026-11-25"
        state.sleep(None)
        self.assertEqual(state.requests, 2)
        self.assertTrue(state.renamed)

    def test_url_change_and_missing_image_allow_redownload(self):
        state = self.run_hook()
        state.config_url = "https://new.example.org/conil.png"
        state.sleep(None)
        self.assertEqual(state.requests, 2)
        state.files[state.target] = None
        state.sleep(None)
        self.assertEqual(state.requests, 3)

    def test_madrid_day_across_midnight_and_dst(self):
        for now in (datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc),
                    datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc),
                    datetime(2026, 3, 29, 22, 30, tzinfo=timezone.utc),
                    datetime(2026, 10, 25, 22, 30, tzinfo=timezone.utc)):
            with self.subTest(now=now):
                state = self.run_hook(now=now)
                expected = now.astimezone(TZ).date().isoformat()
                self.assertTrue(state.files[state.target + ".last-update"].startswith(expected + "\n"))
