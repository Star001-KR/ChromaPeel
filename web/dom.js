// Tiny DOM helpers shared across modules.
export const $ = (id) => document.getElementById(id);

export function setStatus(text) {
  $('status').textContent = text;
}

export function setCropStatus(text) {
  $('cropStatus').textContent = text;
}
