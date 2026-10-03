// =========================================================
// SCRIPT.JS
// Small helper functions shared across pages.
// =========================================================

// Toggle the sidebar on mobile screens
function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("show");
    document.getElementById("sidebarOverlay").classList.toggle("show");
}

// Ask the user to confirm before cancelling an appointment.
// Used on <form> elements like:
// <form onsubmit="return confirmCancel(event)">
function confirmCancel(event) {
    const confirmed = window.confirm("Are you sure you want to cancel this appointment?");
    if (!confirmed) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Generic confirmation for other destructive actions (deactivate, etc.)
function confirmAction(message) {
    return window.confirm(message);
}

// Auto-hide Bootstrap alert messages after a few seconds
document.addEventListener("DOMContentLoaded", function () {
    const alerts = document.querySelectorAll(".alert-auto-hide");
    alerts.forEach(function (alertEl) {
        setTimeout(function () {
            alertEl.classList.remove("show");
            alertEl.classList.add("fade");
            setTimeout(function () { alertEl.remove(); }, 400);
        }, 4000);
    });
});
