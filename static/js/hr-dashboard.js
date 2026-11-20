document.addEventListener("DOMContentLoaded", () => {
    const profileModal = document.getElementById("staffProfileModal");
    const profileFields = {
        id: document.getElementById("staffProfileId"),
        name: document.getElementById("staffProfileName"),
        employmentType: document.getElementById("staffProfileEmploymentType"),
        department: document.getElementById("staffProfileDepartment"),
        email: document.getElementById("staffProfileEmail"),
        dateJoined: document.getElementById("staffProfileDateJoined"),
        mentor: document.getElementById("staffProfileMentor"),
    };

    document.querySelectorAll("[data-staff-profile-open]").forEach((button) => {
        button.addEventListener("click", () => {
            if (
                !(profileModal instanceof HTMLDialogElement) ||
                !(profileFields.id instanceof HTMLElement) ||
                !(profileFields.name instanceof HTMLElement) ||
                !(profileFields.employmentType instanceof HTMLElement) ||
                !(profileFields.department instanceof HTMLElement) ||
                !(profileFields.email instanceof HTMLElement) ||
                !(profileFields.dateJoined instanceof HTMLElement) ||
                !(profileFields.mentor instanceof HTMLElement)
            ) {
                console.error("Staff profile dialog is missing a required element.");
                return;
            }

            profileFields.id.textContent = button.dataset.staffId || "Not recorded";
            profileFields.name.textContent = button.dataset.staffName || "Not provided";
            profileFields.employmentType.textContent = button.dataset.staffType || "Not provided";
            profileFields.department.textContent = button.dataset.staffDepartment || "Not provided";
            profileFields.email.textContent = button.dataset.staffEmail || "Not provided";
            profileFields.dateJoined.textContent = button.dataset.staffDateJoined || "Not recorded";
            profileFields.mentor.textContent = button.dataset.staffMentor || "Not assigned";
            profileModal.showModal();
        });
    });
});
