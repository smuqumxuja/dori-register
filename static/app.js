const loginView = document.querySelector("#loginView");
const appView = document.querySelector("#appView");
const loginForm = document.querySelector("#loginForm");
const filterForm = document.querySelector("#filterForm");
const medicineForm = document.querySelector("#medicineForm");
const usageForm = document.querySelector("#usageForm");
const userForm = document.querySelector("#userForm");
const buildingForm = document.querySelector("#buildingForm");
const departmentForm = document.querySelector("#departmentForm");
const toast = document.querySelector("#toast");
const captchaToken = document.querySelector("#captchaToken");
const captchaQuestion = document.querySelector("#captchaQuestion");
const exportBtn = document.querySelector("#exportBtn");
const refreshBtn = document.querySelector("#refreshBtn");
const entriesBody = document.querySelector("#entriesBody");
const medicinesBody = document.querySelector("#medicinesBody");
const usersBody = document.querySelector("#usersBody");
const buildingsBody = document.querySelector("#buildingsBody");
const departmentsBody = document.querySelector("#departmentsBody");
const userStatsBody = document.querySelector("#userStatsBody");
const auditLogsBody = document.querySelector("#auditLogsBody");
const entryEmptyState = document.querySelector("#entryEmptyState");
const medicineEmptyState = document.querySelector("#medicineEmptyState");
const departmentFilterField = document.querySelector("#departmentFilterField");
const medicineSearch = document.querySelector("#medicineSearch");
const usageMedicineSearch = document.querySelector("#usageMedicineSearch");
const usageMedicineSelect = document.querySelector("#usageMedicineSelect");
const usageStockHint = document.querySelector("#usageStockHint");
const saveMedicineBtn = document.querySelector("#saveMedicineBtn");
const cancelMedicineEditBtn = document.querySelector("#cancelMedicineEditBtn");
const saveBuildingBtn = document.querySelector("#saveBuildingBtn");
const cancelBuildingEditBtn = document.querySelector("#cancelBuildingEditBtn");
const saveDepartmentBtn = document.querySelector("#saveDepartmentBtn");
const cancelDepartmentEditBtn = document.querySelector("#cancelDepartmentEditBtn");
const saveUserBtn = document.querySelector("#saveUserBtn");
const cancelUserEditBtn = document.querySelector("#cancelUserEditBtn");
const userPasswordInput = userForm.elements.namedItem("password");
const managementPanels = document.querySelectorAll("[data-management-panel]");
const managementButtons = document.querySelectorAll("[data-management-target]");

const views = {
  dashboard: document.querySelector("#dashboardView"),
  medicine: document.querySelector("#medicineView"),
  usage: document.querySelector("#usageView"),
  management: document.querySelector("#managementView"),
};

const state = {
  entries: [],
  medicines: [],
  users: [],
  adminActivity: { user_stats: [], logs: [], totals: {} },
  buildings: [],
  departments: [],
  filters: new URLSearchParams(),
  user: null,
  roles: {},
  permissions: {},
  options: {},
  currentView: "dashboard",
  managementSection: "buildings",
};

function isSuperAdmin() {
  return state.user?.role === "super_admin";
}

function canWrite() {
  return Boolean(state.permissions.can_write);
}

function canManage() {
  return Boolean(state.permissions.can_manage_users);
}

function canManageDepartments() {
  return Boolean(state.permissions.can_manage_departments);
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/\.?0+$/, "");
}

function localDateTimeParts() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return {
    date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
    time: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
  };
}

function setCurrentDateTime(dateInput, timeInput) {
  const current = localDateTimeParts();
  dateInput.value = current.date;
  timeInput.value = current.time;
}

function setMedicineCurrentDateTime() {
  setCurrentDateTime(
    medicineForm.elements.namedItem("received_date"),
    medicineForm.elements.namedItem("received_time"),
  );
}

function setUsageCurrentDateTime() {
  setCurrentDateTime(
    usageForm.elements.namedItem("entry_date"),
    usageForm.elements.namedItem("entry_time"),
  );
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("application/json") ? await response.json() : {};
  if (response.status === 401 && url !== "/api/me") {
    showLogin();
    throw new Error(data.error || "Tizimga qayta kiring");
  }
  if (!response.ok) {
    throw new Error(data.error || "So'rov bajarilmadi");
  }
  return data;
}

function formToObject(form) {
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  Object.keys(payload).forEach((key) => {
    if (typeof payload[key] === "string") payload[key] = payload[key].trim();
  });
  return payload;
}

async function loadCaptcha() {
  const data = await fetchJson("/api/captcha");
  captchaToken.value = data.captcha.token;
  captchaQuestion.textContent = data.captcha.question;
  loginForm.elements.namedItem("captcha_answer").value = "";
}

function showLogin() {
  state.user = null;
  state.permissions = {};
  appView.hidden = true;
  loginView.hidden = false;
  Object.values(views).forEach((view) => {
    view.hidden = true;
  });
  loadCaptcha().catch(() => {
    captchaQuestion.textContent = "Captcha yuklanmadi";
  });
}

function showApp(data) {
  state.user = data.user;
  state.roles = data.roles || {};
  state.permissions = data.permissions || {};
  loginView.hidden = true;
  appView.hidden = false;
  document.querySelector("#sessionLine").textContent = sessionText();
  renderRoleOptions();
  applyRoleUi();
  resetMedicineForm();
  resetUsageForm();
  resetBuildingForm();
  resetDepartmentForm();
  resetUserForm();
  showView("dashboard");
}

function sessionText() {
  if (!state.user) return "";
  const scope = state.user.building || state.user.department || "Barcha bo'limlar";
  return [state.user.full_name, state.user.role_label, scope].filter(Boolean).join(" | ");
}

function applyRoleUi() {
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    const target = button.dataset.viewTarget;
    button.hidden =
      (target === "medicine" && !canWrite()) ||
      (target === "usage" && !canWrite()) ||
      (target === "management" && !canManage());
    button.classList.toggle("active", target === state.currentView);
  });
  exportBtn.hidden = state.currentView === "management";
  const hasDepartmentFilter = (state.options.departments || []).length > 1;
  departmentFilterField.hidden = !hasDepartmentFilter;
  filterForm.elements.namedItem("department").disabled = !hasDepartmentFilter;
  managementButtons.forEach((button) => {
    const target = button.dataset.managementTarget;
    button.hidden = (target === "buildings" || target === "departments") && !canManageDepartments();
    button.classList.toggle("active", target === state.managementSection);
  });
  buildingForm.querySelectorAll("input, textarea, button").forEach((input) => {
    input.disabled = !canManageDepartments();
  });
  departmentForm.querySelectorAll("input, textarea, select, button").forEach((input) => {
    input.disabled = !canManageDepartments();
  });
}

function showView(name) {
  if ((name === "medicine" || name === "usage") && !canWrite()) {
    showToast("Bu oyna faqat ma'lumot kiritish huquqi bor foydalanuvchilar uchun", true);
    name = "dashboard";
  }
  if (name === "management" && !canManage()) {
    showToast("Boshqaruv faqat super admin uchun", true);
    name = "dashboard";
  }
  Object.entries(views).forEach(([key, view]) => {
    view.hidden = key !== name;
  });
  state.currentView = name;
  applyRoleUi();
  if (name === "medicine") {
    renderMedicines();
  }
  if (name === "usage") {
    renderMedicineChoices();
    updateUsageStockHint();
  }
  if (name === "management") {
    const defaultSection = canManageDepartments() ? state.managementSection : "users";
    showManagementSection(defaultSection);
  }
}

function showManagementSection(name) {
  if ((name === "buildings" || name === "departments") && !canManageDepartments()) {
    name = "users";
  }
  state.managementSection = name;
  managementPanels.forEach((panel) => {
    panel.hidden = panel.dataset.managementPanel !== name;
  });
  managementButtons.forEach((button) => {
    const isActive = button.dataset.managementTarget === name;
    button.classList.toggle("active", isActive);
  });
}

function renderSelectOptions(select, values, { placeholder = "", includeEmpty = false } = {}) {
  const options = [];
  if (placeholder || includeEmpty) {
    options.push(`<option value="">${escapeHtml(placeholder)}</option>`);
  }
  values.forEach((value) => {
    if (value) options.push(`<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
  });
  select.innerHTML = options.join("");
}

function renderOptions(options) {
  state.options = options || {};
  const departments = state.options.departments || [];
  const buildings = state.options.buildings || [];
  const forms = state.options.forms || [];
  const routes = state.options.routes || [];
  const medicineNames = state.options.medicine_names || [];

  renderSelectOptions(medicineForm.elements.namedItem("department"), departments, { placeholder: "Bo'limni tanlang" });
  renderSelectOptions(filterForm.elements.namedItem("department"), departments, {
    placeholder: "Barcha bo'limlar",
    includeEmpty: true,
  });
  renderSelectOptions(userForm.elements.namedItem("department"), departments, { placeholder: "Bo'limni tanlang" });
  renderSelectOptions(userForm.elements.namedItem("building"), buildings, { placeholder: "Korpusni tanlang" });
  renderSelectOptions(departmentForm.elements.namedItem("building"), buildings, { placeholder: "Korpusni tanlang" });
  renderSelectOptions(medicineForm.elements.namedItem("form"), forms, { placeholder: "Shaklni tanlang" });
  if (departments.length === 1) {
    medicineForm.elements.namedItem("department").value = departments[0];
  }

  document.querySelector("#medicineNameList").innerHTML = medicineNames
    .map((value) => `<option value="${escapeHtml(value)}"></option>`)
    .join("");
  const routeValues = [...new Set([...routes, "og'iz orqali", "vena ichiga", "mushak ichiga", "teri ostiga", "tomchi"])];
  document.querySelector("#routeList").innerHTML = routeValues
    .filter(Boolean)
    .map((value) => `<option value="${escapeHtml(value)}"></option>`)
    .join("");
  updateUserRoleRequirement();
}

function renderRoleOptions() {
  userForm.elements.namedItem("role").innerHTML = Object.entries(state.roles)
    .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
    .join("");
  updateUserRoleRequirement();
}

function updateUserRoleRequirement() {
  const role = userForm.elements.namedItem("role").value;
  const departmentLabel = document.querySelector("#userDepartmentLabel");
  const buildingLabel = document.querySelector("#userBuildingLabel");
  const departmentSelect = userForm.elements.namedItem("department");
  const buildingSelect = userForm.elements.namedItem("building");
  const needsDepartment = role === "nurse";
  const needsBuilding = role === "local_admin" || role === "observer";

  departmentLabel.hidden = !needsDepartment;
  buildingLabel.hidden = !needsBuilding;
  departmentSelect.required = needsDepartment;
  departmentSelect.disabled = !needsDepartment;
  buildingSelect.required = needsBuilding;
  buildingSelect.disabled = !needsBuilding;
  if (!needsDepartment) departmentSelect.value = "";
  if (!needsBuilding) buildingSelect.value = "";
}

function resetUserForm() {
  userForm.reset();
  document.querySelector("#userId").value = "";
  renderRoleOptions();
  userPasswordInput.required = true;
  userPasswordInput.placeholder = "";
  saveUserBtn.textContent = "Akkaunt yaratish";
  cancelUserEditBtn.hidden = true;
}

function startEditUser(user) {
  document.querySelector("#userId").value = user.id;
  userForm.elements.namedItem("username").value = user.username || "";
  userForm.elements.namedItem("full_name").value = user.full_name || "";
  userForm.elements.namedItem("role").value = user.role || "";
  updateUserRoleRequirement();
  userForm.elements.namedItem("department").value = user.department || "";
  userForm.elements.namedItem("building").value = user.building || "";
  userForm.elements.namedItem("is_active").value = user.is_active ? "1" : "0";
  userPasswordInput.value = "";
  userPasswordInput.required = false;
  userPasswordInput.placeholder = "Bo'sh qoldirilsa o'zgarmaydi";
  saveUserBtn.textContent = "Yangilash";
  cancelUserEditBtn.hidden = false;
  showManagementSection("users");
  userForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildFilterParams() {
  const params = new URLSearchParams();
  const values = formToObject(filterForm);
  Object.entries(values).forEach(([key, value]) => {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  });
  state.filters = params;
  return params;
}

function currentQueryString() {
  const text = state.filters.toString();
  return text ? `?${text}` : "";
}

function resetMedicineForm() {
  medicineForm.reset();
  document.querySelector("#medicineId").value = "";
  setMedicineCurrentDateTime();
  if (!isSuperAdmin() && state.options.departments?.length === 1) {
    medicineForm.elements.namedItem("department").value = state.options.departments[0];
  }
  saveMedicineBtn.textContent = "Dorini ro'yxatga olish";
  cancelMedicineEditBtn.hidden = true;
}

function startEditMedicine(medicine) {
  document.querySelector("#medicineId").value = medicine.id;
  medicineForm.elements.namedItem("department").value = medicine.department || "";
  medicineForm.elements.namedItem("name").value = medicine.name || "";
  medicineForm.elements.namedItem("received_date").value = medicine.received_date || "";
  medicineForm.elements.namedItem("received_time").value = medicine.received_time || "";
  medicineForm.elements.namedItem("form").value = medicine.form || "";
  medicineForm.elements.namedItem("initial_quantity").value = medicine.initial_quantity ?? "";
  medicineForm.elements.namedItem("remaining_quantity").value = medicine.remaining_quantity ?? "";
  medicineForm.elements.namedItem("note").value = medicine.note || "";
  saveMedicineBtn.textContent = "Yangilash";
  cancelMedicineEditBtn.hidden = false;
  showView("medicine");
  medicineForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetUsageForm() {
  usageForm.reset();
  setUsageCurrentDateTime();
  usageForm.elements.namedItem("nurse_name").value = state.user?.full_name || "";
  usageMedicineSearch.value = "";
  renderMedicineChoices();
  updateUsageStockHint();
}

function resetBuildingForm() {
  buildingForm.reset();
  document.querySelector("#buildingId").value = "";
  saveBuildingBtn.textContent = "Korpus qo'shish";
  cancelBuildingEditBtn.hidden = true;
}

function startEditBuilding(building) {
  document.querySelector("#buildingId").value = building.id;
  buildingForm.elements.namedItem("name").value = building.name || "";
  buildingForm.elements.namedItem("note").value = building.note || "";
  saveBuildingBtn.textContent = "Yangilash";
  cancelBuildingEditBtn.hidden = false;
  showManagementSection("buildings");
  buildingForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetDepartmentForm() {
  departmentForm.reset();
  document.querySelector("#departmentId").value = "";
  saveDepartmentBtn.textContent = "Bo'lim qo'shish";
  cancelDepartmentEditBtn.hidden = true;
}

function startEditDepartment(department) {
  document.querySelector("#departmentId").value = department.id;
  departmentForm.elements.namedItem("name").value = department.name || "";
  departmentForm.elements.namedItem("building").value = department.building || "";
  departmentForm.elements.namedItem("note").value = department.note || "";
  saveDepartmentBtn.textContent = "Yangilash";
  cancelDepartmentEditBtn.hidden = false;
  showManagementSection("departments");
  departmentForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderStats(stats) {
  const totals = stats.totals || {};
  document.querySelector("#entryCount").textContent = formatNumber(totals.entry_count);
  document.querySelector("#patientCount").textContent = formatNumber(totals.patient_count);
  document.querySelector("#usedMedicineCount").textContent = formatNumber(totals.used_medicine_count);
  document.querySelector("#usedTotal").textContent = formatNumber(totals.total_used);
  document.querySelector("#stockBatchCount").textContent = formatNumber(totals.stock_batches);
  document.querySelector("#remainingTotal").textContent = formatNumber(totals.total_remaining);
  document.querySelector("#lowStockCount").textContent = formatNumber(totals.low_batches);
  document.querySelector("#emptyStockCount").textContent = formatNumber(totals.empty_batches);

  renderSummaryList(
    document.querySelector("#medicineSummary"),
    stats.by_medicine || [],
    (row) => `${escapeHtml(row.medicine_name)}: ${formatNumber(row.total_quantity)} ${escapeHtml(row.unit)}`
  );
  renderSummaryList(
    document.querySelector("#departmentSummary"),
    stats.by_department || [],
    (row) => {
      const building = row.building ? ` (${escapeHtml(row.building)})` : "";
      return `${escapeHtml(row.department)}${building}: ${formatNumber(row.uses)} ta yozuv`;
    }
  );
  renderSummaryList(
    document.querySelector("#stockDepartmentSummary"),
    stats.stock_by_department || [],
    (row) => `${escapeHtml(row.department)}: ${formatNumber(row.remaining_quantity)} qoldiq`
  );
  renderSummaryList(
    document.querySelector("#lowStockSummary"),
    stats.low_stock || [],
    (row) => `${escapeHtml(row.name)}: ${formatNumber(row.remaining_quantity)} / ${formatNumber(row.initial_quantity)} ${escapeHtml(row.form)}`
  );
}

function renderSummaryList(target, rows, labeler) {
  target.innerHTML = "";
  if (!rows.length) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "Ma'lumot yo'q";
    target.appendChild(li);
    return;
  }
  rows.forEach((row) => {
    const li = document.createElement("li");
    li.innerHTML = labeler(row);
    target.appendChild(li);
  });
}

function renderMedicines() {
  const term = medicineSearch.value.trim().toLowerCase();
  const rows = state.medicines.filter((medicine) => {
    if (!term) return true;
    return [medicine.name, medicine.department, medicine.form, medicine.note]
      .join(" ")
      .toLowerCase()
      .includes(term);
  });
  document.querySelector("#medicineResultCount").textContent = `${rows.length} ta dori partiyasi`;
  medicineEmptyState.hidden = rows.length !== 0;
  medicinesBody.innerHTML = "";

  const fragment = document.createDocumentFragment();
  rows.forEach((medicine) => {
    const remaining = Number(medicine.remaining_quantity || 0);
    const initial = Number(medicine.initial_quantity || 0);
    const ratio = initial > 0 ? remaining / initial : 0;
    const stockClass = remaining <= 0 ? "empty" : ratio <= 0.1 ? "low" : "ok";
    const actionCell = medicine.can_edit
      ? `<button class="secondary" type="button" data-action="edit-medicine" data-id="${medicine.id}">Tahrir</button>`
      : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(medicine.name)}</strong>
        <div class="muted">${escapeHtml(medicine.form)}</div>
      </td>
      <td>${escapeHtml(medicine.department)}</td>
      <td>
        <strong>${escapeHtml(medicine.received_date)}</strong>
        <div class="muted">${escapeHtml(medicine.received_time)}</div>
      </td>
      <td>${formatNumber(medicine.initial_quantity)} ${escapeHtml(medicine.form)}</td>
      <td><span class="stock-badge ${stockClass}">${formatNumber(medicine.remaining_quantity)} ${escapeHtml(medicine.form)}</span></td>
      <td>${escapeHtml(medicine.note || "")}</td>
      <td><div class="table-actions">${actionCell}</div></td>
    `;
    fragment.appendChild(tr);
  });
  medicinesBody.appendChild(fragment);
}

function renderMedicineChoices() {
  const selected = usageMedicineSelect.value;
  const term = usageMedicineSearch.value.trim().toLowerCase();
  let rows = state.medicines.filter((medicine) => Number(medicine.remaining_quantity || 0) > 0);
  if (term) {
    rows = rows.filter((medicine) =>
      [medicine.name, medicine.department, medicine.form, medicine.received_date]
        .join(" ")
        .toLowerCase()
        .includes(term)
    );
  }
  rows = rows.slice(0, 120);

  const options = ['<option value="">Dorini tanlang</option>'];
  rows.forEach((medicine) => {
    const label = `${medicine.name} | ${formatNumber(medicine.remaining_quantity)} ${medicine.form} | ${medicine.department} | ${medicine.received_date}`;
    options.push(`<option value="${medicine.id}">${escapeHtml(label)}</option>`);
  });
  usageMedicineSelect.innerHTML = options.join("");
  if (selected && rows.some((medicine) => String(medicine.id) === String(selected))) {
    usageMedicineSelect.value = selected;
  }
  updateUsageStockHint();
}

function updateUsageStockHint() {
  const selected = usageMedicineSelect.value;
  const medicine = state.medicines.find((item) => String(item.id) === String(selected));
  const quantityInput = usageForm.elements.namedItem("quantity");
  if (!medicine) {
    usageStockHint.textContent = "Dori tanlanganda qoldiq ko'rinadi.";
    quantityInput.removeAttribute("max");
    return;
  }
  quantityInput.max = medicine.remaining_quantity;
  usageStockHint.textContent = `${medicine.department}: ${medicine.name} qoldig'i ${formatNumber(medicine.remaining_quantity)} ${medicine.form}. Qabul qilingan sana: ${medicine.received_date} ${medicine.received_time}.`;
}

function renderEntries() {
  document.querySelector("#entryResultCount").textContent = `${state.entries.length} ta yozuv`;
  entryEmptyState.hidden = state.entries.length !== 0;
  entriesBody.innerHTML = "";

  const fragment = document.createDocumentFragment();
  state.entries.forEach((entry) => {
    const tr = document.createElement("tr");
    const actionCell = entry.can_edit
      ? `<button class="secondary danger" type="button" data-action="delete-entry" data-id="${entry.id}">O'chirish</button>`
      : "";
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(entry.entry_date)}</strong>
        <div class="muted">${escapeHtml(entry.entry_time)}</div>
      </td>
      <td>
        <strong>${escapeHtml(entry.patient_name)}</strong>
        <div class="muted">${escapeHtml(entry.patient_id || "")}</div>
      </td>
      <td>
        <strong>${escapeHtml(entry.medicine_name)}</strong>
        <div class="muted">${escapeHtml(entry.dose || "")} ${escapeHtml(entry.route || "")}</div>
      </td>
      <td>${formatNumber(entry.quantity)} ${escapeHtml(entry.unit)}</td>
      <td>${escapeHtml(entry.nurse_name)}</td>
      <td>${escapeHtml(entry.department)}</td>
      <td><div class="table-actions">${actionCell}</div></td>
    `;
    fragment.appendChild(tr);
  });
  entriesBody.appendChild(fragment);
}

function renderBuildings(buildings) {
  buildingsBody.innerHTML = "";
  const fragment = document.createDocumentFragment();
  buildings.forEach((building) => {
    const actionCell = building.can_edit
      ? `<button class="secondary" type="button" data-action="edit-building" data-id="${building.id}">Tahrir</button>`
      : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(building.name)}</strong></td>
      <td>${escapeHtml(building.note || "")}</td>
      <td><div class="table-actions">${actionCell}</div></td>
    `;
    fragment.appendChild(tr);
  });
  buildingsBody.appendChild(fragment);
}

function renderDepartments(departments) {
  departmentsBody.innerHTML = "";
  const fragment = document.createDocumentFragment();
  departments.forEach((department) => {
    const actionCell = department.can_edit
      ? `<button class="secondary" type="button" data-action="edit-department" data-id="${department.id}">Tahrir</button>`
      : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(department.name)}</strong></td>
      <td>${escapeHtml(department.building || "")}</td>
      <td>${escapeHtml(department.note || "")}</td>
      <td><div class="table-actions">${actionCell}</div></td>
    `;
    fragment.appendChild(tr);
  });
  departmentsBody.appendChild(fragment);
}

function renderUsers(users) {
  usersBody.innerHTML = "";
  document.querySelector("#userCount").textContent = `${users.length} ta akkaunt`;
  const fragment = document.createDocumentFragment();
  users.forEach((user) => {
    const scope = user.department || user.building || "Barcha bo'limlar";
    const actionCell = user.can_edit
      ? `<button class="secondary" type="button" data-action="edit-user" data-id="${user.id}">Tahrir</button>`
      : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(user.username)}</strong></td>
      <td>${escapeHtml(user.full_name)}</td>
      <td>${escapeHtml(user.role_label)}</td>
      <td>${escapeHtml(scope)}</td>
      <td>${user.is_active ? "Faol" : "Nofaol"}</td>
      <td><div class="table-actions">${actionCell}</div></td>
    `;
    fragment.appendChild(tr);
  });
  usersBody.appendChild(fragment);
}

function renderAdminActivity(activity) {
  const totals = activity.totals || {};
  document.querySelector("#adminUserTotal").textContent = formatNumber(totals.users);
  document.querySelector("#adminActiveUserTotal").textContent = formatNumber(totals.active_users);
  document.querySelector("#adminEntryTotal").textContent = formatNumber(totals.entries);
  document.querySelector("#adminLogTotal").textContent = formatNumber(totals.logs);

  userStatsBody.innerHTML = "";
  const statsFragment = document.createDocumentFragment();
  (activity.user_stats || []).forEach((user) => {
    const scope = user.department || user.building || "Barcha bo'limlar";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(user.full_name)}</strong>
        <div class="muted">${escapeHtml(user.username)}</div>
      </td>
      <td>${escapeHtml(user.role_label)}</td>
      <td>${escapeHtml(scope)}</td>
      <td>${formatNumber(user.entry_count)} ta<div class="muted">${formatNumber(user.total_quantity)} miqdor</div></td>
      <td>${formatNumber(user.medicine_count)} ta</td>
      <td>${formatNumber(user.log_count)} ta</td>
      <td>${escapeHtml(user.last_activity || "")}</td>
    `;
    statsFragment.appendChild(tr);
  });
  userStatsBody.appendChild(statsFragment);

  auditLogsBody.innerHTML = "";
  const logsFragment = document.createDocumentFragment();
  (activity.logs || []).forEach((log) => {
    const actor = log.full_name || log.username || "Tizim";
    const objectText = [log.entity_type, log.entity_id].filter(Boolean).join(" #");
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(log.created_at)}</td>
      <td>
        <strong>${escapeHtml(actor)}</strong>
        <div class="muted">${escapeHtml(log.role_label || "")}</div>
      </td>
      <td>${escapeHtml(log.action)}</td>
      <td>${escapeHtml(objectText)}</td>
      <td>${escapeHtml(log.description || "")}</td>
    `;
    logsFragment.appendChild(tr);
  });
  auditLogsBody.appendChild(logsFragment);
}

async function loadUsers() {
  if (!canManage()) {
    state.users = [];
    renderUsers([]);
    state.adminActivity = { user_stats: [], logs: [], totals: {} };
    renderAdminActivity(state.adminActivity);
    return;
  }
  const data = await fetchJson("/api/users");
  state.users = data.users || [];
  if (data.roles) {
    state.roles = data.roles;
    renderRoleOptions();
  }
  renderUsers(state.users);
}

async function loadAdminActivity() {
  if (!canManage()) {
    state.adminActivity = { user_stats: [], logs: [], totals: {} };
    renderAdminActivity(state.adminActivity);
    return;
  }
  const data = await fetchJson("/api/admin/activity");
  state.adminActivity = data;
  renderAdminActivity(state.adminActivity);
}

async function loadData() {
  if (!state.user) return;
  const query = currentQueryString();
  const requests = [
    fetchJson(`/api/entries${query}`),
    fetchJson(`/api/stats${query}`),
    fetchJson("/api/options"),
    fetchJson("/api/buildings"),
    fetchJson("/api/departments"),
    fetchJson("/api/medicines"),
  ];
  const [entryData, statsData, optionData, buildingData, departmentData, medicineData] = await Promise.all(requests);
  state.entries = entryData.entries || [];
  state.buildings = buildingData.buildings || [];
  state.departments = departmentData.departments || [];
  state.medicines = medicineData.medicines || [];

  renderStats(statsData);
  renderOptions(optionData);
  renderBuildings(state.buildings);
  renderDepartments(state.departments);
  renderMedicines();
  renderMedicineChoices();
  renderEntries();
  await loadUsers();
  await loadAdminActivity();
  applyRoleUi();
}

async function saveMedicine(event) {
  event.preventDefault();
  const payload = formToObject(medicineForm);
  const medicineId = payload.id;
  delete payload.id;
  try {
    if (medicineId) {
      await fetchJson(`/api/medicines/${medicineId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("Dori yangilandi");
    } else {
      await fetchJson("/api/medicines", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Dori ro'yxatga olindi");
    }
    resetMedicineForm();
    await loadData();
    showView("medicine");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function createUsage(event) {
  event.preventDefault();
  try {
    await fetchJson("/api/entries", {
      method: "POST",
      body: JSON.stringify(formToObject(usageForm)),
    });
    showToast("Sarf yozuvi saqlandi");
    resetUsageForm();
    await loadData();
    showView("usage");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteEntry(entryId) {
  const entry = state.entries.find((item) => String(item.id) === String(entryId));
  if (!entry || !window.confirm(`"${entry.patient_name}" uchun sarf yozuvi o'chirilsinmi?`)) return;
  try {
    await fetchJson(`/api/entries/${entry.id}`, { method: "DELETE" });
    showToast("Sarf yozuvi o'chirildi, qoldiq qaytarildi");
    await loadData();
    showView("usage");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function saveBuilding(event) {
  event.preventDefault();
  const payload = formToObject(buildingForm);
  const buildingId = payload.id;
  delete payload.id;
  try {
    if (buildingId) {
      await fetchJson(`/api/buildings/${buildingId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("Korpus yangilandi");
    } else {
      await fetchJson("/api/buildings", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Korpus qo'shildi");
    }
    resetBuildingForm();
    await loadData();
    showView("management");
    showManagementSection("buildings");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function saveDepartment(event) {
  event.preventDefault();
  const payload = formToObject(departmentForm);
  const departmentId = payload.id;
  delete payload.id;
  try {
    if (departmentId) {
      await fetchJson(`/api/departments/${departmentId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("Bo'lim yangilandi");
    } else {
      await fetchJson("/api/departments", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Bo'lim qo'shildi");
    }
    resetDepartmentForm();
    await loadData();
    showView("management");
    showManagementSection("departments");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function saveUser(event) {
  event.preventDefault();
  const payload = formToObject(userForm);
  const userId = payload.id;
  delete payload.id;
  if (!payload.password) {
    delete payload.password;
  }
  try {
    if (userId) {
      await fetchJson(`/api/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("Akkaunt yangilandi");
    } else {
      await fetchJson("/api/users", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Akkaunt yaratildi");
    }
    resetUserForm();
    await loadData();
    showView("management");
    showManagementSection("users");
  } catch (error) {
    showToast(error.message, true);
  }
}

function exportExcel() {
  window.location.href = `/export.xlsx${currentQueryString()}`;
}

async function login(event) {
  event.preventDefault();
  try {
    const data = await fetchJson("/api/login", {
      method: "POST",
      body: JSON.stringify(formToObject(loginForm)),
    });
    loginForm.reset();
    showApp(data);
    await loadData();
    showView("dashboard");
  } catch (error) {
    showToast(error.message, true);
    await loadCaptcha().catch(() => null);
  }
}

async function logout() {
  await fetchJson("/api/logout", { method: "POST" }).catch(() => null);
  state.entries = [];
  state.medicines = [];
  state.users = [];
  state.adminActivity = { user_stats: [], logs: [], totals: {} };
  state.buildings = [];
  state.departments = [];
  state.filters = new URLSearchParams();
  filterForm.reset();
  showLogin();
}

async function boot() {
  await fetchJson("/api/logout", { method: "POST" }).catch(() => null);
  showLogin();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loginForm.addEventListener("submit", login);
medicineForm.addEventListener("submit", saveMedicine);
usageForm.addEventListener("submit", createUsage);
buildingForm.addEventListener("submit", saveBuilding);
departmentForm.addEventListener("submit", saveDepartment);
userForm.addEventListener("submit", saveUser);
userForm.elements.namedItem("role").addEventListener("change", updateUserRoleRequirement);

document.querySelector("#refreshCaptchaBtn").addEventListener("click", () => loadCaptcha());
document.querySelector("#logoutBtn").addEventListener("click", logout);
document.querySelector("#clearMedicineBtn").addEventListener("click", resetMedicineForm);
cancelMedicineEditBtn.addEventListener("click", resetMedicineForm);
document.querySelector("#clearUsageBtn").addEventListener("click", resetUsageForm);
cancelBuildingEditBtn.addEventListener("click", resetBuildingForm);
cancelDepartmentEditBtn.addEventListener("click", resetDepartmentForm);
cancelUserEditBtn.addEventListener("click", resetUserForm);
document.querySelector("#resetFiltersBtn").addEventListener("click", async () => {
  filterForm.reset();
  state.filters = new URLSearchParams();
  await loadData();
  showToast("Filtrlar tozalandi");
});
refreshBtn.addEventListener("click", async () => {
  await loadData();
  showToast("Ma'lumotlar yangilandi");
});
exportBtn.addEventListener("click", exportExcel);
filterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  buildFilterParams();
  await loadData();
  showToast("Bosh sahifa yangilandi");
});

document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.viewTarget));
});
managementButtons.forEach((button) => {
  button.addEventListener("click", () => showManagementSection(button.dataset.managementTarget));
});
medicineSearch.addEventListener("input", renderMedicines);
usageMedicineSearch.addEventListener("input", renderMedicineChoices);
usageMedicineSelect.addEventListener("change", updateUsageStockHint);
medicineForm.elements.namedItem("initial_quantity").addEventListener("input", () => {
  const initial = medicineForm.elements.namedItem("initial_quantity").value;
  const remaining = medicineForm.elements.namedItem("remaining_quantity");
  if (!remaining.value || Number(remaining.value) > Number(initial)) {
    remaining.value = initial;
  }
});
entriesBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='delete-entry']");
  if (button) deleteEntry(button.dataset.id);
});
medicinesBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='edit-medicine']");
  if (!button) return;
  const medicine = state.medicines.find((item) => String(item.id) === String(button.dataset.id));
  if (medicine) startEditMedicine(medicine);
});
buildingsBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='edit-building']");
  if (!button) return;
  const building = state.buildings.find((item) => String(item.id) === String(button.dataset.id));
  if (building) startEditBuilding(building);
});
departmentsBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='edit-department']");
  if (!button) return;
  const department = state.departments.find((item) => String(item.id) === String(button.dataset.id));
  if (department) startEditDepartment(department);
});
usersBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='edit-user']");
  if (!button) return;
  const user = state.users.find((item) => String(item.id) === String(button.dataset.id));
  if (user) startEditUser(user);
});

boot().catch((error) => {
  showLogin();
  showToast(error.message, true);
});
