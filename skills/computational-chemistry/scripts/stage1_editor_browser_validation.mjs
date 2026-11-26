#!/usr/bin/env node
/* Real Microsoft Edge validation for the Stage-1 structured plan editor. */

import { spawn } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const pageUrl = process.argv[2] || "http://127.0.0.1:8876/";
const outputDir = path.resolve(process.argv[3] || "stage1-editor-browser-validation");
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const debuggingPort = 9337;
await mkdir(outputDir, { recursive: true });
const profileDir = path.join(outputDir, "edge-profile-cdp");
await rm(profileDir, { recursive: true, force: true });

const edge = spawn(edgePath, [
  "--headless=new", "--disable-gpu", "--no-first-run", `--remote-debugging-port=${debuggingPort}`,
  `--user-data-dir=${profileDir}`, "--window-size=1440,1200", pageUrl,
], { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
let edgeStderr = "";
edge.stderr.on("data", chunk => { edgeStderr += chunk.toString(); });

async function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
async function waitForValue(getter, timeout = 15000, label = "condition") {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    try { last = await getter(); if (last) return last; } catch (error) { last = error.message; }
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${label}; last=${String(last)}`);
}

const target = await waitForValue(async () => {
  const response = await fetch(`http://127.0.0.1:${debuggingPort}/json/list`);
  const targets = await response.json();
  return targets.find(item => item.type === "page" && item.url.startsWith(pageUrl));
}, 15000, "Edge debugging target");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
let sequence = 0;
const pending = new Map();
const browserErrors = [];
socket.addEventListener("message", event => {
  const message = JSON.parse(String(event.data));
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id); pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message)); else resolve(message.result);
  }
  if (message.method === "Runtime.exceptionThrown") browserErrors.push(message.params.exceptionDetails.text || "Runtime exception");
  if (message.method === "Log.entryAdded" && message.params.entry.level === "error") browserErrors.push(message.params.entry.text);
});
function send(method, params = {}) {
  const id = ++sequence;
  const promise = new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  socket.send(JSON.stringify({ id, method, params }));
  return promise;
}
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}
async function waitJs(expression, label, timeout = 12000) { return waitForValue(() => evaluate(expression), timeout, label); }
async function screenshot(name) {
  const result = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const file = path.join(outputDir, name); await writeFile(file, Buffer.from(result.data, "base64")); return file;
}

await send("Runtime.enable"); await send("Log.enable"); await send("Page.enable");
await waitJs("document.readyState === 'complete' && Boolean(window.__stage1EditorTest) && Boolean(window.__stage1EditorTest.getWorkingPlan())", "Stage-1 editor load");

const results = [];
async function test(name, callback) {
  try { const evidence = await callback(); results.push({ name, status: "PASSED", evidence }); }
  catch (error) { results.push({ name, status: "FAILED", error: error.stack || error.message }); }
}
function assert(condition, message) { if (!condition) throw new Error(message); }

await test("default_form_mode_and_readonly_metadata", async () => {
  await evaluate("document.querySelector('button[data-view=edit]').click()");
  await waitJs("document.querySelector('#edit').classList.contains('active')", "editor tab");
  const view = await evaluate(`({
    formVisible: !document.querySelector('#formMode').classList.contains('hidden'),
    jsonHidden: document.querySelector('#jsonMode').classList.contains('hidden'),
    project: document.querySelector('#metaProject').textContent,
    hash: document.querySelector('#metaHash').textContent,
    questionCards: document.querySelectorAll('#questionCards .editor-card').length,
    taskCards: document.querySelectorAll('#taskCards > .editor-card').length
  })`);
  assert(view.formVisible && view.jsonHidden, "The editor did not default to form mode.");
  assert(view.project.startsWith("PROJECT-"), "Protected project ID was not shown read-only.");
  assert(view.hash.startsWith("sha256:"), "Candidate SHA-256 was not visible.");
  assert(view.questionCards === 2 && view.taskCards === 2, "Existing JSON did not load into cards.");
  return { ...view, screenshot: await screenshot("editor-form-default.png") };
});

await test("question_cards_add_sort_copy_dependency_delete_guard", async () => {
  const before = await evaluate("window.__stage1EditorTest.getWorkingPlan().scientific_questions.length");
  await evaluate("document.querySelector('#addQuestion').click()");
  let plan = await evaluate("window.__stage1EditorTest.getWorkingPlan()");
  assert(plan.scientific_questions.length === before + 1, "Question was not added.");
  assert(plan.scientific_questions.at(-1).id === "SQ03", "Question ID was not generated automatically.");
  plan.scientific_questions.at(-1).question = "新增的收敛证据是否与最终任务一致？";
  plan.scientific_questions.at(-1).evidence_target = "一致性审查记录";
  plan.scientific_questions.at(-1).dependencies = ["SQ01"];
  await evaluate(`window.__stage1EditorTest.setWorkingPlan(${JSON.stringify(plan)})`);
  await evaluate("window.confirm=()=>true; document.querySelector('button[data-card-kind=\"question\"][data-card-action=\"delete\"][data-index=\"0\"]').click()");
  const guarded = await evaluate(`({count:window.__stage1EditorTest.getWorkingPlan().scientific_questions.length,toast:document.querySelector('#toast').textContent})`);
  assert(guarded.count === before + 1 && guarded.toast.includes("仍依赖"), "Dependent-question deletion was not blocked.");
  await evaluate("document.querySelector('button[data-card-kind=\"question\"][data-card-action=\"up\"][data-index=\"2\"]').click()");
  const order = await evaluate("window.__stage1EditorTest.getWorkingPlan().scientific_questions.map(item=>item.id)");
  assert(order[1] === "SQ03", "Question move-up did not preserve IDs/order.");
  await evaluate("document.querySelector('button[data-card-kind=\"question\"][data-card-action=\"copy\"][data-index=\"1\"]').click()");
  const copied = await evaluate("window.__stage1EditorTest.getWorkingPlan().scientific_questions.map(item=>item.id)");
  assert(new Set(copied).size === copied.length, "Question copy created a duplicate ID.");
  return { guarded, order, copied };
});

await test("task_cards_add_and_delete", async () => {
  await evaluate("window.__stage1EditorTest.setWorkingPlan(window.__stage1EditorTest.getBaselinePlan())");
  const before = await evaluate("window.__stage1EditorTest.getWorkingPlan().tasks.length");
  await evaluate("document.querySelector('#addTask').click()");
  const added = await evaluate("window.__stage1EditorTest.getWorkingPlan().tasks.map(item=>item.id)");
  assert(added.length === before + 1 && added.at(-1) === "T03", "Task card/ID was not generated.");
  await evaluate("window.confirm=()=>true; document.querySelector('button[data-card-kind=\"task\"][data-card-action=\"delete\"][data-index=\"2\"]').click()");
  const after = await evaluate("window.__stage1EditorTest.getWorkingPlan().tasks.length");
  assert(after === before, "Unreferenced task card could not be deleted.");
  return { added, after };
});

await test("form_json_two_way_sync_unknown_preservation", async () => {
  const base = await evaluate("window.__stage1EditorTest.getBaselinePlan()");
  base.custom_extension = { retained: true, nested: { value: 7 } };
  await evaluate(`window.__stage1EditorTest.setWorkingPlan(${JSON.stringify(base)}); window.__stage1EditorTest.switchToJson()`);
  let jsonPlan = await evaluate("JSON.parse(document.querySelector('#planEditor').value)");
  assert(jsonPlan.custom_extension.nested.value === 7, "Unknown extension was missing in JSON mode.");
  jsonPlan.research_goal.core_question = "在统一结构、方法和收敛标准下，表单与 JSON 双向同步是否保持全部方案字段？";
  jsonPlan.custom_extension.extra = "preserved";
  const applied = await evaluate(`window.__stage1EditorTest.applyJsonText(${JSON.stringify(JSON.stringify(jsonPlan))})`);
  assert(applied === true, "Valid JSON did not synchronize to the form.");
  const synchronized = await evaluate(`({question:document.querySelector('#goalCoreQuestion').value,extension:window.__stage1EditorTest.getWorkingPlan().custom_extension})`);
  assert(synchronized.question.includes("双向同步") && synchronized.extension.extra === "preserved", "JSON-to-form synchronization lost data.");
  await evaluate("document.querySelector('#goalComparison').value='表单修改后的比较对象'; document.querySelector('#goalComparison').dispatchEvent(new Event('input',{bubbles:true})); window.__stage1EditorTest.switchToJson()");
  const roundTrip = await evaluate("JSON.parse(document.querySelector('#planEditor').value)");
  assert(roundTrip.research_goal.comparison_object === "表单修改后的比较对象", "Form-to-JSON synchronization failed.");
  assert(roundTrip.custom_extension.extra === "preserved", "Unknown extension was lost on mode switch.");
  return { synchronized, unknown: roundTrip.custom_extension };
});

await test("invalid_json_and_schema_do_not_overwrite_valid_model", async () => {
  const before = await evaluate("window.__stage1EditorTest.getWorkingPlan()");
  const invalidResult = await evaluate("window.__stage1EditorTest.applyJsonText('{\"research_goal\":')");
  const afterInvalid = await evaluate("window.__stage1EditorTest.getWorkingPlan()");
  const syntaxMessage = await evaluate("document.querySelector('#jsonErrors').textContent");
  assert(invalidResult === false && JSON.stringify(before) === JSON.stringify(afterInvalid), "Invalid JSON overwrote valid data.");
  assert(syntaxMessage.includes("第") && syntaxMessage.includes("行"), "JSON error did not include a line location.");
  const invalidSchema = structuredClone(before); invalidSchema.research_goal.core_question = "";
  const schemaResult = await evaluate(`window.__stage1EditorTest.applyJsonText(${JSON.stringify(JSON.stringify(invalidSchema))})`);
  const afterSchema = await evaluate("window.__stage1EditorTest.getWorkingPlan()");
  const schemaMessage = await evaluate("document.querySelector('#jsonErrors').textContent");
  assert(schemaResult === false && JSON.stringify(before) === JSON.stringify(afterSchema), "Schema-invalid JSON overwrote valid data.");
  assert(schemaMessage.includes("research_goal.core_question"), "Schema error did not identify the field path.");
  await evaluate(`window.__stage1EditorTest.setWorkingPlan(${JSON.stringify(before)}); window.__stage1EditorTest.switchToJson()`);
  const restored = await evaluate("window.__stage1EditorTest.switchToForm()");
  assert(restored === true, "The test could not restore the last valid form state.");
  return { syntaxMessage, schemaMessage };
});

await test("protected_override_generates_manual_overrides", async () => {
  await evaluate("window.__stage1EditorTest.setWorkingPlan(window.__stage1EditorTest.getBaselinePlan()); document.querySelector('#openProtectedDialog').click()");
  await evaluate(`document.querySelector('#protectedPath').value='project_id'; document.querySelector('#protectedPath').dispatchEvent(new Event('change')); document.querySelector('#protectedNewValue').value='PROJECT-EDITOR-OVERRIDE'; document.querySelector('#protectedReason').value='验证受保护字段专用修改流程'; document.querySelector('#protectedActor').value='browser-e2e'; document.querySelector('#protectedForm').requestSubmit()`);
  const plan = await evaluate("window.__stage1EditorTest.getWorkingPlan()");
  const record = plan.manual_overrides.at(-1);
  assert(plan.project_id === "PROJECT-EDITOR-OVERRIDE", "Protected value did not change through the dialog.");
  assert(record.path === "project_id" && record.old_value && record.new_value === "PROJECT-EDITOR-OVERRIDE" && record.reason && record.modified_at && record.actor === "browser-e2e" && record.manual_override === true, "manual_overrides record was incomplete.");
  return record;
});

await test("draft_save_does_not_advance_workflow", async () => {
  await evaluate("window.__stage1EditorTest.setWorkingPlan(window.__stage1EditorTest.getBaselinePlan()); document.querySelector('#goalComparison').value='草稿专用比较对象'; document.querySelector('#goalComparison').dispatchEvent(new Event('input',{bubbles:true}))");
  await evaluate("window.__stage1EditorTest.saveDraft()");
  await waitJs("document.querySelector('#draftStatus').textContent.includes('未提交')", "draft save");
  const response = await fetch(new URL("api/state", pageUrl)); const current = await response.json();
  assert(current.status.status === "WAITING_FOR_USER_APPROVAL" && current.versions.length === 1, "Draft save advanced status or created a version.");
  assert(current.draft.plan.research_goal.comparison_object === "草稿专用比较对象", "Draft did not persist the edited object.");
  return { status: current.status.status, versions: current.versions, draftStatus: current.draft.draft_status };
});

await test("missing_reason_blocks_formal_submission", async () => {
  await evaluate("document.querySelector('#editReason').value=''; document.querySelector('#submitApproval').click()");
  await sleep(300);
  const errorText = await evaluate("document.querySelector('[data-error-for=edit_reason]').textContent");
  const response = await fetch(new URL("api/state", pageUrl)); const current = await response.json();
  assert(errorText.includes("必须填写") && current.versions.length === 1, "Missing modification reason did not block submission.");
  return { errorText, versions: current.versions };
});

await test("check_detects_invalid_dependency_and_natural_summary", async () => {
  let plan = await evaluate("window.__stage1EditorTest.getBaselinePlan()");
  plan.scientific_questions[1].dependencies = ["SQ404"];
  await evaluate(`window.__stage1EditorTest.setWorkingPlan(${JSON.stringify(plan)})`);
  const check = await evaluate("window.__stage1EditorTest.checkPlan(false)");
  assert(check.valid === false && check.errors.some(item => String(item.message).includes("SQ404")), "Invalid dependency was not detected.");
  plan = await evaluate("window.__stage1EditorTest.getBaselinePlan()"); plan.research_goal.comparison_object = "自然语言摘要验证对象";
  await evaluate(`window.__stage1EditorTest.setWorkingPlan(${JSON.stringify(plan)}); window.__stage1EditorTest.renderSummary()`);
  const summary = await evaluate("document.querySelector('#summaryContent').textContent");
  assert(summary.includes("比较对象发生变化") && summary.includes("自然语言摘要验证对象"), "Natural-language modification summary was not shown.");
  await evaluate("document.querySelector('#summaryDialog').close()");
  return { dependencyErrors: check.errors.map(item => item.message), summaryExcerpt: summary.slice(-360) };
});

await test("legacy_views_remain_operational", async () => {
  const tabs = ["current","history","diff","science","work","evidence","results","risks"];
  const checks = {};
  for (const tab of tabs) {
    checks[tab] = await evaluate(`document.querySelector('button[data-view=${tab}]').click(); ({active:document.querySelector('#${tab}').classList.contains('active'),text:document.querySelector('#${tab}').textContent.trim().slice(0,80)})`);
    assert(checks[tab].active && checks[tab].text.length > 0, `Legacy view ${tab} did not render.`);
  }
  return checks;
});

await test("responsive_editor_render", async () => {
  await send("Emulation.setDeviceMetricsOverride", { width: 680, height: 1000, deviceScaleFactor: 1, mobile: false });
  await evaluate("document.querySelector('button[data-view=edit]').click()");
  const layout = await evaluate(`({bodyWidth:document.body.scrollWidth,viewport:window.innerWidth,sticky:document.querySelector('#stickyActions').getBoundingClientRect().width,buttons:[...document.querySelectorAll('#stickyActions button')].every(button=>button.getBoundingClientRect().width>0)})`);
  assert(layout.bodyWidth <= layout.viewport + 2 && layout.buttons, "Narrow layout has horizontal overflow or unusable controls.");
  return { ...layout, screenshot: await screenshot("editor-form-narrow.png") };
});

const report = {
  schema_version: "1.0",
  generated_at: new Date().toISOString(),
  page_url: pageUrl,
  browser: "Microsoft Edge headless via DevTools Protocol",
  results,
  browser_errors: browserErrors,
  overall_status: results.every(item => item.status === "PASSED") && browserErrors.length === 0 ? "PASSED" : "FAILED",
};
await writeFile(path.join(outputDir, "browser_editor_validation.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
socket.close(); edge.kill();
if (report.overall_status !== "PASSED") {
  process.stderr.write(JSON.stringify(report, null, 2) + "\n");
  process.exitCode = 1;
} else {
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
}
