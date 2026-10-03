"use strict";

(() => {
  document.querySelectorAll("[data-organization-form]").forEach((form) => {
    const position = form.querySelector("[data-position-select]");
    const positionLabel = form.querySelector("[data-position-label]");
    const positionOpen = form.querySelector("[data-position-open]");
    const positionDialog = form.querySelector("[data-position-dialog]");
    const levelDisplay = form.querySelector("[data-level-display]");
    const area = form.querySelector("[data-area-select]");
    const team = form.querySelector("[data-team-select]");
    const managerFields = form.querySelector("[data-manager-fields]");
    const manager = form.querySelector("[data-manager-select]");
    if (
      !position || !positionLabel || !positionOpen || !positionDialog ||
      !levelDisplay || !area || !team || !managerFields || !manager
    ) return;

    const positionOptions = Array.from(positionDialog.querySelectorAll("[data-position-code]"));

    const updateOptions = () => {
      const selectedPosition = positionOptions.find(
        (option) => position.value === option.dataset.positionCode,
      );
      const parentCodes = (selectedPosition?.dataset.supervisorCodes || "")
        .split(",")
        .filter(Boolean);

      positionLabel.textContent = selectedPosition?.dataset.positionName || "Selecionar cargo...";
      levelDisplay.textContent = selectedPosition
        ? `Nível ${selectedPosition.dataset.level}`
        : "Selecione um cargo";
      positionOpen.setAttribute(
        "aria-label",
        selectedPosition
          ? `Cargo selecionado: ${selectedPosition.dataset.positionName}. Alterar cargo`
          : "Selecionar cargo",
      );

      Array.from(team.options).forEach((option) => {
        if (!option.dataset.areaId) return;
        const belongsToArea = Boolean(area.value) && option.dataset.areaId === area.value;
        option.hidden = !belongsToArea;
        option.disabled = !belongsToArea;
      });
      if (team.selectedOptions[0]?.hidden) team.value = "";

      managerFields.hidden = parentCodes.length === 0;
      manager.disabled = parentCodes.length === 0;
      manager.required = parentCodes.length > 0;
      if (parentCodes.length === 0) manager.value = "";

      Array.from(manager.options).forEach((option) => {
        if (!option.dataset.positionCode) return;
        const allowedPosition = parentCodes.includes(option.dataset.positionCode);
        const globalSupervisor = option.dataset.scope === "GLOBAL";
        const sameArea = option.dataset.areaId === area.value;
        const sameTeam = option.dataset.teamId === team.value;
        const validLocation = globalSupervisor || (sameArea && sameTeam);
        option.hidden = !allowedPosition || !validLocation;
        option.disabled = option.hidden;
      });
      if (manager.selectedOptions[0]?.hidden) manager.value = "";
    };

    positionOpen.addEventListener("click", () => positionDialog.showModal());
    positionDialog.addEventListener("click", (event) => {
      if (event.target === positionDialog) {
        positionDialog.close();
        return;
      }
      const option = event.target.closest("[data-position-code]");
      if (!option) return;
      position.value = option.dataset.positionCode;
      positionDialog.close();
      updateOptions();
    });
    form.querySelector("[data-position-close]")?.addEventListener("click", () =>
      positionDialog.close(),
    );
    area.addEventListener("change", updateOptions);
    team.addEventListener("change", updateOptions);
    updateOptions();
  });
})();
