(function ($) {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nav = document.querySelector(".site-nav");
  const syncNav = () => nav && nav.classList.toggle("scrolled", window.scrollY > 18);
  syncNav();
  window.addEventListener("scroll", syncNav, { passive: true });

  const dashboardShell = document.querySelector("[data-dashboard-shell]");
  if (dashboardShell) {
    const body = document.body;
    const sidebar = document.getElementById("appSidebar");
    const toggleButton = document.querySelector("[data-sidebar-toggle]");
    const collapseButton = document.querySelector("[data-sidebar-collapse]");
    const closeControls = document.querySelectorAll("[data-sidebar-close]");
    const mobileViewport = window.matchMedia("(max-width: 991px)");
    const storageKey = "valedgari.sidebar.collapsed";

    const readCollapsedPreference = () => {
      try { return window.localStorage.getItem(storageKey) === "true"; } catch (_) { return false; }
    };
    const saveCollapsedPreference = (value) => {
      try { window.localStorage.setItem(storageKey, String(value)); } catch (_) { /* storage may be blocked */ }
    };
    const syncSidebarState = () => {
      const mobileOpen = body.classList.contains("sidebar-mobile-open");
      const collapsed = body.classList.contains("sidebar-collapsed");
      if (toggleButton) toggleButton.setAttribute("aria-expanded", String(mobileViewport.matches ? mobileOpen : !collapsed));
      if (collapseButton) {
        collapseButton.setAttribute("aria-expanded", String(!collapsed));
        collapseButton.setAttribute("aria-label", collapsed ? "بازکردن سایدبار" : "جمع‌کردن سایدبار");
      }
      if (sidebar) sidebar.setAttribute("aria-hidden", String(mobileViewport.matches && !mobileOpen));
    };
    const closeMobileSidebar = () => {
      body.classList.remove("sidebar-mobile-open");
      syncSidebarState();
    };
    const toggleDesktopSidebar = () => {
      const collapsed = body.classList.toggle("sidebar-collapsed");
      saveCollapsedPreference(collapsed);
      syncSidebarState();
    };

    if (!mobileViewport.matches && readCollapsedPreference()) body.classList.add("sidebar-collapsed");
    if (toggleButton) toggleButton.addEventListener("click", () => {
      if (mobileViewport.matches) {
        body.classList.toggle("sidebar-mobile-open");
        syncSidebarState();
      } else {
        toggleDesktopSidebar();
      }
    });
    if (collapseButton) collapseButton.addEventListener("click", toggleDesktopSidebar);
    closeControls.forEach((control) => control.addEventListener("click", closeMobileSidebar));
    document.querySelectorAll(".sidebar-link").forEach((link) => link.addEventListener("click", () => {
      if (mobileViewport.matches) closeMobileSidebar();
    }));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && body.classList.contains("sidebar-mobile-open")) {
        closeMobileSidebar();
        if (toggleButton) toggleButton.focus();
      }
    });
    const handleViewportChange = () => {
      body.classList.remove("sidebar-mobile-open");
      if (mobileViewport.matches) body.classList.remove("sidebar-collapsed");
      else body.classList.toggle("sidebar-collapsed", readCollapsedPreference());
      syncSidebarState();
    };
    if (mobileViewport.addEventListener) mobileViewport.addEventListener("change", handleViewportChange);
    else mobileViewport.addListener(handleViewportChange);
    syncSidebarState();
  }

  const animated = document.querySelectorAll("[data-animate]");
  if (reduceMotion || !("IntersectionObserver" in window)) {
    animated.forEach((item) => item.classList.add("animate__animated", item.dataset.animate || "animate__fadeInUp"));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("animate__animated", entry.target.dataset.animate || "animate__fadeInUp");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });
    animated.forEach((item) => observer.observe(item));
  }

  $(document).on("click", "[data-password-toggle]", function () {
    const input = document.querySelector(this.dataset.passwordToggle);
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
    $(this).find("i").toggleClass("fa-eye fa-eye-slash");
  });

  $(document).on("click", ".severity-demo button", function () {
    $(this).addClass("active").siblings().removeClass("active");
  });

  $(document).on("click", "[data-assistant-prompt]", function () {
    const input = document.getElementById("assistantMessage");
    if (!input) return;
    input.value = this.dataset.assistantPrompt || "";
    input.focus();
  });

  $(document).on("click", ".response-card", function () {
    $(this).addClass("selected").siblings().removeClass("selected");
    const icon = $(this).hasClass("good") ? "fa-circle-check" : ($(this).hasClass("wrong") ? "fa-triangle-exclamation" : "fa-circle-info");
    $("#scenarioFeedback").html('<i class="fa-solid ' + icon + '"></i><span>' + $(this).data("feedback") + "</span>");
  });

  const builder = document.getElementById("formBuilder");
  if (builder) initFormBuilder();

  function initFormBuilder() {
    const canvas = document.getElementById("builderCanvas");
    const schemaInput = document.getElementById("schemaJson");
    const preview = document.getElementById("livePreview");
    let fields = [];
    try { fields = JSON.parse(schemaInput.value || "[]"); } catch (_) { fields = []; }

    document.querySelectorAll("[data-field-type]").forEach((button) => {
      button.addEventListener("click", () => {
        fields.push({
          id: "field_" + Date.now(),
          type: button.dataset.fieldType,
          label: button.dataset.fieldLabel,
          required: false,
          help: ""
        });
        render();
      });
    });

    function render() {
      schemaInput.value = JSON.stringify(fields);
      document.getElementById("fieldCount").textContent = toFa(fields.length) + " فیلد";
      if (!fields.length) {
        canvas.innerHTML = '<div class="canvas-empty"><i class="fa-solid fa-wand-magic-sparkles"></i><strong>فرم را بسازید</strong><span>یک نوع فیلد از ستون کناری انتخاب کنید.</span></div>';
        preview.innerHTML = '<div class="preview-empty">فیلدهای فرم اینجا نمایش داده می‌شوند.</div>';
        return;
      }
      canvas.innerHTML = fields.map((field, index) => `
        <div class="builder-field" data-index="${index}">
          <div class="field-head">
            <i class="fa-solid fa-grip-vertical"></i>
            <input class="field-label-input" data-action="label" value="${escapeHtml(field.label)}" aria-label="عنوان فیلد">
            <div class="field-actions">
              <button type="button" data-action="up" aria-label="انتقال به بالا"><i class="fa-solid fa-arrow-up"></i></button>
              <button type="button" data-action="down" aria-label="انتقال به پایین"><i class="fa-solid fa-arrow-down"></i></button>
              <button type="button" class="remove" data-action="remove" aria-label="حذف"><i class="fa-solid fa-trash"></i></button>
            </div>
          </div>
          <div class="field-meta"><span>نوع: ${typeName(field.type)}</span><label><input type="checkbox" data-action="required" ${field.required ? "checked" : ""}> الزامی</label></div>
        </div>`).join("");
      preview.innerHTML = fields.map(previewField).join("");
    }

    canvas.addEventListener("input", (event) => {
      const card = event.target.closest("[data-index]");
      if (!card) return;
      const field = fields[Number(card.dataset.index)];
      if (event.target.dataset.action === "label") field.label = event.target.value;
      if (event.target.dataset.action === "required") field.required = event.target.checked;
      schemaInput.value = JSON.stringify(fields);
      preview.innerHTML = fields.map(previewField).join("");
    });

    canvas.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      const card = event.target.closest("[data-index]");
      if (!button || !card) return;
      const index = Number(card.dataset.index);
      if (button.dataset.action === "remove") fields.splice(index, 1);
      if (button.dataset.action === "up" && index > 0) [fields[index - 1], fields[index]] = [fields[index], fields[index - 1]];
      if (button.dataset.action === "down" && index < fields.length - 1) [fields[index + 1], fields[index]] = [fields[index], fields[index + 1]];
      render();
    });

    builder.addEventListener("submit", () => { schemaInput.value = JSON.stringify(fields); });
    render();
  }

  function previewField(field) {
    const required = field.required ? " *" : "";
    let control = '<input class="form-control" disabled>';
    if (field.type === "textarea") control = '<textarea class="form-control" rows="2" disabled></textarea>';
    if (field.type === "select") control = '<select class="form-select" disabled><option>انتخاب کنید…</option></select>';
    if (field.type === "radio") control = '<div><label class="ms-2"><input type="radio" disabled> گزینه اول</label><label><input type="radio" disabled> گزینه دوم</label></div>';
    if (field.type === "scale") control = '<div class="preview-scale"><span>۱</span><span>۲</span><span>۳</span><span>۴</span><span>۵</span></div>';
    if (field.type === "number") control = '<input type="number" class="form-control" disabled>';
    return '<div class="preview-field"><label>' + escapeHtml(field.label) + required + "</label>" + control + "</div>";
  }

  function typeName(type) {
    return ({ text: "متن کوتاه", textarea: "متن بلند", number: "عدد", radio: "تک‌انتخابی", select: "فهرست", scale: "مقیاس" })[type] || type;
  }

  function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = value || "";
    return element.innerHTML;
  }

  function toFa(value) {
    return String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
  }
})(jQuery);

