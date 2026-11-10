# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Makes the plugin easy to find: an Extensions menu entry and a one-time hello.

Cura hides its left toolbar until a model is on the build plate, so a freshly
installed tool plugin is otherwise invisible in an empty Cura.
"""

from UM.Extension import Extension
from UM.Logger import Logger
from UM.Message import Message

from cura.CuraApplication import CuraApplication

from .HybridSupportsTool import __build_date__, __version__

PREF_INTRO = "hybrid_supports/intro_shown_for"
HOW_TO = ("Load a model and click it so it is selected. The Hybrid Supports button (a small tower) "
          "is then at the bottom of the tool bar on the left; the shortcut is H. "
          "Choose your settings and press Generate, then slice as usual.")


class HybridSupportsExtension(Extension):
    def __init__(self) -> None:
        super().__init__()
        self.setMenuName("Hybrid Supports")
        self.addMenuItem("How to use", self.showHowTo)
        self.addMenuItem(f"About (v{__version__})", self.showAbout)
        app = CuraApplication.getInstance()
        app.getPreferences().addPreference(PREF_INTRO, "")
        app.initializationFinished.connect(self._onCuraReady)

    def _onCuraReady(self) -> None:
        try:
            prefs = CuraApplication.getInstance().getPreferences()
            if prefs.getValue(PREF_INTRO) != __version__:
                prefs.setValue(PREF_INTRO, __version__)
                Message(f"Hybrid Supports {__version__} is installed (work in progress). " + HOW_TO +
                        " This note is shown once; the same help is under Extensions > Hybrid Supports.",
                        title="Hybrid Supports", lifetime=0,
                        message_type=Message.MessageType.POSITIVE).show()
        except Exception:
            Logger.logException("w", "Hybrid Supports could not show its first-run note")

    def showHowTo(self) -> None:
        Message(HOW_TO, title="Hybrid Supports: how to use", lifetime=0,
                message_type=Message.MessageType.NEUTRAL).show()

    def showAbout(self) -> None:
        Message(f"Hybrid Supports v{__version__} (Built {__build_date__}). WORK IN PROGRESS: many features "
                "may be broken. Copyright Matthew Armstrong (github.com/The-Dorkknight). "
                "PolyForm Noncommercial License 1.0.0; no warranty.",
                title="About Hybrid Supports", lifetime=0,
                message_type=Message.MessageType.NEUTRAL).show()
