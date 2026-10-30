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
    const settingsInput = document.getElementById("settingsJson");
    const scoringInput = document.getElementById("scoringJson");
    const preview = document.getElementById("livePreview");
    let fields = [];
    let settings = {};
    let scoring = {};
    let selectedIndex = null;
    let draggedIndex = null;
    try { fields = JSON.parse(schemaInput.value || "[]"); } catch (_) { fields = []; }
    try { settings = JSON.parse(settingsInput.value || "{}"); } catch (_) { settings = {}; }
    try { scoring = JSON.parse(scoringInput.value || "{}"); } catch (_) { scoring = {}; }

    settings = Object.assign({ progress: "bar", save_draft: true, one_question_per_page: false, previous_label: "قبلی", next_label: "بعدی", submit_label: "ثبت نهایی" }, settings);
    scoring = Object.assign({ mode: "manual", subscales: [], interpretations: [] }, scoring);

    const choiceTypes = new Set(["dropdown", "single_choice", "multiple_choice", "multiselect", "image_choice", "image_multiple_choice", "video_choice", "video_multiple_choice", "audio_choice", "audio_multiple_choice", "quiz", "poll", "price_option", "post_category"]);
    const uploadTypes = new Set(["file", "image_answer", "video_answer", "audio_answer", "signature"]);
    const wideTypes = new Set(["paragraph", "content", "section", "page", "matrix", "repeater"]);
    const typeLabels = {};
    document.querySelectorAll("[data-add]").forEach((button) => { typeLabels[button.dataset.add] = button.dataset.label; });

    function uid() { return "field_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }
    function keyFor(type) { return type + "_" + (fields.length + 1); }
    function newField(type, label) {
      const field = {
        id: uid(), key: keyFor(type), type, label: label || typeLabels[type] || type,
        description: "", placeholder: "", required: false, width: wideTypes.has(type) ? 100 : 50,
        default: "", options: [], validation: {},
        conditional_logic: { enabled: false, match: "all", action: "show", rules: [] },
        scoring: { weight: 1, reverse: false, subscale: "", formula: "" },
        media: { url: "", kind: "", alt: "" }
      };
      if (choiceTypes.has(type)) field.options = [{ label: "گزینه اول", value: "option_1", score: 0 }, { label: "گزینه دوم", value: "option_2", score: 0 }];
      if (["scale", "rating", "slider"].includes(type)) field.validation = { min: 1, max: 5, step: 1 };
      if (uploadTypes.has(type)) field.validation = { max_size_mb: 5, max_files: 1, allowed_extensions: type === "image_answer" || type === "signature" ? ["jpg", "jpeg", "png", "webp"] : (type === "video_answer" ? ["mp4", "webm"] : (type === "audio_answer" ? ["mp3", "wav", "ogg", "m4a"] : ["pdf", "doc", "docx", "jpg", "jpeg", "png"])) };
      if (type === "page") field.progress_title = "مرحله " + toFa(fields.filter((item) => item.type === "page").length + 2);
      return field;
    }

    function addField(type, label, atIndex) {
      const field = newField(type, label);
      if (Number.isInteger(atIndex)) fields.splice(atIndex, 0, field); else fields.push(field);
      selectedIndex = Number.isInteger(atIndex) ? atIndex : fields.length - 1;
      render();
      switchInspector("field");
    }

    document.querySelectorAll("[data-add]").forEach((button) => {
      button.addEventListener("click", () => {
        addField(button.dataset.add, button.dataset.label);
      });
      button.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("application/x-valedgari-field", JSON.stringify({ type: button.dataset.add, label: button.dataset.label }));
        event.dataTransfer.effectAllowed = "copy";
      });
    });

    function syncHidden() {
      schemaInput.value = JSON.stringify(fields);
      settingsInput.value = JSON.stringify(settings);
      scoringInput.value = JSON.stringify(scoring);
    }

    function render() {
      syncHidden();
      document.getElementById("fieldCount").textContent = toFa(fields.length) + " فیلد";
      if (!fields.length) {
        canvas.innerHTML = '<div class="canvas-empty"><i class="fa-solid fa-arrow-pointer"></i><strong>اولین فیلد را اضافه کنید</strong><span>از پالت انتخاب یا به این قسمت Drag کنید.</span></div>';
        preview.innerHTML = '<div class="preview-empty">فیلدهای فرم اینجا نمایش داده می‌شوند.</div>';
        document.getElementById("fieldInspector").innerHTML = '<div class="inspector-empty"><i class="fa-solid fa-sliders"></i><strong>یک فیلد را انتخاب کنید</strong><span>تنظیمات کامل فیلد در این بخش نمایش داده می‌شود.</span></div>';
        return;
      }
      canvas.innerHTML = fields.map((field, index) => `
        <article class="professional-builder-field ${selectedIndex === index ? "selected" : ""} ${field.type === "section" || field.type === "page" ? "layout-field" : ""}" data-index="${index}" draggable="true" style="--field-width:${field.width || 100}%">
          <div class="field-head"><button type="button" class="drag-handle" aria-label="جابجایی"><i class="fa-solid fa-grip-vertical"></i></button>
            <div><span>${escapeHtml(typeLabels[field.type] || field.type)} · ${escapeHtml(field.key || "")}</span><strong>${escapeHtml(field.label || "بدون عنوان")}${field.required ? " <em>*</em>" : ""}</strong></div>
            <div class="field-actions">
              <button type="button" data-action="duplicate" aria-label="کپی"><i class="fa-solid fa-copy"></i></button>
              <button type="button" class="remove" data-action="remove" aria-label="حذف"><i class="fa-solid fa-trash"></i></button>
            </div>
          </div>
          <div class="field-mock">${previewControl(field, true)}</div>
          ${field.description ? `<p>${escapeHtml(field.description)}</p>` : ""}
          <div class="field-flags">${field.conditional_logic && field.conditional_logic.enabled ? '<span><i class="fa-solid fa-code-branch"></i> شرطی</span>' : ""}${field.scoring && (field.scoring.reverse || Number(field.scoring.weight) !== 1) ? '<span><i class="fa-solid fa-calculator"></i> امتیاز</span>' : ""}${field.media && field.media.url ? '<span><i class="fa-solid fa-photo-film"></i> رسانه</span>' : ""}</div>
        </article>`).join("");
      preview.innerHTML = fields.map(previewField).join("");
      if (selectedIndex !== null && fields[selectedIndex]) renderInspector();
    }

    canvas.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      const card = event.target.closest("[data-index]");
      if (!card) return;
      const index = Number(card.dataset.index);
      selectedIndex = index;
      if (button && button.dataset.action === "remove") { fields.splice(index, 1); selectedIndex = fields.length ? Math.min(index, fields.length - 1) : null; }
      if (button && button.dataset.action === "duplicate") { const copy = JSON.parse(JSON.stringify(fields[index])); copy.id = uid(); copy.key = copy.key + "_copy"; fields.splice(index + 1, 0, copy); selectedIndex = index + 1; }
      render();
      switchInspector("field");
    });

    canvas.addEventListener("dragstart", (event) => {
      const card = event.target.closest("[data-index]");
      if (!card) return;
      draggedIndex = Number(card.dataset.index);
      event.dataTransfer.effectAllowed = "move";
      card.classList.add("dragging");
    });
    canvas.addEventListener("dragend", (event) => { const card = event.target.closest("[data-index]"); if (card) card.classList.remove("dragging"); draggedIndex = null; });
    canvas.addEventListener("dragover", (event) => { event.preventDefault(); event.dataTransfer.dropEffect = draggedIndex === null ? "copy" : "move"; canvas.classList.add("is-dragover"); });
    canvas.addEventListener("dragleave", (event) => { if (!canvas.contains(event.relatedTarget)) canvas.classList.remove("is-dragover"); });
    canvas.addEventListener("drop", (event) => {
      event.preventDefault(); canvas.classList.remove("is-dragover");
      const over = event.target.closest("[data-index]");
      const targetIndex = over ? Number(over.dataset.index) : fields.length;
      const paletteData = event.dataTransfer.getData("application/x-valedgari-field");
      if (paletteData) { try { const item = JSON.parse(paletteData); addField(item.type, item.label, targetIndex); } catch (_) { /* ignore malformed drag */ } return; }
      if (draggedIndex === null || draggedIndex === targetIndex) return;
      const moved = fields.splice(draggedIndex, 1)[0];
      const adjusted = draggedIndex < targetIndex ? targetIndex - 1 : targetIndex;
      fields.splice(adjusted, 0, moved); selectedIndex = adjusted; render();
    });

    function renderInspector() {
      const field = fields[selectedIndex];
      if (!field) return;
      const optionsText = (field.options || []).map((item) => [item.label || "", item.value || "", item.score ?? 0, item.media_url || ""].join(" | ")).join("\n");
      const logic = field.conditional_logic || { enabled: false, match: "all", action: "show", rules: [] };
      const validation = field.validation || {};
      document.getElementById("fieldInspector").innerHTML = `
        <div class="inspector-selected-head"><div><span>${escapeHtml(typeLabels[field.type] || field.type)}</span><h2>${escapeHtml(field.label || "فیلد")}</h2></div><code>${escapeHtml(field.key || "")}</code></div>
        <div class="inspector-section"><h3>عمومی</h3><label>عنوان<input class="form-control" data-field-prop="label" value="${escapeAttr(field.label)}"></label><label>کلید یکتا<input class="form-control" data-field-prop="key" value="${escapeAttr(field.key)}" dir="ltr"></label><label>توضیح<textarea class="form-control" data-field-prop="description" rows="2">${escapeHtml(field.description || "")}</textarea></label><label>Placeholder<input class="form-control" data-field-prop="placeholder" value="${escapeAttr(field.placeholder || "")}"></label><div class="row g-2"><label class="col-6">عرض<select class="form-select" data-field-prop="width">${[25,33,50,66,75,100].map((value) => `<option value="${value}" ${Number(field.width) === value ? "selected" : ""}>${toFa(value)}٪</option>`).join("")}</select></label><label class="col-6">مقدار پیش‌فرض<input class="form-control" data-field-prop="default" value="${escapeAttr(field.default || "")}"></label></div><label class="form-check"><input class="form-check-input" type="checkbox" data-field-prop="required" ${field.required ? "checked" : ""}><span>پاسخ الزامی</span></label></div>
        ${choiceTypes.has(field.type) ? `<div class="inspector-section"><h3>گزینه‌ها</h3><textarea class="form-control code-editor" data-field-special="options" rows="7" dir="rtl">${escapeHtml(optionsText)}</textarea><small>هر خط: عنوان | مقدار | امتیاز | آدرس رسانه</small></div>` : ""}
        <div class="inspector-section"><h3>اعتبارسنجی</h3><textarea class="form-control code-editor" data-field-special="validation" rows="5" dir="ltr">${escapeHtml(JSON.stringify(validation, null, 2))}</textarea><small>min، max، pattern، allowed_extensions، max_size_mb و…</small></div>
        <div class="inspector-section"><h3>منطق شرطی</h3><label class="form-check"><input class="form-check-input" type="checkbox" data-field-special="condition-enabled" ${logic.enabled ? "checked" : ""}><span>فعال‌سازی شرط</span></label><div class="row g-2"><label class="col-6">تطبیق<select class="form-select" data-field-special="condition-match"><option value="all" ${logic.match !== "any" ? "selected" : ""}>همه شروط</option><option value="any" ${logic.match === "any" ? "selected" : ""}>یکی از شروط</option></select></label><label class="col-6">عملکرد<select class="form-select" data-field-special="condition-action"><option value="show" ${logic.action !== "hide" ? "selected" : ""}>نمایش</option><option value="hide" ${logic.action === "hide" ? "selected" : ""}>پنهان‌سازی</option></select></label></div><textarea class="form-control code-editor" data-field-special="condition-rules" rows="5" dir="ltr">${escapeHtml(JSON.stringify(logic.rules || [], null, 2))}</textarea><small>حداکثر ۲۰ شرط با field، operator و value.</small></div>
        <div class="inspector-section"><h3>امتیازدهی</h3><div class="row g-2"><label class="col-6">وزن<input class="form-control" type="number" step="0.1" data-field-special="weight" value="${Number((field.scoring || {}).weight || 1)}"></label><label class="col-6">خرده‌مقیاس<input class="form-control" data-field-special="subscale" value="${escapeAttr((field.scoring || {}).subscale || "")}" dir="ltr"></label></div><label class="form-check"><input class="form-check-input" type="checkbox" data-field-special="reverse" ${(field.scoring || {}).reverse ? "checked" : ""}><span>نمره‌گذاری معکوس</span></label></div>
        <div class="inspector-section"><h3>رسانه سؤال</h3><label>آدرس خصوصی/داخلی<input class="form-control" data-field-special="media-url" value="${escapeAttr((field.media || {}).url || "")}" dir="ltr" placeholder="/admin/forms/media/12"></label><label>متن جایگزین<input class="form-control" data-field-special="media-alt" value="${escapeAttr((field.media || {}).alt || "")}"></label></div>`;
    }

    document.getElementById("fieldInspector").addEventListener("input", (event) => {
      const field = fields[selectedIndex]; if (!field) return;
      const prop = event.target.dataset.fieldProp;
      if (prop) field[prop] = event.target.type === "checkbox" ? event.target.checked : (prop === "width" ? Number(event.target.value) : event.target.value);
      const special = event.target.dataset.fieldSpecial;
      field.conditional_logic = field.conditional_logic || { enabled: false, match: "all", action: "show", rules: [] };
      field.scoring = field.scoring || { weight: 1, reverse: false, subscale: "" };
      field.media = field.media || { url: "", kind: "", alt: "" };
      if (special === "options") field.options = event.target.value.split("\n").filter(Boolean).slice(0, 100).map((line, index) => { const parts = line.split("|").map((item) => item.trim()); return { label: parts[0] || `گزینه ${index + 1}`, value: parts[1] || `option_${index + 1}`, score: Number(parts[2] || 0), media_url: parts[3] || "" }; });
      if (special === "validation") { try { field.validation = JSON.parse(event.target.value || "{}"); event.target.classList.remove("is-invalid"); } catch (_) { event.target.classList.add("is-invalid"); } }
      if (special === "condition-enabled") field.conditional_logic.enabled = event.target.checked;
      if (special === "condition-match") field.conditional_logic.match = event.target.value;
      if (special === "condition-action") field.conditional_logic.action = event.target.value;
      if (special === "condition-rules") { try { field.conditional_logic.rules = JSON.parse(event.target.value || "[]"); event.target.classList.remove("is-invalid"); } catch (_) { event.target.classList.add("is-invalid"); } }
      if (special === "weight") field.scoring.weight = Number(event.target.value || 1);
      if (special === "subscale") field.scoring.subscale = event.target.value;
      if (special === "reverse") field.scoring.reverse = event.target.checked;
      if (special === "media-url") field.media.url = event.target.value;
      if (special === "media-alt") field.media.alt = event.target.value;
      syncHidden();
      const card = canvas.querySelector(`[data-index="${selectedIndex}"]`);
      if (card && prop === "label") card.querySelector(".field-head strong").innerHTML = escapeHtml(field.label || "بدون عنوان") + (field.required ? " <em>*</em>" : "");
      if (card && prop === "key") card.querySelector(".field-head span").textContent = (typeLabels[field.type] || field.type) + " · " + field.key;
      if (card && prop === "width") card.style.setProperty("--field-width", (field.width || 100) + "%");
      if (card && prop === "required") card.querySelector(".field-head strong").innerHTML = escapeHtml(field.label || "بدون عنوان") + (field.required ? " <em>*</em>" : "");
      preview.innerHTML = fields.map(previewField).join("");
    });

    document.querySelectorAll("[data-setting]").forEach((input) => {
      const key = input.dataset.setting;
      if (input.type === "checkbox") input.checked = Boolean(settings[key]); else input.value = settings[key] ?? "";
      input.addEventListener("input", () => { settings[key] = input.type === "checkbox" ? input.checked : input.value; syncHidden(); preview.innerHTML = fields.map(previewField).join(""); });
    });
    document.querySelectorAll("[data-scoring]").forEach((input) => {
      const key = input.dataset.scoring;
      if (key === "subscales") input.value = (scoring.subscales || []).map((item) => `${item.key || ""}: ${item.label || ""}`).join("\n");
      else if (key === "interpretations") input.value = JSON.stringify(scoring.interpretations || [], null, 2);
      else input.value = scoring[key] ?? "";
      input.addEventListener("input", () => {
        if (key === "subscales") scoring.subscales = input.value.split("\n").filter(Boolean).map((line) => { const parts = line.split(":"); return { key: (parts.shift() || "").trim(), label: parts.join(":").trim() }; });
        else if (key === "interpretations") { try { scoring.interpretations = JSON.parse(input.value || "[]"); input.classList.remove("is-invalid"); } catch (_) { input.classList.add("is-invalid"); } }
        else scoring[key] = input.value;
        syncHidden();
      });
    });

    function switchInspector(name) {
      document.querySelectorAll("[data-inspector-tab]").forEach((button) => button.classList.toggle("active", button.dataset.inspectorTab === name));
      document.querySelectorAll("[data-inspector-pane]").forEach((pane) => pane.classList.toggle("active", pane.dataset.inspectorPane === name));
    }
    document.querySelectorAll("[data-inspector-tab]").forEach((button) => button.addEventListener("click", () => switchInspector(button.dataset.inspectorTab)));
    document.querySelectorAll("[data-studio-view]").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll("[data-studio-view]").forEach((item) => item.classList.remove("active")); button.classList.add("active"); canvas.classList.toggle("mobile-view", button.dataset.studioView === "mobile"); }));
    const formTitleInput = document.getElementById("formTitleInput");
    formTitleInput.addEventListener("input", () => { document.getElementById("canvasTitle").textContent = formTitleInput.value || "فرم جدید"; });
    const paletteSearch = document.getElementById("paletteSearch");
    paletteSearch.addEventListener("input", () => { const query = paletteSearch.value.trim().toLowerCase(); document.querySelectorAll("[data-add]").forEach((button) => { button.hidden = query && !button.textContent.trim().toLowerCase().includes(query); }); });

    builder.addEventListener("submit", (event) => {
      const invalidEditors = builder.querySelectorAll(".code-editor.is-invalid");
      if (invalidEditors.length) { event.preventDefault(); invalidEditors[0].focus(); return; }
      syncHidden();
    });
    render();
  }

  function previewField(field) {
    if (field.type === "section") return `<div class="preview-section"><strong>${escapeHtml(field.label)}</strong><p>${escapeHtml(field.description || "")}</p></div>`;
    if (field.type === "page") return `<div class="preview-page-break"><i class="fa-solid fa-arrow-left"></i>${escapeHtml(field.progress_title || field.label)}</div>`;
    if (field.type === "content") return `<div class="preview-content">${escapeHtml(field.description || field.label)}</div>`;
    const required = field.required ? " *" : "";
    const media = field.media && field.media.url ? `<div class="preview-media"><i class="fa-solid fa-photo-film"></i>${escapeHtml(field.media.alt || "رسانه سؤال")}</div>` : "";
    return `<div class="preview-field" style="width:${Number(field.width || 100)}%"><label>${escapeHtml(field.label)}${required}</label>${media}${previewControl(field, false)}${field.description ? `<small>${escapeHtml(field.description)}</small>` : ""}</div>`;
  }

  function previewControl(field, compact) {
    const type = field.type;
    if (["paragraph", "address", "post_content", "post_excerpt"].includes(type)) return `<textarea class="form-control" rows="${compact ? 2 : 3}" disabled placeholder="${escapeAttr(field.placeholder || "")}"></textarea>`;
    if (["dropdown", "multiselect", "chained", "post_category"].includes(type)) return '<select class="form-select" disabled><option>انتخاب کنید…</option></select>';
    if (["single_choice", "multiple_choice", "image_choice", "image_multiple_choice", "video_choice", "video_multiple_choice", "audio_choice", "audio_multiple_choice", "quiz", "poll", "price_option"].includes(type)) return `<div class="preview-options">${(field.options || []).slice(0, compact ? 3 : 6).map((option) => `<span><i class="fa-regular ${["multiple_choice", "image_multiple_choice", "video_multiple_choice", "audio_multiple_choice"].includes(type) ? "fa-square" : "fa-circle"}"></i>${escapeHtml(option.label || "گزینه")}</span>`).join("")}</div>`;
    if (["scale", "rating"].includes(type)) { const min = Number((field.validation || {}).min || 1); const max = Number((field.validation || {}).max || 5); return `<div class="preview-scale">${Array.from({ length: Math.min(10, max - min + 1) }, (_, index) => `<span>${toFa(min + index)}</span>`).join("")}</div>`; }
    if (type === "slider") return '<input type="range" class="form-range" disabled>';
    if (["file", "image_answer", "video_answer", "audio_answer", "signature"].includes(type)) return '<div class="preview-upload"><i class="fa-solid fa-cloud-arrow-up"></i>انتخاب فایل خصوصی</div>';
    if (type === "consent") return '<label class="preview-consent"><input type="checkbox" disabled> متن رضایت‌نامه را می‌پذیرم</label>';
    if (["matrix", "repeater", "list"].includes(type)) return '<div class="preview-table"><span></span><span></span><span></span></div>';
    if (type === "captcha") return '<div class="preview-captcha"><strong>۷ + ۲ = ؟</strong><input class="form-control" disabled></div>';
    if (["number", "quantity", "calculation", "total", "shipping", "product"].includes(type)) return '<input type="number" class="form-control" disabled>';
    const htmlType = ({ email: "email", phone: "tel", date: "date", time: "time", url: "url", password: "password" })[type] || "text";
    return `<input type="${htmlType}" class="form-control" disabled placeholder="${escapeAttr(field.placeholder || "")}">`;
  }

  const runner = document.getElementById("dynamicFormRunner");
  if (runner) {
    const fieldContainer = document.getElementById("runnerFields");
    const previousButton = runner.querySelector("[data-runner-prev]");
    const nextButton = runner.querySelector("[data-runner-next]");
    const submitButton = runner.querySelector("[data-runner-submit]");
    const progressBar = document.querySelector("[data-progress-bar]");
    const progressLabel = document.querySelector("[data-progress-label]");
    const progressSteps = document.querySelector("[data-progress-steps]");
    let currentPage = 0;
    const pages = [[]];

    Array.from(fieldContainer.children).forEach((element) => {
      if (element.matches("[data-page-break]")) {
        if (pages[pages.length - 1].length) pages.push([]);
        return;
      }
      pages[pages.length - 1].push(element);
    });
    if (!pages[pages.length - 1].length && pages.length > 1) pages.pop();

    function answerFor(key) {
      const controls = Array.from(runner.querySelectorAll(`[name="answer_${CSS.escape(key)}"]`));
      if (!controls.length) return "";
      if (controls[0].type === "checkbox") {
        const checked = controls.filter((control) => control.checked).map((control) => control.value);
        return controls.length === 1 ? (checked[0] || "") : checked;
      }
      if (controls[0].type === "radio") {
        const checked = controls.find((control) => control.checked);
        return checked ? checked.value : "";
      }
      return controls[0].value;
    }

    function ruleMatches(rule) {
      const actual = answerFor(rule.field || "");
      const expected = rule.value ?? "";
      if (rule.operator === "not_equals") return String(actual) !== String(expected);
      if (rule.operator === "contains") return Array.isArray(actual) ? actual.map(String).includes(String(expected)) : String(actual).includes(String(expected));
      if (rule.operator === "greater_than") return Number(actual) > Number(expected);
      if (rule.operator === "less_than") return Number(actual) < Number(expected);
      if (rule.operator === "is_empty") return actual === "" || (Array.isArray(actual) && !actual.length);
      if (rule.operator === "is_not_empty") return actual !== "" && (!Array.isArray(actual) || actual.length > 0);
      return String(actual) === String(expected);
    }

    function applyConditions() {
      runner.querySelectorAll("[data-field-key]").forEach((element) => {
        let logic = {};
        try { logic = JSON.parse(element.dataset.logic || "{}"); } catch (_) { logic = {}; }
        let visible = true;
        if (logic.enabled && Array.isArray(logic.rules) && logic.rules.length) {
          const matches = logic.rules.map(ruleMatches);
          const matched = logic.match === "any" ? matches.some(Boolean) : matches.every(Boolean);
          visible = logic.action === "hide" ? !matched : matched;
        }
        element.classList.toggle("condition-hidden", !visible);
        element.querySelectorAll("input,select,textarea").forEach((control) => { control.disabled = !visible; });
      });
    }

    function visibleElements(page) {
      return page.filter((element) => !element.classList.contains("condition-hidden"));
    }

    function renderPage() {
      applyConditions();
      pages.forEach((page, pageIndex) => page.forEach((element) => { element.hidden = pageIndex !== currentPage; }));
      if (previousButton) previousButton.hidden = currentPage === 0;
      const atEnd = currentPage === pages.length - 1;
      if (nextButton) nextButton.hidden = atEnd;
      if (submitButton) submitButton.hidden = !atEnd;
      const percent = Math.round(((currentPage + 1) / Math.max(1, pages.length)) * 100);
      if (progressBar) progressBar.style.width = `${percent}%`;
      if (progressLabel) progressLabel.textContent = `${toFa(percent)}٪`;
      if (progressSteps) {
        progressSteps.innerHTML = pages.map((_, index) => `<span class="${index === currentPage ? "active" : ""}">${toFa(index + 1)}</span>`).join("");
      }
    }

    function pageIsValid() {
      for (const element of visibleElements(pages[currentPage])) {
        for (const control of element.querySelectorAll("input,select,textarea")) {
          if (!control.disabled && !control.checkValidity()) {
            control.reportValidity();
            return false;
          }
        }
      }
      return true;
    }

    runner.addEventListener("input", () => {
      applyConditions();
      runner.querySelectorAll(".runner-slider").forEach((wrapper) => {
        const input = wrapper.querySelector("input");
        const output = wrapper.querySelector("output");
        if (input && output) output.textContent = toFa(input.value);
      });
    });
    if (nextButton) nextButton.addEventListener("click", () => {
      if (pageIsValid() && currentPage < pages.length - 1) { currentPage += 1; renderPage(); runner.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" }); }
    });
    if (previousButton) previousButton.addEventListener("click", () => {
      if (currentPage > 0) { currentPage -= 1; renderPage(); runner.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" }); }
    });
    runner.addEventListener("submit", (event) => {
      applyConditions();
      if (event.submitter && event.submitter.value === "submit" && !runner.checkValidity()) {
        event.preventDefault();
        runner.reportValidity();
      }
    });
    renderPage();
  }

  function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = value || "";
    return element.innerHTML;
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function toFa(value) {
    return String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
  }
})(jQuery);

