"""In-process Qt adapter for CapCut 9.7 export-panel integration.

NOT a standalone exporter, external process injector, or patched CapCut EXE.
A trusted host INSIDE the original CapCut Qt process must supply the *real*
ExportCompileBottomViewModel QObject, current-draft reader, output-path reader,
and original-engine admission/completion notifications. Without that host
nativeBridgeVerified stays false and requestExport always fails closed.

The recovered original clickBackgroudExport() returns void: dispatch success
NEVER means native task admission. See ORIGINAL_NATIVE_EXPORT_ROUTE.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import ntpath
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QObject, QMetaMethod, QMetaObject, QThread, Qt, Signal, Slot, Property,
)

from .native_output_validation import (
    begin_export, verify_completed, NativeOutputError, ExportTicket,
    VerifiedOutput,
)

EXPECTED_CLASS = "ExportCompileBottomViewModel"
EXPECTED_SIGNATURE = b"clickBackgroudExport()"


@dataclass(frozen=True)
class CurrentDraft:
    """A live view of the original export panel, provided by trusted host."""

    draft_id: str
    project_path: str
    model: QObject


@dataclass
class PendingExport:
    key: str
    draft_id: str
    project_path: str
    ticket: ExportTicket
    task_id: str = ""


def same_windows_path(left: str, right: str) -> bool:
    """Compare Windows paths lexically, without accessing the filesystem."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if not left or not right:
        return False
    if not ntpath.isabs(left) or not ntpath.isabs(right):
        return False
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def is_expected_original_qobject(model: QObject) -> bool:
    """Check Qt metaobject *shape*, not its provenance or live host identity."""
    if not isinstance(model, QObject):
        return False
    meta = model.metaObject()
    if meta.className() != EXPECTED_CLASS:
        return False
    index = meta.indexOfMethod(EXPECTED_SIGNATURE)
    if index < 0:
        return False
    method = meta.method(index)
    if method.access() != QMetaMethod.Access.Public:
        return False
    if method.methodType() == QMetaMethod.MethodType.Signal:
        return False
    if method.parameterCount() != 0:
        return False
    if method.returnMetaType().name() not in (b"void", "void"):
        return False
    return True


class QtRuntimeAdapter(QObject):
    """A contract-compatible, fail-closed QObject for the existing Home QML.

    Runtime verification is supplied by a *trusted same-process* host.
    External scripts cannot obtain foreign-process QObjects by constructing
    a local PySide6 QObject. No DLL address or byte offset is invoked.
    """

    bridgeChanged = Signal()
    exportAdmitted = Signal(str, str)
    exportVerified = Signal(str, str, str)
    exportFailed = Signal(str, str)
    exportProgress = Signal(str, float)

    def __init__(
        self,
        model: QObject,
        read_current_draft: Callable[[], CurrentDraft | None],
        resolve_output: Callable[[str, str], str],
        *,
        verify_native_runtime: Callable[[QObject], bool],
        receipt_verifier: Callable[[ExportTicket, str], VerifiedOutput] = verify_completed,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._model = model
        self._reader = read_current_draft
        self._resolve_output = resolve_output
        self._verify_runtime = verify_native_runtime
        self._receipt_verifier = receipt_verifier
        self._verified = False
        self._pending: PendingExport | None = None
        # No automatic activation; the trusted original host must opt in
        # after a live, exact-version, in-process object provenance check.

    @Property(bool, notify=bridgeChanged)
    def nativeBridgeVerified(self) -> bool:
        return self._verified

    @Slot(result=bool)
    def verifyRuntime(self) -> bool:
        """Call only from the genuine trusted in-process integration host."""
        if self._pending is not None:
            return False
        valid = self._qt_thread_ready() and is_expected_original_qobject(self._model)
        if valid:
            try:
                valid = self._verify_runtime(self._model) is True
            except Exception:
                valid = False
        if self._verified != valid:
            self._verified = valid
            self.bridgeChanged.emit()
        return valid

    def _qt_thread_ready(self) -> bool:
        return (
            isinstance(self._model, QObject) and
            self.thread() == QThread.currentThread() and
            self._model.thread() == QThread.currentThread()
        )

    def _matches(self, draft_id: str, project_path: str, key: str) -> bool:
        if not self._verified or not self._qt_thread_ready():
            return False
        if not all(isinstance(s, str) and bool(s) for s in
                   (draft_id, project_path, key)):
            return False
        if key != draft_id + "::" + project_path:
            return False
        try:
            active = self._reader()
        except Exception:
            return False
        return (
            isinstance(active, CurrentDraft) and
            active.model is self._model and
            active.draft_id == draft_id and
            same_windows_path(active.project_path, project_path)
        )

    @Slot(str, str, str, result=bool)
    def verifyCurrentDraftBinding(self, draft_id: str, project_path: str, key: str) -> bool:
        return self._matches(draft_id, project_path, key) and self._pending is None

    @Slot(str, str, str, result=bool)
    def requestExport(self, draft_id: str, project_path: str, key: str) -> bool:
        if self._pending is not None or not self._matches(draft_id, project_path, key):
            return False
        try:
            output = self._resolve_output(draft_id, project_path)
            if not isinstance(output, str):
                return False
            ticket = begin_export(key, draft_id, project_path, output)
        except (NativeOutputError, OSError, ValueError):
            return False
        # Reserve the request before native dispatch, so re-entrant host
        # callbacks can never cause a duplicate export.
        pending = PendingExport(key, draft_id, project_path, ticket)
        self._pending = pending
        try:
            # Dispatch the actual original Qt invokable, not a guessed C++ ABI.
            # Qt's bool here is method-invocation SUCCESS, not task admission.
            dispatched = QMetaObject.invokeMethod(
                self._model, "clickBackgroudExport", Qt.ConnectionType.DirectConnection
            )
        except Exception:
            dispatched = False
        if dispatched is not True:
            if self._pending is pending:
                self._pending = None
            return False
        return True

    def _matches_pending(self, key: str) -> bool:
        pending = self._pending
        return bool(pending and pending.key == key and
                    self._matches(pending.draft_id, pending.project_path, pending.key))

    def nativeTaskAdmitted(self, key: str, task_id: str,
                           draft_id: str, project_path: str) -> bool:
        """Trusted ORIGINAL native scheduler callback (not a file watcher).

        The callback must have verified that the original task belongs to
        this draft and output ticket. This adapter cannot discover CapCut's
        private native scheduler from a separate process.
        """
        pending = self._pending
        if (pending is None or pending.task_id or
                not isinstance(task_id, str) or not task_id.strip() or
                key != pending.key or draft_id != pending.draft_id or
                not same_windows_path(project_path, pending.project_path) or
                not self._matches_pending(key)):
            return False
        pending.task_id = task_id
        self.exportAdmitted.emit(key, task_id)
        return True

    def nativeTaskProgress(self, key: str, task_id: str, percent: float) -> bool:
        pending = self._pending
        if (not pending or pending.key != key or
                not pending.task_id or pending.task_id != task_id or
                not isinstance(percent, (int, float)) or
                not 0 <= percent <= 100):
            return False
        self.exportProgress.emit(key, float(percent))
        return True

    def nativeTaskCompleted(self, key: str, task_id: str, output_path: str) -> bool:
        """Complete only after admitted native task ID and MP4 receipt match."""
        pending = self._pending
        if (not pending or pending.key != key or not pending.task_id or
                task_id != pending.task_id or not isinstance(output_path, str)):
            return False
        try:
            receipt = self._receipt_verifier(pending.ticket, output_path)
            if (not isinstance(receipt, VerifiedOutput) or receipt.key != key or
                    not same_windows_path(receipt.output_path, str(pending.ticket.output_path)) or
                    len(receipt.sha256) != 64):
                raise NativeOutputError("Native output receipt mismatch")
        except (NativeOutputError, OSError, ValueError) as exc:
            self.nativeTaskFailed(key, task_id, str(exc))
            return False
        self._pending = None
        self.exportVerified.emit(key, receipt.output_path, receipt.sha256)
        return True

    def nativeTaskFailed(self, key: str, task_id: str, reason: str) -> bool:
        pending = self._pending
        if (not pending or pending.key != key or
                (pending.task_id and pending.task_id != task_id)):
            return False
        self._pending = None
        self.exportFailed.emit(key, str(reason))
        return True

    def cancelUnadmittedRequest(self, key: str) -> bool:
        """Only for a confirmed no-admission case, never for unknown outcomes.

        An admission timeout is an UNKNOWN outcome: the original engine may
        already be working. Do not clear/replay it automatically.
        """
        pending = self._pending
        if pending is None or pending.key != key or pending.task_id:
            return False
        return False  # Needs trusted native scheduler cancellation evidence.
