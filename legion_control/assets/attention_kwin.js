// Tells Legion Control which windows are asking for attention (the highlighted taskbar entry).
// KWin clears the state when the window is focused, which also ends the keyboard flash.
const SERVICE = "org.legioncontrol.Attention";
const PATH = "/org/legioncontrol/Attention";

function send(window, waiting) {
    callDBus(SERVICE, PATH, SERVICE, "Set", "window:" + window.internalId.toString(), waiting);
}

function watch(window) {
    window.demandsAttentionChanged.connect(function () {
        send(window, window.demandsAttention);
    });
    if (window.demandsAttention) {
        send(window, true);
    }
}

workspace.windowList().forEach(watch);
workspace.windowAdded.connect(watch);
workspace.windowRemoved.connect(function (window) {
    send(window, false);
});
