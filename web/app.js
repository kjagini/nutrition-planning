const METRICS = [
  { key: "calories", label: "Calories", unit: "kcal", digits: 0 },
  { key: "protein_g", label: "Protein", unit: "g", digits: 1 },
  { key: "carbs_g", label: "Carbs", unit: "g", digits: 1 },
  { key: "fats_g", label: "Fats", unit: "g", digits: 1 },
];

const state = {
  profile: null,
  targets: null,
  dayPlan: {},
  dayTotals: null,
  withinLimits: null,
  report: null,
  logSelection: {},
  llm: null,
  llmEnabled: false,
};

const dom = {
  profileForm: document.getElementById("profile-form"),
  height: document.getElementById("height-cm"),
  weight: document.getElementById("weight-kg"),
  workout: document.getElementById("workout-level"),
  ingredientsBreakfast: document.getElementById("ingredients-breakfast"),
  ingredientsLunch: document.getElementById("ingredients-lunch"),
  ingredientsDinner: document.getElementById("ingredients-dinner"),
  extraPreferences: document.getElementById("extra-preferences"),
  planStatus: document.getElementById("plan-status"),
  llmHint: document.getElementById("llm-hint"),
  targetsGrid: document.getElementById("targets-grid"),
  progressGrid: document.getElementById("progress-grid"),
  mealPlanGrid: document.getElementById("meal-plan-grid"),
  limitsBadge: document.getElementById("within-limits-badge"),
  dateInput: document.getElementById("log-date"),
  logSelector: document.getElementById("log-meal-selector"),
  logButton: document.getElementById("log-selected-btn"),
  reportButton: document.getElementById("generate-report-btn"),
  logStatus: document.getElementById("log-status"),
  reportCard: document.getElementById("report-card"),
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function toFixed(value, digits = 1) {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "0";
}

function titleCase(value) {
  return value
    .split("_")
    .join(" ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function setStatus(element, message, mode = "info") {
  element.textContent = message;
  element.className = `status ${mode}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function getProfileFormValues() {
  return {
    height_cm: Number(dom.height.value),
    weight_kg: Number(dom.weight.value),
    workout_level: dom.workout.value,
  };
}

function parseIngredientText(value) {
  const tokens = String(value || "")
    .split(/[\n,;]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const seen = new Set();
  const output = [];
  for (const token of tokens) {
    const key = token.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(token);
  }
  return output;
}

function getIngredientsByMeal() {
  return {
    breakfast: parseIngredientText(dom.ingredientsBreakfast.value),
    lunch: parseIngredientText(dom.ingredientsLunch.value),
    dinner: parseIngredientText(dom.ingredientsDinner.value),
  };
}

function buildWorkoutOptions(levels) {
  dom.workout.innerHTML = levels
    .map((level) => `<option value="${level}">${titleCase(level)}</option>`)
    .join("");
  if (levels.includes("moderate")) {
    dom.workout.value = "moderate";
  }
}

function renderTargets() {
  if (!state.targets) {
    dom.targetsGrid.innerHTML = `<p class="muted-empty">Generate a plan to view your target calories and macros.</p>`;
    return;
  }

  dom.targetsGrid.innerHTML = METRICS.map((metric) => {
    const value = toFixed(state.targets[metric.key], metric.digits);
    return `
      <article class="metric-card">
        <p class="label">${metric.label} target</p>
        <p class="value">${value} ${metric.unit}</p>
      </article>
    `;
  }).join("");
}

function renderProgress() {
  if (!state.targets || !state.dayTotals) {
    dom.progressGrid.innerHTML = "";
    return;
  }

  dom.progressGrid.innerHTML = METRICS.map((metric) => {
    const actual = Number(state.dayTotals[metric.key] || 0);
    const target = Number(state.targets[metric.key] || 0);
    const ratio = target > 0 ? actual / target : 0;
    const percent = Math.min(130, Math.max(0, ratio * 100));
    return `
      <article class="progress-item">
        <div class="progress-head">
          <span>${metric.label}</span>
          <span>${toFixed(actual, metric.digits)} / ${toFixed(target, metric.digits)} ${metric.unit}</span>
        </div>
        <div class="track">
          <div class="fill" style="width: ${percent}%"></div>
        </div>
      </article>
    `;
  }).join("");
}

function updateLimitsBadge() {
  if (!state.withinLimits) {
    dom.limitsBadge.className = "badge neutral";
    dom.limitsBadge.textContent = "No plan yet";
    return;
  }

  const allWithin = Object.values(state.withinLimits).every(Boolean);
  dom.limitsBadge.className = allWithin ? "badge good" : "badge bad";
  dom.limitsBadge.textContent = allWithin ? "Within daily limits" : "Needs adjustment";
}

function renderMealPlan() {
  const mealNames = Object.keys(state.dayPlan);
  if (!mealNames.length) {
    dom.mealPlanGrid.innerHTML = "";
    return;
  }

  dom.mealPlanGrid.innerHTML = mealNames
    .map((mealName) => {
      const meal = state.dayPlan[mealName];
      return `
        <article class="meal-card">
          <header class="meal-card-head">
            <h3>${titleCase(mealName)}</h3>
            <span class="meal-calories">${toFixed(meal.calories, 0)} kcal</span>
          </header>
          <table class="meal-table">
            <thead>
              <tr>
                <th>Ingredient</th>
                <th>Grams</th>
                <th>Kcal</th>
              </tr>
            </thead>
            <tbody>
              ${meal.ingredients
                .map(
                  (ingredient) => `
                  <tr>
                    <td>${ingredient.name}</td>
                    <td>
                      <input
                        class="grams-input"
                        type="number"
                        min="0"
                        step="1"
                        value="${toFixed(ingredient.grams, 1)}"
                        data-meal="${mealName}"
                        data-name="${ingredient.name}"
                      >
                    </td>
                    <td>${toFixed(ingredient.calories, 0)}</td>
                  </tr>
                `
                )
                .join("")}
            </tbody>
          </table>
        </article>
      `;
    })
    .join("");
}

function renderLogSelector() {
  const mealNames = Object.keys(state.dayPlan);
  if (!mealNames.length) {
    dom.logSelector.innerHTML = "";
    return;
  }

  mealNames.forEach((mealName) => {
    if (!(mealName in state.logSelection)) {
      state.logSelection[mealName] = true;
    }
  });

  dom.logSelector.innerHTML = mealNames
    .map(
      (mealName) => `
      <label class="toggle-chip">
        <input type="checkbox" data-log-meal="${mealName}" ${state.logSelection[mealName] ? "checked" : ""}>
        <span>${titleCase(mealName)}</span>
      </label>
    `
    )
    .join("");
}

function renderReport() {
  if (!state.report) {
    dom.reportCard.innerHTML = `<p class="muted-empty">Log meals and generate a report to see goals met/unmet and improvements.</p>`;
    return;
  }

  const score = toFixed(state.report.completion_score, 0);
  const metricsMarkup = METRICS.map((metric) => {
    const target = Number(state.report.targets[metric.key] || 0);
    const actual = Number(state.report.actual[metric.key] || 0);
    const met = Boolean(state.report.met[metric.key]);
    return `
      <article class="report-item">
        <p class="name">${metric.label}</p>
        <p class="pair">${toFixed(actual, metric.digits)} / ${toFixed(target, metric.digits)} ${metric.unit}</p>
        <span class="pill ${met ? "good" : "bad"}">${met ? "Met" : "Unmet"}</span>
      </article>
    `;
  }).join("");

  const tips = (state.report.improvements || [])
    .map((tip) => `<li>${tip}</li>`)
    .join("");

  dom.reportCard.innerHTML = `
    <div class="report-head">
      <h3>Daily report for ${state.report.date}</h3>
      <span class="score">${score}% goals met</span>
    </div>
    <p class="hint">${state.report.meal_count} logged meal(s)</p>
    <div class="report-grid">${metricsMarkup}</div>
    <ul class="improvements">${tips}</ul>
  `;
}

function renderAll() {
  renderTargets();
  renderProgress();
  renderMealPlan();
  renderLogSelector();
  renderReport();
  updateLimitsBadge();
}

function getSelectedMealsForLog() {
  return Object.entries(state.dayPlan)
    .filter(([mealName]) => state.logSelection[mealName])
    .map(([, meal]) => meal);
}

function validateIngredientInput(ingredientsByMeal) {
  for (const [mealName, items] of Object.entries(ingredientsByMeal)) {
    if (!items.length) {
      throw new Error(`Please enter at least one ingredient for ${mealName}.`);
    }
  }
}

async function generatePlanWithLlm() {
  const profile = getProfileFormValues();
  if (profile.height_cm <= 0 || profile.weight_kg <= 0) {
    setStatus(dom.planStatus, "Height and weight must be positive values.", "error");
    return;
  }

  const ingredientsByMeal = getIngredientsByMeal();
  validateIngredientInput(ingredientsByMeal);

  setStatus(dom.planStatus, "Running backend LLM to create your meal quantities...", "info");
  const payload = {
    profile,
    ingredients_by_meal: ingredientsByMeal,
    extra_preferences: dom.extraPreferences.value.trim(),
  };
  const result = await api("/api/llm-plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  state.profile = profile;
  state.targets = result.targets;
  state.dayPlan = result.plan;
  state.dayTotals = result.day_totals;
  state.withinLimits = result.within_limits;
  state.report = null;
  state.logSelection = {};
  state.llm = result.llm || null;

  renderAll();
  const modelLabel = state.llm && state.llm.model ? ` (${state.llm.model})` : "";
  setStatus(
    dom.planStatus,
    `LLM plan ready${modelLabel}. Edit grams in any meal and others rebalance automatically.`,
    "success"
  );
}

async function handleRebalance(input) {
  if (!state.targets) {
    return;
  }
  const mealName = input.dataset.meal;
  const ingredientName = input.dataset.name;
  const newGrams = Number(input.value);
  if (!Number.isFinite(newGrams) || newGrams < 0) {
    setStatus(dom.planStatus, "Ingredient grams must be zero or higher.", "error");
    return;
  }

  const result = await api("/api/rebalance", {
    method: "POST",
    body: JSON.stringify({
      meal: state.dayPlan[mealName],
      ingredient_name: ingredientName,
      new_grams: newGrams,
      day_plan: state.dayPlan,
      targets: state.targets,
    }),
  });

  state.dayPlan = result.day_plan || state.dayPlan;
  state.dayPlan[mealName] = result.meal;
  state.dayTotals = result.day_totals || state.dayTotals;
  state.withinLimits = result.within_limits || state.withinLimits;

  renderAll();
  setStatus(dom.planStatus, `${titleCase(mealName)} rebalanced around ${ingredientName}.`, "success");
}

async function logMeals() {
  if (!state.profile || Object.keys(state.dayPlan).length === 0) {
    setStatus(dom.logStatus, "Generate a plan before logging meals.", "error");
    return;
  }

  const meals = getSelectedMealsForLog();
  if (meals.length === 0) {
    setStatus(dom.logStatus, "Select at least one meal to log.", "error");
    return;
  }

  setStatus(dom.logStatus, "Saving meal log...", "info");
  const result = await api("/api/log", {
    method: "POST",
    body: JSON.stringify({
      date: dom.dateInput.value,
      meals,
    }),
  });
  setStatus(
    dom.logStatus,
    `Logged ${result.logged_count} meal(s). Total logs for ${result.date}: ${result.total_logged_meals_for_day}.`,
    "success"
  );
}

async function generateReport() {
  if (!state.profile) {
    setStatus(dom.logStatus, "Generate a plan first so your profile targets are known.", "error");
    return;
  }

  setStatus(dom.logStatus, "Building report...", "info");
  const result = await api("/api/report", {
    method: "POST",
    body: JSON.stringify({
      date: dom.dateInput.value,
      profile: state.profile,
    }),
  });

  state.report = result;
  renderReport();
  setStatus(dom.logStatus, `Report ready for ${result.date}.`, "success");
}

function wireEvents() {
  dom.profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await generatePlanWithLlm();
    } catch (error) {
      setStatus(dom.planStatus, error.message, "error");
    }
  });

  dom.mealPlanGrid.addEventListener("change", async (event) => {
    const input = event.target.closest(".grams-input");
    if (!input) {
      return;
    }
    try {
      await handleRebalance(input);
    } catch (error) {
      setStatus(dom.planStatus, error.message, "error");
    }
  });

  dom.logSelector.addEventListener("change", (event) => {
    const checkbox = event.target.closest("input[data-log-meal]");
    if (!checkbox) {
      return;
    }
    state.logSelection[checkbox.dataset.logMeal] = checkbox.checked;
  });

  dom.logButton.addEventListener("click", async () => {
    try {
      await logMeals();
    } catch (error) {
      setStatus(dom.logStatus, error.message, "error");
    }
  });

  dom.reportButton.addEventListener("click", async () => {
    try {
      await generateReport();
    } catch (error) {
      setStatus(dom.logStatus, error.message, "error");
    }
  });
}

async function initialize() {
  dom.dateInput.value = todayIso();
  wireEvents();
  setStatus(dom.planStatus, "Checking backend capabilities...", "info");
  try {
    const payload = await api("/api/ingredients");
    buildWorkoutOptions(payload.workout_levels || []);
    state.llmEnabled = Boolean(payload.llm_enabled);
    if (!state.llmEnabled) {
      dom.llmHint.textContent =
        "LLM is not configured yet. Set OPENAI_API_KEY in your terminal before running the server.";
    }
    renderAll();
    setStatus(dom.planStatus, "Enter your ingredients and generate your plan with the backend LLM.", "info");
  } catch (error) {
    setStatus(dom.planStatus, error.message, "error");
  }
}

initialize();
