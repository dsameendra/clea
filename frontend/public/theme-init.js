// Apply the saved colour scheme before first paint (avoids a light/dark flash).
// A separate file rather than an inline script so a strict Content-Security-Policy can apply.
(function () {
  try {
    var s = JSON.parse(localStorage.getItem("clea.colorScheme") || '"auto"');
    if (s !== "light" && s !== "dark") s = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.setAttribute("data-mantine-color-scheme", s);
  } catch {
    /* storage unavailable: Mantine will apply the system scheme */
  }
})();
