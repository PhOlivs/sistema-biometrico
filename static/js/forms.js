"use strict";

(() => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll("#registration-form, #user-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const cpfField = form.elements.namedItem("cpf");
      const cpf = cpfField?.value.replace(/\D/g, "") || "";
      if (cpf && !isValidCpf(cpf)) {
        cpfField.setCustomValidity("Informe um CPF válido.");
        cpfField.reportValidity();
        event.preventDefault();
        return;
      }
      cpfField?.setCustomValidity("");

      const password = form.elements.namedItem("password");
      const confirmation = form.elements.namedItem("password_confirmation");
      if (password && confirmation && password.value !== confirmation.value) {
        confirmation.setCustomValidity("A confirmação de senha não confere.");
        confirmation.reportValidity();
        event.preventDefault();
      } else {
        confirmation?.setCustomValidity("");
      }
    });
  });

  function isValidCpf(cpf) {
    if (!/^\d{11}$/.test(cpf) || /^(\d)\1{10}$/.test(cpf)) return false;
    for (let position = 9; position < 11; position += 1) {
      let sum = 0;
      for (let index = 0; index < position; index += 1) {
        sum += Number(cpf[index]) * (position + 1 - index);
      }
      let check = (sum * 10) % 11;
      if (check === 10) check = 0;
      if (check !== Number(cpf[position])) return false;
    }
    return true;
  }
})();
