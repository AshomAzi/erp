document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-edit-department]").forEach((trigger) => {
        trigger.addEventListener("click", () => {
            document.getElementById("editDepartmentId").value = trigger.dataset.departmentId || "";
            document.getElementById("editDepartmentName").value = trigger.dataset.departmentName || "";
            const headSelect = document.getElementById("editDepartmentHead");
            if (headSelect) headSelect.value = trigger.dataset.departmentHead || "";
        });
    });
});
