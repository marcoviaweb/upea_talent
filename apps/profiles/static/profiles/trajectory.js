"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const firstInvalid = document.querySelector("[aria-invalid='true']");
  const errorSummary = document.querySelector("#form-error-summary");
  (firstInvalid || errorSummary)?.focus();
});
