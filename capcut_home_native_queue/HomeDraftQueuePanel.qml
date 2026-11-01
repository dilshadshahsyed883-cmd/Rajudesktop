// HomeDraftQueuePanel.qml
// Intended to be hosted INSIDE CapCut's verified Home QML module after its
// original background-export adapter ABI is established. NOT injected/loaded
// into the production CapCut application by this repository.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    width: 820
    height: 480

    // Host provides ORIGINAL Home draft objects:
    // {draftId: string, strProjectPath: string, strTitle: string}
    property var drafts: []
    // Explicitly bound after the genuine Qt-to-BackEndExportImpl bridge
    // is verified. This module NEVER guesses a DLL address or ABI.
    //
    // Host contract:
    //   bool submitExport(draftId, strProjectPath, key)
    //   signal exportVerified(key, outputPath, sha256) // verified native MP4
    //   signal exportFailed(key, message)
    //   signal exportProgress(key, percent)
    property var nativeAdapter: null
    property var selected: ({})
    property var results: ({})
    property var pending: []
    property string activeKey: ""
    property bool pauseAfterCurrent: false
    property string statusLine: "Native CapCut Home bridge not connected"
    readonly property bool adapterReady:
        nativeAdapter !== null &&
        typeof nativeAdapter.submitExport === "function"
    readonly property bool running: activeKey.length > 0
    readonly property int selectedCount: Object.keys(selected).filter(
        function (k) { return selected[k] === true; }).length

    signal snapshotChanged(var snapshot)

    function validDraft(draft) {
        return draft !== null && draft !== undefined &&
               typeof draft.draftId === "string" && draft.draftId.length > 0 &&
               typeof draft.strProjectPath === "string" &&
               draft.strProjectPath.length > 0;
    }
    function keyFor(draft) {
        return validDraft(draft) ? draft.draftId + "::" + draft.strProjectPath : "";
    }
    function setSelected(draft, value) {
        var key = keyFor(draft);
        if (!key || running || pending.length > 0 || results[key] === "Completed")
            return false;
        var updated = Object.assign({}, selected);
        updated[key] = value === true;
        selected = updated;
        snapshotChanged(snapshot());
        return true;
    }
    function setResult(key, status) {
        var updated = Object.assign({}, results);
        updated[key] = status;
        results = updated;
        snapshotChanged(snapshot());
    }
    function snapshot() {
        return {
            selectedKeys: Object.keys(selected).filter(function (k) { return selected[k]; }),
            pendingKeys: pending.map(function (d) { return keyFor(d); }),
            activeKey: activeKey,
            results: Object.assign({}, results),
            paused: pauseAfterCurrent
        };
    }
    function startSelected() {
        if (!adapterReady) {
            statusLine = "Native bridge unavailable; export disabled";
            return false;
        }
        if (running || pending.length > 0)
            return false;
        var candidates = [];
        var seen = {};
        for (var i = 0; i < drafts.length; i++) {
            var draft = drafts[i];
            var key = keyFor(draft);
            if (!key || seen[key] || selected[key] !== true ||
                results[key] === "Completed")
                continue;
            seen[key] = true;
            candidates.push(draft);
        }
        if (candidates.length === 0) {
            statusLine = "Select one or more eligible drafts";
            return false;
        }
        pending = candidates;
        pauseAfterCurrent = false;
        for (var j = 0; j < pending.length; j++)
            setResult(keyFor(pending[j]), "Queued");
        runNext();
        return true;
    }
    function runNext() {
        if (running || pauseAfterCurrent || pending.length === 0)
            return;
        if (!adapterReady) {
            statusLine = "Native adapter disconnected; queue is paused";
            pauseAfterCurrent = true;
            return;
        }
        var draft = pending[0];
        pending = pending.slice(1);
        var key = keyFor(draft);
        if (!key) {
            statusLine = "Invalid draft rejected";
            pauseAfterCurrent = true;
            return;
        }
        activeKey = key;
        setResult(key, "Rendering");
        statusLine = "Rendering with original CapCut engine: " +
                     (draft.strTitle || draft.draftId);
        try {
            // Only the host's *verified* adapter may enqueue an export.
            // Do not treat undefined / Promise / inferred status as success.
            if (nativeAdapter.submitExport(draft.draftId,
                                           draft.strProjectPath, key) !== true) {
                nativeFailed(key, "Host did not confirm native queue admission");
            }
        } catch (error) {
            nativeFailed(key, String(error));
        }
    }
    function nativeVerified(key, outputPath, sha256) {
        // The host MUST verify the full native MP4 before emitting this event.
        if (!activeKey || key !== activeKey)
            return false;
        if (typeof outputPath !== "string" || !outputPath ||
            typeof sha256 !== "string" || !/^[a-fA-F0-9]{64}$/.test(sha256)) {
            nativeFailed(key, "Native output verification evidence missing");
            return false;
        }
        setResult(key, "Completed");
        activeKey = "";
        var updatedSelection = Object.assign({}, selected);
        delete updatedSelection[key];
        selected = updatedSelection;
        statusLine = "Verified MP4: " + outputPath;
        snapshotChanged(snapshot());
        if (!pauseAfterCurrent)
            runNext();
        return true;
    }
    function nativeFailed(key, reason) {
        if (!activeKey || key !== activeKey)
            return false;
        setResult(key, "Review");
        activeKey = "";
        pauseAfterCurrent = true;
        statusLine = "Stopped for review: " + String(reason);
        snapshotChanged(snapshot());
        return true;
    }
    function pause() {
        pauseAfterCurrent = true;
        statusLine = running ? "Will pause after current render" : "Queue paused";
        snapshotChanged(snapshot());
    }
    function resume() {
        if (running || !adapterReady)
            return false;
        pauseAfterCurrent = false;
        runNext();
        snapshotChanged(snapshot());
        return true;
    }

    Connections {
        target: root.nativeAdapter
        ignoreUnknownSignals: true
        function onExportVerified(key, outputPath, sha256) {
            root.nativeVerified(key, outputPath, sha256);
        }
        function onExportFailed(key, reason) {
            root.nativeFailed(key, reason);
        }
        function onExportProgress(key, percent) {
            if (root.activeKey === key && percent >= 0 && percent <= 100)
                root.statusLine = "Native render " + Math.round(percent) + "%";
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Label {
            text: "Ready drafts — select and export"
            font.bold: true
            font.pixelSize: 21
            Layout.fillWidth: true
        }
        Label {
            text: root.adapterReady
                  ? "Original CapCut native queue connected"
                  : "Native Qt Home export bridge not verified — Start disabled"
            color: root.adapterReady ? "#187a3a" : "#c66b27"
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        ListView {
            id: projects
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.drafts
            spacing: 3
            delegate: Rectangle {
                width: projects.width
                height: 46
                color: index % 2 ? "#f6f6f6" : "#ffffff"
                property var draft: modelData
                property string key: root.keyFor(draft)
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 6
                    anchors.rightMargin: 6
                    CheckBox {
                        enabled: key.length > 0 && !root.running &&
                                 root.pending.length === 0 &&
                                 root.results[key] !== "Completed"
                        checked: root.selected[key] === true
                        onClicked: root.setSelected(draft, checked)
                    }
                    Label {
                        text: draft.strTitle || draft.draftId || "Unnamed draft"
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Label {
                        text: root.results[key] || (key ? "Ready" : "Invalid draft")
                        Layout.preferredWidth: 125
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Button {
                text: "Export selected in queue (" + root.selectedCount + ")"
                enabled: root.adapterReady && !root.running &&
                         root.pending.length === 0 && root.selectedCount > 0
                onClicked: root.startSelected()
            }
            Button {
                text: "Stop after current"
                enabled: root.running && !root.pauseAfterCurrent
                onClicked: root.pause()
            }
            Button {
                text: "Resume"
                enabled: root.pauseAfterCurrent &&
                         !root.running && root.pending.length > 0 &&
                         root.adapterReady
                onClicked: root.resume()
            }
            Item { Layout.fillWidth: true }
        }
        Label {
            text: root.statusLine
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
    }
}
