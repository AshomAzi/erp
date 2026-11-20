document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-submit-task-trigger]").forEach((trigger) => {
        trigger.addEventListener("click", () => {
            const form = document.getElementById("submitTaskForm");
            const notes = document.getElementById("workNotes");
            const reference = document.getElementById("workReference");
            const title = document.getElementById("submitWorkTitle");
            const submitButton = document.getElementById("submitTaskButton");
            if (
                !(form instanceof HTMLFormElement) ||
                !(notes instanceof HTMLTextAreaElement) ||
                !(reference instanceof HTMLInputElement) ||
                !title ||
                !submitButton
            ) {
                console.error("Task submission form is missing a required element.");
                return;
            }

            const taskRow = trigger.closest("[data-task-row]");
            if (!taskRow) {
                console.error("Task submission trigger is missing its task row.");
                return;
            }

            const task = taskRow.dataset;
            const isRevision = task.taskSubmissionStatus === "RevisionRequested";
            form.action = `/epr/employee/tasks/${trigger.dataset.taskId}/submit/`;
            notes.value = task.taskSubmissionNotes || "";
            reference.value = task.taskSubmissionReference || "";
            title.textContent = isRevision ? "Edit and Resubmit Work" : "Submit Completed Work";
            submitButton.textContent = isRevision
                ? "Resubmit for Supervisor Review"
                : "Submit for Supervisor Review";
        });
    });
    const taskDetailsModal = document.getElementById("taskDetailsModal");
    const taskDetailsTitle = document.getElementById("taskDetailsTitle");
    const taskDetailsAssigner = document.getElementById("taskDetailsAssigner");
    const taskDetailsDeadline = document.getElementById("taskDetailsDeadline");
    const taskDetailsStatus = document.getElementById("taskDetailsStatus");
    const taskDetailsDescription = document.getElementById("taskDetailsDescription");
    const taskPdfMessage = document.getElementById("taskPdfMessage");
    const taskPdfDownload = document.getElementById("taskPdfDownload");

    document.querySelectorAll("[data-task-details-open]").forEach((trigger) => {
        trigger.addEventListener("click", () => {
            const taskRow = trigger.closest("[data-task-row]");
            if (
                !(taskDetailsModal instanceof HTMLDialogElement) ||
                !taskRow ||
                !taskDetailsTitle ||
                !taskDetailsAssigner ||
                !taskDetailsDeadline ||
                !taskDetailsStatus ||
                !taskDetailsDescription ||
                !taskPdfMessage ||
                !(taskPdfDownload instanceof HTMLAnchorElement)
            ) {
                console.error("Task details are missing a required element or task row.");
                return;
            }

            const task = taskRow.dataset;
            taskDetailsTitle.textContent = task.taskTitle || "Task Details";
            taskDetailsAssigner.textContent = task.taskAssignedBy || "Not provided";
            taskDetailsDeadline.textContent = task.taskDeadline || "Not provided";
            taskDetailsStatus.textContent = task.taskStatus || "Not provided";
            taskDetailsDescription.textContent = task.taskDescription || "No instructions were provided.";

            taskPdfDownload.hidden = true;
            taskPdfDownload.removeAttribute("href");
            taskPdfDownload.removeAttribute("download");

            const attachmentUrl = task.taskAttachmentUrl;
            const attachmentName = task.taskAttachmentName || "";
            const attachmentType = (task.taskAttachmentType || "").split(";")[0].trim().toLowerCase();
            const isPdf =
                attachmentType === "application/pdf" ||
                /\.pdf(?:$|[?#])/i.test(attachmentName) ||
                /\.pdf(?:$|[?#])/i.test(attachmentUrl || "");

            if (attachmentUrl && isPdf) {
                try {
                    const downloadUrl = new URL(attachmentUrl, window.location.href);
                    if (downloadUrl.protocol !== "http:" && downloadUrl.protocol !== "https:") {
                        throw new Error("Unsupported task attachment URL protocol.");
                    }

                    const suggestedName = attachmentName.split(/[\\/]/).pop() || "task-attachment.pdf";
                    taskPdfDownload.href = downloadUrl.href;
                    taskPdfDownload.download = suggestedName;
                    taskPdfDownload.hidden = false;
                    taskPdfMessage.textContent = "";
                    taskPdfMessage.hidden = true;
                } catch (error) {
                    console.error("Unable to open the task PDF attachment.", error);
                    taskPdfMessage.textContent = "The PDF attachment link is invalid.";
                    taskPdfMessage.hidden = false;
                }
            } else {
                taskPdfMessage.textContent = attachmentUrl
                    ? "This task has an attachment, but it is not a PDF."
                    : "No PDF is attached to this task.";
                taskPdfMessage.hidden = false;
            }

            taskDetailsModal.showModal();
        });
    });

    const checkInBtn = document.getElementById("checkInBtn");
    const checkOutBtn = document.getElementById("checkOutBtn");
    const attendanceFeedback = document.getElementById("attendanceFeedback");
    const checkInStatusBadge = document.getElementById("checkInStatusBadge");
    const attendanceForm = document.getElementById("attendanceForm");
    const attendanceAction = document.getElementById("attendanceActionInput");
    const attendancePanel = document.querySelector("[data-attendance-settings]");
    const serverNowMs = Number(attendancePanel ? attendancePanel.dataset.serverNowMs : NaN);
    const lateDeadlineMs = Number(attendancePanel ? attendancePanel.dataset.lateDeadlineMs : NaN);
    const checkOutDeadlineMs = Number(attendancePanel ? attendancePanel.dataset.checkOutDeadlineMs : NaN);
    const lateAfterTime = attendancePanel ? attendancePanel.dataset.lateAfterLabel : "";
    const clientLoadTimeMs = Date.now();
    let hasCheckedIn = Boolean(attendancePanel && attendancePanel.dataset.hasCheckedIn === "true");
    let hasCheckedOut = Boolean(attendancePanel && attendancePanel.dataset.hasCheckedOut === "true");

    function getServerNowMs() {
        return serverNowMs + (Date.now() - clientLoadTimeMs);
    }

    if (
        attendancePanel &&
        (!Number.isFinite(serverNowMs) || !Number.isFinite(lateDeadlineMs) || !Number.isFinite(checkOutDeadlineMs))
    ) {
        console.error("Attendance schedule is missing or invalid.");
        if (checkInBtn) checkInBtn.disabled = true;
        if (checkOutBtn) checkOutBtn.disabled = true;
    }

    function updateCheckoutAvailability() {
        checkOutBtn.disabled =
            !Number.isFinite(checkOutDeadlineMs) ||
            !hasCheckedIn ||
            hasCheckedOut ||
            getServerNowMs() < checkOutDeadlineMs;
    }

    if (checkOutBtn) {
        updateCheckoutAvailability();
        setInterval(updateCheckoutAvailability, 1000);
    }

    function showAttendanceAlert(message, type) {
        if (!attendanceFeedback) return;
        attendanceFeedback.textContent = message;
        attendanceFeedback.className = `alert-banner show alert-${type}`;
    }

    if (checkInBtn) {
        checkInBtn.addEventListener("click", () => {
            const now = new Date();
            if (!Number.isFinite(lateDeadlineMs)) {
                showAttendanceAlert("Attendance schedule is unavailable.", "danger");
                return;
            }

            const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            const isLate = getServerNowMs() > lateDeadlineMs;

            if (isLate) {
                showAttendanceAlert(
                    `Checked in at ${timeStr}. Check-ins after ${lateAfterTime} are marked LATE.`,
                    "warning"
                );
                if (checkInStatusBadge) {
                    checkInStatusBadge.textContent = `Checked In (${timeStr} - Late)`;
                    checkInStatusBadge.className = "badge badge-warning";
                }
            } else {
                showAttendanceAlert(
                    `Checked in at ${timeStr}. Check-in is on time (by ${lateAfterTime}).`,
                    "success"
                );
                if (checkInStatusBadge) {
                    checkInStatusBadge.textContent = `Checked In (${timeStr} - On Time)`;
                    checkInStatusBadge.className = "badge badge-success";
                }
            }

            checkInBtn.disabled = true;
            hasCheckedIn = true;
            if (attendanceAction instanceof HTMLInputElement && attendanceForm instanceof HTMLFormElement) {
                attendanceAction.value = "check_in";
                attendanceForm.requestSubmit();
            } else {
                console.error("Attendance form is missing its action field.");
                showAttendanceAlert("Unable to submit attendance. Please reload and try again.", "danger");
            }
            if (checkOutBtn) updateCheckoutAvailability();
        });
    }

    if (checkOutBtn) {
        checkOutBtn.addEventListener("click", () => {
            const now = new Date();
            if (!Number.isFinite(checkOutDeadlineMs)) {
                showAttendanceAlert("Attendance schedule is unavailable.", "danger");
                return;
            }

            const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            showAttendanceAlert(`Checked out at ${timeStr}. Attendance check-out recorded.`, "success");
            if (checkInStatusBadge) {
                checkInStatusBadge.textContent = `Checked Out (${timeStr})`;
                checkInStatusBadge.className = "badge badge-info";
            }

            checkOutBtn.disabled = true;
            hasCheckedOut = true;
            if (attendanceAction instanceof HTMLInputElement && attendanceForm instanceof HTMLFormElement) {
                attendanceAction.value = "check_out";
                attendanceForm.requestSubmit();
            } else {
                console.error("Attendance form is missing its action field.");
                showAttendanceAlert("Unable to submit attendance. Please reload and try again.", "danger");
            }
        });
    }
});
