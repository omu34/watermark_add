const opacitySlider = document.querySelector("#opacity");
const opacityValue = document.querySelector("#opacity-value");

if (opacitySlider && opacityValue) {
  opacitySlider.addEventListener("input", () => {
    opacityValue.textContent = opacitySlider.value;
  });
}

const errorAlert = document.querySelector("[data-alert-message]");
if (errorAlert) {
  window.alert(errorAlert.textContent);
}
