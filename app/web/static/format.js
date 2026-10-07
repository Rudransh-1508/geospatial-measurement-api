// Number formatting shared by the home page and the viewer.
window.SurveyFormat = (() => {
  const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
  const fmtArea = (m2) => (m2 >= 1e6 ? `${nf.format(m2 / 1e6)} km²` : m2 >= 1e4 ? `${nf.format(m2 / 1e4)} ha` : `${nf.format(m2)} m²`);
  const fmtLength = (m) => (m >= 1000 ? `${nf.format(m / 1000)} km` : `${nf.format(m)} m`);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  return { fmtArea, fmtLength, esc };
})();
