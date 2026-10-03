"use strict";

(() => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.closest(".password-input-wrap")?.querySelector("input");
      if (!input) return;
      const showPassword = input.type === "password";
      input.type = showPassword ? "text" : "password";
      button.setAttribute("aria-label", showPassword ? "Ocultar senha" : "Mostrar senha");
      button.setAttribute("title", showPassword ? "Ocultar senha" : "Mostrar senha");
      button.setAttribute("aria-pressed", String(showPassword));
      button.classList.toggle("is-visible", showPassword);
    });
  });

  const cpfField = document.querySelector("#registration-form [name='cpf'], #user-edit-form [name='cpf']");
  cpfField?.addEventListener("input", () => {
    const digits = cpfField.value.replace(/\D/g, "").slice(0, 11);
    const digitsBeforeCursor = cpfField.value.slice(0, cpfField.selectionStart ?? 0).replace(/\D/g, "").length;
    cpfField.value = formatCpf(digits);
    const cursorPosition = formatCpf(digits.slice(0, digitsBeforeCursor)).length;
    cpfField.setSelectionRange(cursorPosition, cursorPosition);
    cpfField.setCustomValidity("");
  });

  const passwordField = document.querySelector("#registration-form [name='password']");
  if (passwordField) {
    const rules = {
      length: (password) => password.length >= 12,
      "letters-numbers": (password) => /\p{L}/u.test(password) && /\p{N}/u.test(password),
      uppercase: (password) => /\p{Lu}/u.test(password),
      symbol: (password) => /[^\p{L}\p{N}\s]/u.test(password),
    };
    const status = document.querySelector("[data-password-strength-status]");
    const ruleElements = document.querySelectorAll("[data-password-rule]");
    const updatePasswordStrength = () => {
      const password = passwordField.value;
      let satisfied = 0;
      ruleElements.forEach((element) => {
        const rule = rules[element.dataset.passwordRule];
        const valid = rule ? rule(password) : false;
        element.classList.toggle("is-satisfied", valid);
        element.setAttribute("aria-checked", String(valid));
        if (valid) satisfied += 1;
      });
      if (status) {
        status.textContent = satisfied === 4 ? "Senha forte" : "Senha fraca";
        status.classList.toggle("is-strong", satisfied === 4);
      }
    };
    passwordField.addEventListener("input", updatePasswordStrength);
    updatePasswordStrength();
  }

  document.querySelectorAll("#registration-form, #user-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const cpfField = form.elements.namedItem("cpf");
      const cpf = cpfField?.value.replace(/\D/g, "") || "";
      if (cpf && cpf.length !== 11) {
        cpfField.setCustomValidity("Informe os 11 dígitos do CPF.");
        cpfField.reportValidity();
        event.preventDefault();
        return;
      }
      cpfField?.setCustomValidity("");

      const email = form.elements.namedItem("email");
      if (email) {
        let domain = "";
        try {
          domain = new URL(`http://${email.value.trim().split("@").pop()}`).hostname;
        } catch {
          domain = "";
        }
        const expectedDomain = new URL("http://egíde.com.br").hostname;
        if (domain !== expectedDomain) {
          email.setCustomValidity("Use um e-mail do domínio institucional @egíde.com.br.");
          email.reportValidity();
          event.preventDefault();
          return;
        }
        email.setCustomValidity("");
      }

      const consent = form.elements.namedItem("biometric_consent");
      if (consent && !consent.checked) {
        consent.setCustomValidity("É necessário consentir com o registro biométrico.");
        consent.reportValidity();
        event.preventDefault();
      } else {
        consent?.setCustomValidity("");
      }

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

  function formatCpf(digits) {
    return digits
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/^(\d{3})\.(\d{3})\.(\d{3})(\d{1,2})$/, "$1.$2.$3-$4");
  }
})();
