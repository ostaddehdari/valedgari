$(function () {
  const roleSelect = document.querySelector('.assignment-role select[name="target_ref"]');
  if (!roleSelect) return;
  const existing = new Set(Array.from(roleSelect.options).map((item) => item.value));
  [
    ["child", "پروفایل همه فرزندان"],
    ["organization", "پروفایل همه سازمان‌ها"],
  ].forEach(([value, label]) => {
    if (!existing.has(value)) roleSelect.add(new Option(label, value));
  });
});
