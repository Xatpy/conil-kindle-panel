"""Exercise the real hook under Lua 5.1, with device/network/filesystem doubles."""
import unittest
from pathlib import Path

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None


@unittest.skipIf(LuaRuntime is None, "Instala requirements-dev.txt para las pruebas Lua")
class SleepHookTests(unittest.TestCase):
    def run_hook(self, mode="success", connected=True, event=None):
        lua = LuaRuntime()
        state = lua.execute(r'''
            local s = {calls=0, written=false, renamed=false, decoded=false}
            local modules = {}
            modules.device = {isKindle=function() return true end}
            modules["ui/screensaver"] = {setup=function(self,event) s.calls=s.calls+1; s.event=event; return "original" end}
            modules["ui/network/manager"] = {isConnected=function() return s.connected end}
            modules.socketutil = {block_timeout=9, total_timeout=21, set_timeout=function(self,b,t) self.block_timeout=b; self.total_timeout=t end}
            modules.logger = {warn=function() end, info=function() end}
            local png = "\137PNG\r\n\26\n" .. string.char(0,0,0,13) .. "IHDR" .. string.char(0,0,4,48,0,0,5,168)
            modules["socket.http"] = {request=function(options)
                if s.mode=="timeout" then error("timeout") end
                options.sink(s.mode=="invalid" and "<html>error</html>" or png)
                options.sink(nil)
                return 1,200
            end}
            modules["ui/renderimage"] = {renderImageData=function()
                s.decoded=true
                return {free=function() s.freed=true end}
            end}
            require=function(name) assert(modules[name],name); return modules[name] end
            dofile=function() return {url="http://192.0.2.1/conil.png"} end
            io.open=function() return {
                write=function(self,data) s.written=true; return self end,
                close=function() return true end,
            } end
            os.rename=function() s.renamed=true; return true end
            os.remove=function() end
            s.modules=modules
            return s
        ''')
        state.mode = mode
        state.connected = connected
        lua.execute((Path(__file__).parent / "kindle/2-conil-sleepscreen.lua").read_text())
        result = state.modules["ui/screensaver"].setup(lua.table(), event)
        self.assertEqual(result, "original")
        self.assertEqual(state.calls, 1)
        self.assertEqual(state.modules.socketutil.block_timeout, 9)
        self.assertEqual(state.modules.socketutil.total_timeout, 21)
        return state

    def test_success_decodes_then_replaces_image(self):
        state = self.run_hook()
        self.assertTrue(state.decoded)
        self.assertTrue(state.freed)
        self.assertTrue(state.renamed)

    def test_timeout_and_invalid_image_keep_previous_file(self):
        for mode in ("timeout", "invalid"):
            with self.subTest(mode=mode):
                state = self.run_hook(mode)
                self.assertFalse(state.written)
                self.assertFalse(state.renamed)

    def test_no_download_offline_or_during_reboot(self):
        self.assertFalse(self.run_hook(connected=False).written)
        state = self.run_hook(event="reboot")
        self.assertFalse(state.written)
        self.assertEqual(state.event, "reboot")
