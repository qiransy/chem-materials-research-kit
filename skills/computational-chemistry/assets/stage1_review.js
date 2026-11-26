"use strict";

let state = null;
let baselinePlan = null;
let workingPlan = null;
let lastValidJsonText = "";
let originalSuggestions = {};
let baselineUnknown = new Map();
let jsonUndo = [];
let jsonRedo = [];
let jsonSnapshotTimer = null;
let dirty = false;

const $ = (id) => document.getElementById(id);
const deepClone = (value) => JSON.parse(JSON.stringify(value));
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const compact = (value) => value === null || value === undefined ? "—" : (typeof value === "string" ? value : JSON.stringify(value, null, 2));
const listValue = (value) => Array.isArray(value) ? value.join("\n") : (value === undefined || value === null ? "" : String(value));
const lines = (value) => String(value || "").split(/\r?\n/).map(item => item.trim()).filter(Boolean);

const TOP_LEVEL_FIELDS = new Set([
  "project_id", "stage", "research_goal", "scientific_questions", "systems", "controls", "evidence_chain", "tasks",
  "redundancy_review", "execution_route", "assumptions", "risks", "weight_settings", "protected_records", "change_intents",
  "manual_overrides", "plan_version", "generated_at", "version_record", "schema_version", "status", "request_id", "content_hash",
  "created_at", "updated_at", "confirmed_at"
]);
const GOAL_FIELDS = new Set(["research_object", "comparison_object", "experimental_phenomenon", "core_question", "target_conclusion", "research_boundaries"]);
const QUESTION_FIELDS = new Set(["id", "question", "evidence_target", "dependencies", "depends_on", "notes", "limitations"]);
const SYSTEM_FIELDS = new Set(["id", "name", "role", "description"]);
const CONTROL_FIELDS = new Set(["id", "name", "isolates", "consistency_requirements"]);
const EVIDENCE_FIELDS = new Set(["id", "role", "task_ids", "supports", "required"]);
const TASK_FIELDS = new Set([
  "id", "name", "scientific_question_id", "systems", "controls", "software", "module", "method", "target_parameters",
  "target_data_forms", "scientific_meaning", "supported_conclusions", "experimental_correspondence", "corroborates_with",
  "prerequisites", "downstream_dependencies", "evidence_role", "scientific_weight", "workload_weight", "execution_priority_index",
  "result_sensitivity", "irreplaceability", "priority", "necessity", "alternatives", "redundancy", "status", "user_notes"
]);
const ROUTE_FIELDS = new Set(["order", "action", "gate", "task_id", "name", "description"]);
const ALTERNATIVE_FIELDS = new Set(["condition", "method", "scientific_impact", "workload_impact", "risk", "notes"]);
const SYSTEM_GENERATED_FIELDS = ["stage", "plan_version", "generated_at", "version_record", "schema_version", "status", "request_id", "content_hash", "created_at", "updated_at", "confirmed_at"];

const HELP = {
  research_object: {
    title: "研究对象",
    explanation: "说明实际要计算的材料、分子、晶体、表面或反应体系，并注明结构来自用户文件、数据库、文献还是待构建模型。它直接影响后续模型验收和输入文件生成。",
    good: "金刚石结构体相单晶硅，使用用户确认的最小周期原胞；初始晶格常数来自上传的 CIF 文件。",
    bad: "硅。",
  },
  comparison_object: {
    title: "比较对象",
    explanation: "说明哪些变量会被比较，以及哪些条件必须保持相同。它决定对照组和结果可比性。",
    good: "在相同晶胞、赝势和 k 点下比较 PBE 与 PBEsol 的平衡晶格常数。",
    bad: "比较不同结果。",
  },
  experimental_phenomenon: {
    title: "已知实验现象",
    explanation: "只记录已经由用户或来源材料提供的实验观察、条件和数据来源。没有资料时选择“未提供”，不要推测。",
    good: "300 K XRD 报告晶格常数约 5.43 Å，数据来源为用户上传的实验表。",
    bad: "实验一定证明模型正确。",
  },
  core_question: {
    title: "核心科学问题",
    explanation: "用可检验的问题说明研究变量、统一条件、判断指标与希望回答的关系。后续任务和证据链必须能够直接回答它。",
    good: "在统一晶体结构和收敛标准下，不同交换关联泛函是否会显著改变硅的平衡晶格常数和相对总能量？",
    bad: "研究硅的性质。",
  },
  target_conclusion: {
    title: "预期获得的结论",
    explanation: "写计划通过计算支持、排除或限定的判断，不要把尚未得到的数值或机制写成确定事实。",
    good: "判断在批准的数值精度内，两种泛函对晶格常数的预测差异是否显著。",
    bad: "PBEsol 一定比 PBE 准确。",
  },
  research_boundaries: {
    title: "研究边界",
    explanation: "明确本阶段不回答的内容，防止把单点能、优化结构或电子结构证据解释到其支持范围之外。",
    good: "本阶段不讨论温度效应、缺陷态和跨赝势绝对总能量比较。",
    bad: "无。",
  },
};

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.className = isError ? "show error" : "show";
  window.clearTimeout(node._timer);
  node._timer = window.setTimeout(() => { node.className = ""; }, 4200);
}

function getPath(object, path) {
  if (!path) return object;
  return path.split(".").reduce((value, key) => value === undefined || value === null ? undefined : value[key], object);
}

function setPath(object, path, value, options = {}) {
  const keys = path.split(".");
  let cursor = object;
  keys.slice(0, -1).forEach(key => {
    if (cursor[key] === undefined || cursor[key] === null || typeof cursor[key] !== "object") cursor[key] = {};
    cursor = cursor[key];
  });
  const finalKey = keys[keys.length - 1];
  if (options.deleteWhenEmpty && value === "" && !(finalKey in cursor)) return;
  if (options.deleteWhenEmpty && value === "") delete cursor[finalKey];
  else cursor[finalKey] = value;
}

function nextId(items, prefix, width = 2) {
  const used = new Set((items || []).map(item => String(item && item.id || "")));
  let number = 1;
  while (used.has(`${prefix}${String(number).padStart(width, "0")}`)) number += 1;
  return `${prefix}${String(number).padStart(width, "0")}`;
}

function itemSummary(item, fallback) {
  const text = String(item && (item.question || item.name || item.action || item.role) || fallback || "未命名").trim();
  return text.length > 48 ? `${text.slice(0, 48)}…` : text;
}

function currentQuestionDependencies(question) {
  if (Array.isArray(question.dependencies)) return ["dependencies", question.dependencies];
  if (Array.isArray(question.depends_on)) return ["depends_on", question.depends_on];
  return ["dependencies", []];
}

function markDirty() {
  dirty = !same(workingPlan, baselinePlan);
  $("dirtyStatus").textContent = dirty ? "存在未提交修改" : "没有未保存修改";
  validateAndRender();
}

function makeField(labelText, path, value, options = {}) {
  const block = el("div", null, `field-block ${options.wide ? "wide" : ""}`.trim());
  const label = el("label", labelText);
  if (options.tag) label.append(el("span", options.tag, `field-tag ${options.tagClass || "optional"}`));
  block.append(label);
  let input;
  if (options.type === "select") {
    input = el("select");
    (options.options || []).forEach(([stored, shown]) => {
      const option = el("option", shown);
      option.value = stored;
      option.selected = String(stored) === String(value ?? "");
      input.append(option);
    });
  } else if (options.type === "number") {
    input = el("input"); input.type = "number"; input.min = options.min ?? ""; input.max = options.max ?? ""; input.step = options.step ?? "any"; input.value = value ?? "";
    input.dataset.numberPath = path;
  } else if (options.type === "text") {
    input = el("input"); input.type = "text"; input.value = value ?? "";
  } else {
    input = el("textarea"); input.value = options.list ? listValue(value) : (value ?? "");
  }
  if (!input.dataset.numberPath) {
    if (options.list) input.dataset.listPath = path;
    else input.dataset.path = path;
  }
  if (options.placeholder) input.placeholder = options.placeholder;
  if (options.datalist) input.setAttribute("list", options.datalist);
  block.append(input, el("p", "", "field-error"));
  block.lastElementChild.dataset.errorFor = path;
  return block;
}

function choiceList(labelText, path, choices, selected, options = {}) {
  const block = el("div", null, "field-block wide");
  const label = el("label", labelText);
  if (options.tag) label.append(el("span", options.tag, `field-tag ${options.tagClass || "optional"}`));
  block.append(label);
  const list = el("div", null, "choice-list");
  const current = new Set(Array.isArray(selected) ? selected.map(String) : []);
  choices.forEach(choice => {
    const optionLabel = el("label");
    const input = el("input"); input.type = "checkbox"; input.checked = current.has(String(choice.id)); input.dataset.arrayPath = path; input.dataset.value = choice.id;
    optionLabel.append(input, el("span", choice.label)); list.append(optionLabel);
  });
  block.append(list, el("p", "", "field-error"));
  block.lastElementChild.dataset.errorFor = path;
  return block;
}

function cardHeader(title, id, index, length, kind) {
  const header = el("div", null, "card-header");
  const titleBox = el("div", null, "card-title"); titleBox.append(el("strong", title), el("span", `内部 ID：${id}`, "internal-id"));
  const actions = el("div", null, "card-actions");
  [["↑", "up"], ["↓", "down"], ["复制", "copy"], ["删除", "delete"]].forEach(([text, action]) => {
    const button = el("button", text, action === "delete" ? "danger" : ""); button.type = "button"; button.dataset.cardKind = kind; button.dataset.cardAction = action; button.dataset.index = index;
    if ((action === "up" && index === 0) || (action === "down" && index === length - 1)) button.disabled = true;
    actions.append(button);
  });
  header.append(titleBox, actions); return header;
}

function renderResearchGoal() {
  const goal = workingPlan.research_goal || (workingPlan.research_goal = {});
  const mappings = [
    ["goalResearchObject", "research_object"], ["goalComparison", "comparison_object"], ["goalExperiment", "experimental_phenomenon"],
    ["goalCoreQuestion", "core_question"], ["goalConclusion", "target_conclusion"], ["goalBoundaries", "research_boundaries"]
  ];
  mappings.forEach(([id, key]) => { $(id).value = goal[key] ?? ""; });
  const phenomenon = String(goal.experimental_phenomenon || "");
  let mode = "provided";
  if (!phenomenon || /^未提供/.test(phenomenon)) mode = "not_provided";
  if (/^(不适用|本任务不涉及)/.test(phenomenon)) mode = "not_applicable";
  $("experimentMode").value = mode;
  $("goalExperiment").classList.toggle("hidden", mode !== "provided");
}

function renderQuestions() {
  const root = $("questionCards"); root.replaceChildren();
  const questions = Array.isArray(workingPlan.scientific_questions) ? workingPlan.scientific_questions : (workingPlan.scientific_questions = []);
  questions.forEach((question, index) => {
    const card = el("article", null, "editor-card"); card.dataset.entityId = question.id;
    card.append(cardHeader(`科学问题 ${index + 1}：${itemSummary(question)}`, question.id, index, questions.length, "question"));
    const grid = el("div", null, "card-grid");
    const notesKey = Object.prototype.hasOwnProperty.call(question, "notes") ? "notes" : (Object.prototype.hasOwnProperty.call(question, "limitations") ? "limitations" : "notes");
    grid.append(
      makeField("科学问题", `scientific_questions.${index}.question`, question.question, {wide: true, tag: "必填", tagClass: "required"}),
      makeField("需要获得的证据", `scientific_questions.${index}.evidence_target`, question.evidence_target, {wide: true, tag: "必填", tagClass: "required"}),
      makeField("备注或限制条件", `scientific_questions.${index}.${notesKey}`, question[notesKey] ?? "", {wide: true, tag: "选填", tagClass: "optional"})
    );
    const [dependencyKey, dependencies] = currentQuestionDependencies(question);
    const choices = questions.filter((_, otherIndex) => otherIndex !== index).map((item, n) => ({id: item.id, label: `科学问题 ${questions.indexOf(item) + 1}：${itemSummary(item)}`}));
    grid.append(choiceList("依赖的前置问题", `scientific_questions.${index}.${dependencyKey}`, choices, dependencies, {tag: "选填", tagClass: "optional"}));
    card.append(grid); root.append(card);
  });
}

function renderWeightEditor(task, taskIndex, kind) {
  const isScientific = kind === "scientific_weight";
  const components = isScientific ? ["I", "U", "S", "N"] : ["M", "C", "K", "P", "H"];
  const labels = isScientific ? {I:"核心重要性 I",U:"证据独立性 U",S:"结果敏感性 S",N:"不可替代性 N"} : {M:"模型规模 M",C:"方法复杂度 C",K:"构型/对照数 K",P:"流程/参数测试 P",H:"后处理难度 H"};
  const wrapper = el("div", null, "score-grid");
  const weight = task[kind] || (task[kind] = {rationale:{}}); weight.rationale ||= {};
  components.forEach(component => {
    const box = el("div", null, "score-item");
    box.append(
      makeField(labels[component], `tasks.${taskIndex}.${kind}.${component}`, weight[component] ?? 0, {type:"number", min:0, max:100, step:1}),
      makeField("评分理由", `tasks.${taskIndex}.${kind}.rationale.${component}`, weight.rationale[component] ?? "", {type:"textarea"})
    );
    wrapper.append(box);
  });
  return wrapper;
}

function renderAlternatives(task, taskIndex, container) {
  const alternatives = Array.isArray(task.alternatives) ? task.alternatives : (task.alternatives = []);
  const title = el("h4", "替代方案"); container.append(title);
  alternatives.forEach((alternative, altIndex) => {
    const card = el("div", null, "editor-card");
    const header = el("div", null, "card-header"); header.append(el("strong", `替代方案 ${altIndex + 1}`));
    const remove = el("button", "删除", "danger"); remove.type="button"; remove.dataset.removeAlternative=`${taskIndex}:${altIndex}`; header.append(remove); card.append(header);
    if (alternative && typeof alternative === "object" && !Array.isArray(alternative)) {
      const grid = el("div", null, "card-grid");
      [["适用条件","condition"],["替代方法","method"],["对科学结论的影响","scientific_impact"],["对计算工作量的影响","workload_impact"],["可能增加的风险","risk"],["备注","notes"]].forEach(([label,key]) => grid.append(makeField(label,`tasks.${taskIndex}.alternatives.${altIndex}.${key}`,alternative[key] ?? "",{wide:true})));
      card.append(grid);
    } else {
      card.append(makeField("替代方法与取舍说明", `tasks.${taskIndex}.alternatives.${altIndex}`, alternative ?? "", {wide:true}));
    }
    container.append(card);
  });
  const add = el("button", "＋ 添加替代方案", "add-button"); add.type="button"; add.dataset.addAlternative=taskIndex; container.append(add);
}

function renderTasks() {
  const root = $("taskCards"); root.replaceChildren();
  const tasks = Array.isArray(workingPlan.tasks) ? workingPlan.tasks : (workingPlan.tasks = []);
  const questions = (workingPlan.scientific_questions || []).map(item => [item.id, `${item.id} · ${itemSummary(item)}`]);
  tasks.forEach((task, index) => {
    const card = el("article", null, "editor-card"); card.dataset.entityId = task.id;
    card.append(cardHeader(`任务 ${index + 1}：${itemSummary(task)}`, task.id, index, tasks.length, "task"));
    const grid = el("div", null, "card-grid");
    grid.append(
      makeField("任务名称", `tasks.${index}.name`, task.name, {wide:true, type:"text", tag:"必填", tagClass:"required"}),
      makeField("回答的科学问题", `tasks.${index}.scientific_question_id`, task.scientific_question_id, {type:"select", options:[["","请选择"],...questions], tag:"必填", tagClass:"required"}),
      makeField("计算软件", `tasks.${index}.software`, task.software, {type:"text", datalist:"softwareOptions", tag:"必填", tagClass:"required"}),
      makeField("计算模块", `tasks.${index}.module`, task.module, {type:"text", tag:"必填", tagClass:"required"}),
      makeField("方法与作用", `tasks.${index}.method`, task.method, {wide:true, tag:"必填", tagClass:"required"}),
      makeField("目标参数 / 可观察量", `tasks.${index}.target_parameters`, task.target_parameters, {wide:true, list:true, tag:"必填", tagClass:"required", placeholder:"每行一项；数值保持原类型的复杂参数请在高级模式处理"}),
      makeField("输出数据形式 / 完成条件", `tasks.${index}.target_data_forms`, task.target_data_forms, {wide:true, list:true, tag:"必填", tagClass:"required"}),
      makeField("科学含义", `tasks.${index}.scientific_meaning`, task.scientific_meaning, {wide:true, tag:"必填", tagClass:"required"}),
      makeField("支持的结论", `tasks.${index}.supported_conclusions`, task.supported_conclusions, {wide:true, list:true, tag:"必填", tagClass:"required"}),
      makeField("实验对应关系", `tasks.${index}.experimental_correspondence`, task.experimental_correspondence, {wide:true, list:true}),
      makeField("证据角色", `tasks.${index}.evidence_role`, task.evidence_role, {type:"text", tag:"必填", tagClass:"required"}),
      makeField("结果敏感性", `tasks.${index}.result_sensitivity`, task.result_sensitivity, {tag:"必填", tagClass:"required"}),
      makeField("不可替代性", `tasks.${index}.irreplaceability`, task.irreplaceability, {tag:"必填", tagClass:"required"}),
      makeField("执行优先级", `tasks.${index}.priority`, task.priority, {type:"select", options:[["foundation","基础"],["core","核心"],["mechanism","机理"],["supplemental","补充"],[String(task.priority || ""),String(task.priority || "其他")]], tag:"必填", tagClass:"required"}),
      makeField("必要性", `tasks.${index}.necessity`, task.necessity, {type:"text", tag:"必填", tagClass:"required"}),
      makeField("冗余判断", `tasks.${index}.redundancy`, task.redundancy, {wide:true, tag:"必填", tagClass:"required"}),
      makeField("任务状态", `tasks.${index}.status`, task.status, {type:"text", tag:"必填", tagClass:"required"}),
      makeField("用户备注", `tasks.${index}.user_notes`, task.user_notes, {wide:true, tag:"选填", tagClass:"optional"})
    );
    const systemChoices = (workingPlan.systems || []).map(item => ({id:item.id,label:`${item.id} · ${itemSummary(item)}`}));
    const controlChoices = (workingPlan.controls || []).map(item => ({id:item.id,label:`${item.id} · ${itemSummary(item)}`}));
    const taskChoices = tasks.filter((_, other) => other !== index).map(item => ({id:item.id,label:`${item.id} · ${itemSummary(item)}`}));
    grid.append(
      choiceList("输入研究体系", `tasks.${index}.systems`, systemChoices, task.systems, {tag:"必填",tagClass:"required"}),
      choiceList("使用的对照体系", `tasks.${index}.controls`, controlChoices, task.controls),
      choiceList("前置任务", `tasks.${index}.prerequisites`, taskChoices, task.prerequisites),
      choiceList("后续依赖任务", `tasks.${index}.downstream_dependencies`, taskChoices, task.downstream_dependencies),
      choiceList("互相印证的任务", `tasks.${index}.corroborates_with`, taskChoices, task.corroborates_with)
    );
    card.append(grid);
    const advanced = el("details", null, "mini-details"); advanced.append(el("summary", "展开权重、理由与替代方案"));
    advanced.append(el("h4", "科学权重"), renderWeightEditor(task, index, "scientific_weight"), el("h4", "工作量权重"), renderWeightEditor(task, index, "workload_weight"));
    renderAlternatives(task, index, advanced); card.append(advanced); root.append(card);
  });
}

function renderSimpleEntityCards(kind) {
  const config = {
    system:{key:"systems",root:"systemCards",prefix:"S",fields:[["名称","name"],["角色","role"],["说明","description"]]},
    control:{key:"controls",root:"controlCards",prefix:"C",fields:[["名称","name"],["隔离变量","isolates"],["一致性条件","consistency_requirements"]]},
  }[kind];
  const items = Array.isArray(workingPlan[config.key]) ? workingPlan[config.key] : (workingPlan[config.key] = []);
  const root = $(config.root); root.replaceChildren();
  items.forEach((item,index) => {
    const card=el("article",null,"editor-card"); card.append(cardHeader(itemSummary(item),item.id,index,items.length,kind));
    const grid=el("div",null,"card-grid"); config.fields.forEach(([label,key])=>grid.append(makeField(label,`${config.key}.${index}.${key}`,item[key],{wide:key==="description"||key==="consistency_requirements",tag:key==="name"?"必填":undefined,tagClass:"required"}))); card.append(grid); root.append(card);
  });
}

function renderEvidenceCards() {
  const items=Array.isArray(workingPlan.evidence_chain)?workingPlan.evidence_chain:(workingPlan.evidence_chain=[]); const root=$("evidenceCards"); root.replaceChildren();
  const taskChoices=(workingPlan.tasks||[]).map(item=>({id:item.id,label:`${item.id} · ${itemSummary(item)}`}));
  items.forEach((item,index)=>{
    const card=el("article",null,"editor-card"); card.append(cardHeader(itemSummary(item),item.id,index,items.length,"evidence")); const grid=el("div",null,"card-grid");
    grid.append(makeField("证据功能",`evidence_chain.${index}.role`,item.role,{tag:"必填",tagClass:"required"}),makeField("支持的结论",`evidence_chain.${index}.supports`,item.supports,{wide:true,tag:"必填",tagClass:"required"}),choiceList("关联任务",`evidence_chain.${index}.task_ids`,taskChoices,item.task_ids,{tag:"必填",tagClass:"required"}));
    const required=el("label"); const checkbox=el("input"); checkbox.type="checkbox"; checkbox.checked=Boolean(item.required); checkbox.dataset.booleanPath=`evidence_chain.${index}.required`; required.append(checkbox,el("span","这是不可缺失的必要证据")); grid.append(required); card.append(grid); root.append(card);
  });
}

function renderRoutes() {
  const routes=Array.isArray(workingPlan.execution_route)?workingPlan.execution_route:(workingPlan.execution_route=[]); const root=$("routeCards"); root.replaceChildren();
  routes.forEach((route,index)=>{
    const card=el("article",null,"editor-card"); card.append(cardHeader(`步骤 ${index+1}：${itemSummary(route)}`,String(route.order??index+1),index,routes.length,"route")); const grid=el("div",null,"card-grid");
    grid.append(makeField("顺序",`execution_route.${index}.order`,route.order??index+1,{type:"number",min:1,step:1}),makeField("执行内容",`execution_route.${index}.action`,route.action??route.name??"",{wide:true,tag:"必填",tagClass:"required"}),makeField("进入下一步的条件",`execution_route.${index}.gate`,route.gate??"",{wide:true,tag:"建议填写",tagClass:"recommended"})); card.append(grid); root.append(card);
  });
}

function renderNotes() {
  $("assumptionsEditor").value=listValue(workingPlan.assumptions);
  $("risksEditor").value=listValue(workingPlan.risks);
  const root=$("redundancyEditor"); root.replaceChildren();
  const value=workingPlan.redundancy_review;
  if(value && typeof value==="object" && !Array.isArray(value)) Object.entries(value).forEach(([key,items])=>root.append(makeField(key,`redundancy_review.${key}`,items,{wide:true,list:Array.isArray(items)})));
  else root.append(makeField("冗余与取舍说明","redundancy_review",value??"",{wide:true}));
}

function flattenProtected(value, prefix="protected_records") {
  const result=[];
  if(value && typeof value==="object" && !Array.isArray(value)) Object.entries(value).forEach(([key,item])=>{
    const path=`${prefix}.${key}`; if(item && typeof item==="object" && !Array.isArray(item)) result.push(...flattenProtected(item,path)); else result.push([path,item]);
  });
  return result;
}

function renderProtected() {
  const root=$("protectedRecords"); root.replaceChildren();
  const entries=[["project_id",workingPlan.project_id],...flattenProtected(workingPlan.protected_records||{})];
  const overrides=Array.isArray(workingPlan.manual_overrides)?workingPlan.manual_overrides:[];
  entries.forEach(([path,value])=>{
    const card=el("div",null,"unknown-entry"); const left=el("div"); left.append(el("code",path),el("span"," 受保护","field-tag protected"));
    const matching=overrides.filter(item=>item&&item.path===path); if(matching.length) left.append(el("span"," 已人工覆盖","field-tag override"));
    const pre=el("pre",compact(value)); card.append(left,pre); root.append(card);
    matching.forEach(item=>{const record=el("div",null,"override-record");record.textContent=`修改理由：${item.reason}；时间：${item.modified_at||"未记录"}；操作者：${item.actor||"未记录"}`;root.append(record);});
  });
}

function collectUnknown(plan) {
  const result=new Map();
  const addUnknown=(object,known,prefix)=>{if(!object||typeof object!=="object"||Array.isArray(object))return;Object.entries(object).forEach(([key,value])=>{if(!known.has(key))result.set(`${prefix}.${key}`,deepClone(value));});};
  addUnknown(plan,TOP_LEVEL_FIELDS,"$"); addUnknown(plan.research_goal,GOAL_FIELDS,"research_goal");
  [["scientific_questions",QUESTION_FIELDS],["systems",SYSTEM_FIELDS],["controls",CONTROL_FIELDS],["evidence_chain",EVIDENCE_FIELDS],["tasks",TASK_FIELDS]].forEach(([listName,known])=>{
    (plan[listName]||[]).forEach((item,index)=>{const stable=item&&item.id?`${listName}[id=${item.id}]`:`${listName}[${index}]`;addUnknown(item,known,stable);});
  });
  (plan.execution_route||[]).forEach((item,index)=>addUnknown(item,ROUTE_FIELDS,`execution_route[${index}]`));
  (plan.tasks||[]).forEach(task=>(task.alternatives||[]).forEach((item,index)=>{if(item&&typeof item==="object"&&!Array.isArray(item))addUnknown(item,ALTERNATIVE_FIELDS,`tasks[id=${task.id}].alternatives[${index}]`);}));
  return result;
}

function renderUnknownFields() {
  const root=$("unknownFields"); root.replaceChildren(); const unknown=collectUnknown(workingPlan);
  if(!unknown.size){root.append(el("p","当前方案没有无法安全表单化的扩展字段。","small"));return;}
  unknown.forEach((value,path)=>{const row=el("div",null,"unknown-entry");row.append(el("code",path),el("pre",compact(value)));root.append(row);});
}

function renderForm() {
  renderResearchGoal(); renderQuestions(); renderTasks(); renderSimpleEntityCards("system"); renderSimpleEntityCards("control"); renderEvidenceCards(); renderRoutes(); renderNotes(); renderProtected(); renderUnknownFields(); validateAndRender();
}

function cycleFromEdges(ids, edges) {
  const graph=new Map(ids.map(id=>[id,[]])); edges.forEach(([from,to])=>{if(graph.has(from)&&graph.has(to))graph.get(from).push(to);});
  const visiting=new Set(),visited=new Set(); let found=null;
  function visit(id,path){if(visiting.has(id)){found=[...path,id];return;}if(visited.has(id)||found)return;visiting.add(id);for(const next of graph.get(id)||[])visit(next,[...path,id]);visiting.delete(id);visited.add(id);}
  ids.forEach(id=>visit(id,[])); return found;
}

function changedLeafPaths(before, after, prefix) {
  if (same(before, after)) return [];
  if (before && after && typeof before === "object" && typeof after === "object" && !Array.isArray(before) && !Array.isArray(after)) {
    return [...new Set([...Object.keys(before), ...Object.keys(after)])].flatMap(key => changedLeafPaths(before[key], after[key], `${prefix}.${key}`));
  }
  return [prefix];
}

function validatePlan(plan) {
  const errors=[],warnings=[],completed=[];
  const error=(path,message)=>errors.push({path,message}); const warn=(path,message)=>warnings.push({path,message});
  const goal=plan.research_goal;
  if(!goal||typeof goal!=="object") error("research_goal","研究目标必须是一个结构化对象。");
  else {
    [["research_object","研究对象"],["core_question","核心科学问题"],["target_conclusion","预期获得的结论"]].forEach(([key,label])=>{if(!String(goal[key]||"").trim())error(`research_goal.${key}`,`${label}为必填项。`);else completed.push(label);});
    const objectText=String(goal.research_object||"");
    if(objectText && !/(结构|晶格|晶胞|坐标|CIF|POSCAR|文件|来源|数据库|文献|用户|构建|原胞|分子式)/i.test(objectText)) warn("research_goal.research_object","当前研究对象缺少结构来源，后续无法稳定生成计算输入文件。");
    const question=String(goal.core_question||"").trim();
    if(question && (question.length<18 || /^(研究|计算|分析).{0,8}(性质|结果|体系)?[。？?]?$/.test(question))) warn("research_goal.core_question","核心科学问题过于宽泛，建议明确比较变量和判断指标。");
    const conclusion=String(goal.target_conclusion||"");
    if(/(一定|必然|已经证明|完全证明|确定无疑|绝对正确)/.test(conclusion)) warn("research_goal.target_conclusion","该目标结论包含绝对性表述，请改为可由计算结果验证的判断。");
  }
  ["scientific_questions","systems","controls","evidence_chain","tasks"].forEach(key=>{if(!Array.isArray(plan[key])||!plan[key].length)error(key,`${key} 至少需要一项。`);else completed.push(key);});
  const questions=Array.isArray(plan.scientific_questions)?plan.scientific_questions:[]; const questionIds=new Set(); const normalized=new Map(); const qEdges=[];
  questions.forEach((item,index)=>{
    const path=`scientific_questions.${index}`; if(!item||typeof item!=="object"){error(path,"科学问题必须是对象。");return;}
    if(!String(item.id||"").trim())error(`${path}.id`,"内部科学问题 ID 缺失。"); else if(questionIds.has(String(item.id)))error(`${path}.id`,`内部 ID ${item.id} 重复。`); else questionIds.add(String(item.id));
    if(!String(item.question||"").trim())error(`${path}.question`,"科学问题不能为空。");
    if(!String(item.evidence_target||"").trim())error(`${path}.evidence_target`,"需要获得的证据不能为空。");
    const key=String(item.question||"").trim().replace(/[\s，。！？?]/g,"").toLowerCase(); if(key){if(normalized.has(key))error(`${path}.question`,`与科学问题 ${normalized.get(key)+1} 重复。`);else normalized.set(key,index);}
    const [,deps]=currentQuestionDependencies(item); deps.forEach(dep=>{if(!questions.some(q=>String(q.id)===String(dep)))error(`${path}.dependencies`,`依赖的问题 ${dep} 不存在，请重新设置依赖关系。`);else qEdges.push([String(item.id),String(dep)]);});
  });
  const qCycle=cycleFromEdges([...questionIds],qEdges); if(qCycle)error("scientific_questions",`科学问题存在循环依赖：${qCycle.join(" → ")}。`);
  const systems=new Set((plan.systems||[]).map(item=>String(item&&item.id))); const controls=new Set((plan.controls||[]).map(item=>String(item&&item.id)));
  const tasks=Array.isArray(plan.tasks)?plan.tasks:[]; const taskIds=new Set(); const taskEdges=[];
  tasks.forEach((task,index)=>{
    const path=`tasks.${index}`; if(!task||typeof task!=="object"){error(path,"任务必须是对象。");return;}
    if(!String(task.id||"").trim())error(`${path}.id`,"内部任务 ID 缺失。");else if(taskIds.has(String(task.id)))error(`${path}.id`,`任务 ID ${task.id} 重复。`);else taskIds.add(String(task.id));
    [["name","任务名称"],["scientific_question_id","科学问题"],["software","软件"],["module","模块"],["method","方法"],["scientific_meaning","科学含义"],["evidence_role","证据角色"],["result_sensitivity","结果敏感性"],["irreplaceability","不可替代性"],["priority","优先级"],["necessity","必要性"],["redundancy","冗余判断"],["status","任务状态"]].forEach(([key,label])=>{if(!String(task[key]||"").trim())error(`${path}.${key}`,`${label}不能为空。`);});
    if(!questionIds.has(String(task.scientific_question_id)))error(`${path}.scientific_question_id`,`引用的科学问题 ${task.scientific_question_id||"—"} 不存在。`);
    if(!Array.isArray(task.systems)||!task.systems.length)error(`${path}.systems`,"任务缺少输入研究体系。"); else task.systems.forEach(id=>{if(!systems.has(String(id)))error(`${path}.systems`,`研究体系 ${id} 不存在。`);});
    if(!Array.isArray(task.target_parameters)||!task.target_parameters.length)error(`${path}.target_parameters`,"任务缺少目标参数。");
    if(!Array.isArray(task.target_data_forms)||!task.target_data_forms.length)error(`${path}.target_data_forms`,"任务缺少输出数据形式或完成条件。");
    (task.controls||[]).forEach(id=>{if(!controls.has(String(id)))error(`${path}.controls`,`对照体系 ${id} 不存在。`);});
    (task.prerequisites||[]).forEach(dep=>taskEdges.push([String(task.id),String(dep)]));
    const software=String(task.software||"").toLowerCase(),module=String(task.module||"").toLowerCase();
    if((software.includes("gaussian")||software.includes("orca")||software.includes("cp2k")) && /^pw\.x$/.test(module)) error(`${path}.module`,`软件 ${task.software} 与 Quantum ESPRESSO 模块 pw.x 不兼容。`);
    if(software.includes("quantum espresso") && /(^|\s)(g16|orca|quickstep)(\s|$)/.test(module)) error(`${path}.module`,`软件与模块组合明显不兼容，请核对。`);
    ["scientific_weight","workload_weight"].forEach(kind=>{const weight=task[kind];if(!weight||typeof weight!=="object")error(`${path}.${kind}`,`${kind} 必须是评分对象。`);else Object.entries(weight).forEach(([key,value])=>{if(key!=="rationale"&&key!=="value"&&(typeof value!=="number"||value<0||value>100))error(`${path}.${kind}.${key}`,"权重分量必须是 0–100 的数字。");});});
  });
  taskEdges.forEach(([from,to])=>{if(!taskIds.has(to))error(`tasks.${Math.max(0,tasks.findIndex(item=>String(item.id)===from))}.prerequisites`,`前置任务 ${to} 不存在。`);});
  const taskCycle=cycleFromEdges([...taskIds],taskEdges); if(taskCycle)error("tasks",`任务存在循环依赖：${taskCycle.join(" → ")}。`);
  (plan.evidence_chain||[]).forEach((item,index)=>{if(!item||typeof item!=="object")return;(item.task_ids||[]).forEach(id=>{if(!taskIds.has(String(id)))error(`evidence_chain.${index}.task_ids`,`证据节点引用的任务 ${id} 不存在。`);});});
  baselineUnknown.forEach((value,path)=>{if(!collectUnknown(plan).has(path))error(path,`未知扩展字段 ${path} 被删除；请恢复或在高级模式明确处理。`);});
  const overrides=Array.isArray(plan.manual_overrides)?plan.manual_overrides:[];
  const changedProtected=[]; if(baselinePlan&&plan.project_id!==baselinePlan.project_id)changedProtected.push("project_id");
  if(baselinePlan)changedProtected.push(...changedLeafPaths(baselinePlan.protected_records,plan.protected_records,"protected_records"));
  changedProtected.forEach(path=>{if(!overrides.some(item=>item&&item.path===path&&String(item.reason||"").trim()))error(path,`受保护字段 ${path} 已修改，但缺少修改理由。`);});
  if(!Array.isArray(plan.assumptions)||!plan.assumptions.length)warn("assumptions","建议记录暂定假设及确认条件。");
  if(!Array.isArray(plan.risks)||!plan.risks.length)warn("risks","建议记录科学、技术或可比性风险。");
  return {errors,warnings,completed:[...new Set(completed)]};
}

function renderValidation(result) {
  document.querySelectorAll(".field-error").forEach(node=>node.textContent=""); document.querySelectorAll(".invalid-field").forEach(node=>node.classList.remove("invalid-field"));
  result.errors.forEach(item=>{
    const message=document.querySelector(`[data-error-for="${CSS.escape(item.path)}"]`); if(message)message.textContent=item.message;
    const input=document.querySelector(`[data-path="${CSS.escape(item.path)}"],[data-list-path="${CSS.escape(item.path)}"],[data-number-path="${CSS.escape(item.path)}"]`); if(input)input.classList.add("invalid-field");
  });
  const score=Math.max(0,Math.min(100,100-result.errors.length*12-result.warnings.length*3)); $("completenessValue").textContent=`${score}%`; $("completenessBar").style.width=`${score}%`;
  const fillList=(id,items,emptyText)=>{const root=$(id);root.replaceChildren();(items.length?items:[emptyText]).forEach(item=>root.append(el("li",typeof item==="string"?item:item.message)));};
  fillList("completedItems",result.completed,"尚无"); fillList("pendingItems",result.warnings,"无待确认项目"); fillList("blockingItems",result.errors,"无阻塞问题"); fillList("warningItems",result.warnings,"无一般提醒");
  return result;
}

function validateAndRender() { return renderValidation(validatePlan(workingPlan)); }

function syntaxPosition(text,error) {
  const match=String(error.message||error).match(/position\s+(\d+)/i); if(!match)return {line:1,column:1,position:0}; const position=Number(match[1]); const before=text.slice(0,position); const line=before.split("\n").length; const last=before.lastIndexOf("\n"); return {line,column:position-(last<0?-1:last),position};
}

function escapedJsonHighlight(text) {
  const escaped=text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  return escaped.replace(/("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"\s*:)|("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*")|\b(true|false)\b|\b(null)\b|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/g,(match,key,string,bool,nil)=>`<span class="${key?"json-key":string?"json-string":bool?"json-boolean":nil?"json-null":"json-number"}">${match}</span>`);
}

function updateJsonPresentation() {
  const text=$("planEditor").value; const lineCount=Math.max(1,text.split("\n").length); $("jsonLineNumbers").textContent=Array.from({length:lineCount},(_,index)=>index+1).join("\n"); $("jsonHighlight").innerHTML=escapedJsonHighlight(text); updateCursorStatus();
}

function jsonPathAtCursor(text,position) {
  const linesBefore=text.slice(0,position).split("\n"); const stack=[];
  linesBefore.forEach(line=>{const key=line.match(/^\s*"((?:\\.|[^"])*)"\s*:/); if(key){const indent=(line.match(/^\s*/)||[""])[0].length; while(stack.length&&stack[stack.length-1].indent>=indent)stack.pop();stack.push({indent,key:key[1]});}});
  return stack.map(item=>item.key).join(".")||"—";
}

function bracketMatch(text,position) {
  const pairs={"{":"}","[":"]","}":"{","]":"["}; let index=position; if(!pairs[text[index]])index=position-1; const char=text[index]; if(!pairs[char])return "—"; const forward=char==="{"||char==="["; let depth=0,inString=false,escaped=false;
  for(let i=index;forward?i<text.length:i>=0;forward?i++:i--){const c=text[i];if(c==='"'&&!escaped)inString=!inString;escaped=c==='\\'&&!escaped;if(inString)continue;if(c===char)depth++;if(c===pairs[char])depth--;if(depth===0)return `第 ${text.slice(0,i).split("\n").length} 行`;}
  return "未匹配";
}

function updateCursorStatus() {
  const input=$("planEditor"),position=input.selectionStart,text=input.value,before=text.slice(0,position),line=before.split("\n").length,last=before.lastIndexOf("\n"); $("jsonCursor").textContent=`第 ${line} 行，第 ${position-(last<0?-1:last)} 列`; $("jsonPath").textContent=`字段路径：${jsonPathAtCursor(text,position)}`; $("bracketStatus").textContent=`括号：${bracketMatch(text,position)}`;
}

function showJsonMessages(errors=[],warnings=[]) {
  const root=$("jsonErrors"); root.replaceChildren(); errors.forEach(item=>root.append(el("div",`${item.path?item.path+"：":""}${item.message||item}`,"error"))); warnings.forEach(item=>root.append(el("div",`${item.path?item.path+"：":""}${item.message||item}`,"warning"))); if(!errors.length&&!warnings.length)root.append(el("div","JSON 语法和方案结构校验通过。","notice"));
}

function protectedJsonDifferences(parsed) {
  const differences=[]; ["project_id","protected_records","manual_overrides",...SYSTEM_GENERATED_FIELDS].forEach(path=>{if(!same(getPath(parsed,path),getPath(workingPlan,path)))differences.push(path);}); return [...new Set(differences)];
}

async function applyJsonToModel(options={}) {
  const text=$("planEditor").value; let parsed;
  try{parsed=JSON.parse(text);}catch(error){const pos=syntaxPosition(text,error);showJsonMessages([{path:`第 ${pos.line} 行，第 ${pos.column} 列`,message:error.message}]);$("planEditor").focus();$("planEditor").setSelectionRange(pos.position,pos.position+1);return false;}
  if(!parsed||typeof parsed!=="object"||Array.isArray(parsed)){showJsonMessages([{path:"$",message:"顶层必须是 JSON 对象。"}]);return false;}
  const protectedChanges=protectedJsonDifferences(parsed); if(protectedChanges.length){showJsonMessages(protectedChanges.map(path=>({path,message:"系统或受保护字段不能在高级 JSON 中直接修改，请使用受保护字段对话框。"})));return false;}
  const local=validatePlan(parsed); let backend={errors:[],warnings:[]};
  try{const response=await post("/api/check",{plan:parsed},{reload:false});backend=response.result;}catch(error){showJsonMessages([{path:"server",message:error.message}]);return false;}
  const errors=[...local.errors,...(backend.errors||[]).map(message=>({path:"schema",message}))]; const warnings=[...local.warnings,...(backend.warnings||[]).map(message=>({path:"schema",message}))]; showJsonMessages(errors,warnings); if(errors.length)return false;
  workingPlan=deepClone(backend.checked_plan||parsed); lastValidJsonText=JSON.stringify(workingPlan,null,2); $("planEditor").value=lastValidJsonText; updateJsonPresentation(); renderForm(); markDirty(); if(!options.silent)toast("高级 JSON 已通过校验并同步到表单。"); return true;
}

function switchToJson() {
  $("formMode").classList.add("hidden"); $("jsonMode").classList.remove("hidden"); $("formModeButton").classList.remove("active"); $("jsonModeButton").classList.add("active"); $("formModeButton").setAttribute("aria-selected","false"); $("jsonModeButton").setAttribute("aria-selected","true");
  lastValidJsonText=JSON.stringify(workingPlan,null,2); $("planEditor").value=lastValidJsonText; jsonUndo=[lastValidJsonText]; jsonRedo=[]; updateJsonPresentation(); $("modeStatus").textContent="高级 JSON 正在编辑同一方案对象；只有通过语法、Schema 和保护字段校验后才会写回表单。";
}

async function switchToForm() { if(!await applyJsonToModel({silent:true}))return false; $("jsonMode").classList.add("hidden"); $("formMode").classList.remove("hidden"); $("jsonModeButton").classList.remove("active"); $("formModeButton").classList.add("active"); $("jsonModeButton").setAttribute("aria-selected","false"); $("formModeButton").setAttribute("aria-selected","true"); $("modeStatus").textContent="表单与 JSON 使用同一个内存数据对象。"; return true; }

function technicalDiff(before,after,path="$",result=[]) {
  if(same(before,after))return result;
  if(before&&after&&typeof before==="object"&&typeof after==="object"&&!Array.isArray(before)&&!Array.isArray(after)){[...new Set([...Object.keys(before),...Object.keys(after)])].sort().forEach(key=>technicalDiff(before[key],after[key],`${path}.${key}`,result));return result;}
  result.push({path,before,after}); return result;
}

function naturalDiff(before,after) {
  const messages=[]; const goalLabels={research_object:"研究对象",comparison_object:"比较对象",experimental_phenomenon:"实验现象",core_question:"核心科学问题",target_conclusion:"预期结论",research_boundaries:"研究边界"};
  Object.entries(goalLabels).forEach(([key,label])=>{const old=before.research_goal&&before.research_goal[key],now=after.research_goal&&after.research_goal[key];if(!same(old,now))messages.push(`${label}发生变化：原方案为“${compact(old)}”；新方案为“${compact(now)}”。`);});
  const entityChanges=(key,label)=>{const oldMap=new Map((before[key]||[]).map(item=>[item.id,item])),newMap=new Map((after[key]||[]).map(item=>[item.id,item]));newMap.forEach((item,id)=>{if(!oldMap.has(id))messages.push(`新增${label}：${itemSummary(item)}。`);else if(!same(oldMap.get(id),item))messages.push(`修改${label} ${id}：${itemSummary(item)}。`);});oldMap.forEach((item,id)=>{if(!newMap.has(id))messages.push(`删除${label} ${id}：${itemSummary(item)}。`);});};
  entityChanges("scientific_questions","科学问题"); entityChanges("tasks","计算任务"); entityChanges("systems","研究体系"); entityChanges("controls","对照体系"); entityChanges("evidence_chain","证据节点");
  const beforeSoftware=(before.tasks||[]).map(item=>`${item.id}:${item.software}/${item.module}/${item.method}`),afterSoftware=(after.tasks||[]).map(item=>`${item.id}:${item.software}/${item.module}/${item.method}`); if(!same(beforeSoftware,afterSoftware))messages.push("软件、模块或计算方法发生变化，请核对兼容性和不同版本之间的可比性。");
  const beforeParams=(before.tasks||[]).map(item=>[item.id,item.target_parameters]),afterParams=(after.tasks||[]).map(item=>[item.id,item.target_parameters]); if(!same(beforeParams,afterParams))messages.push("任务目标参数发生变化，可能改变输出数据范围和结果解释边界。");
  const beforeDeps=(before.tasks||[]).map(item=>[item.id,item.prerequisites,item.downstream_dependencies]),afterDeps=(after.tasks||[]).map(item=>[item.id,item.prerequisites,item.downstream_dependencies]); if(!same(beforeDeps,afterDeps)||!same(before.execution_route,after.execution_route))messages.push("依赖关系或执行顺序发生变化，系统将重新检查无效引用和循环依赖。");
  const beforeAlt=(before.tasks||[]).map(item=>[item.id,item.alternatives]),afterAlt=(after.tasks||[]).map(item=>[item.id,item.alternatives]); if(!same(beforeAlt,afterAlt))messages.push("替代方案发生变化，请检查其适用条件、科学影响、工作量影响和新增风险。");
  if((before.tasks||[]).length!==(after.tasks||[]).length)messages.push(`工作量变化：任务数量由 ${(before.tasks||[]).length} 项变为 ${(after.tasks||[]).length} 项。`);
  if(!same(before.risks,after.risks))messages.push("风险记录发生变化，请在批准前确认新增、删除或重述的风险。");
  if(!same((before.tasks||[]).map(item=>item.supported_conclusions),(after.tasks||[]).map(item=>item.supported_conclusions)))messages.push("结果解释范围发生变化：任务所支持的结论已调整。");
  return messages.length?messages:["当前编辑内容与候选版本一致，没有待提交差异。"];
}

function renderTechnicalDiff(container,diffs) { container.replaceChildren(); if(!diffs.length){container.append(el("p","没有技术差异。"));return;} container.append(table(["字段路径","修改前","修改后"],diffs.map(item=>[item.path,item.before,item.after]))); }

function renderSummary() {
  const root=$("summaryContent"); root.replaceChildren(); const goal=workingPlan.research_goal||{};
  const overview=el("div",null,"grid"); [["研究对象",goal.research_object],["核心科学问题",goal.core_question],["预期结论",goal.target_conclusion],["软件与方法",(workingPlan.tasks||[]).map(item=>`${item.name}：${item.software} / ${item.module} / ${item.method}`).join("\n")],["主要参数",(workingPlan.tasks||[]).flatMap(item=>item.target_parameters||[]).join("；")],["主要风险",(workingPlan.risks||[]).join("\n")]].forEach(([label,value])=>{const card=el("div",null,"card");card.append(el("strong",label),el("div",compact(value)));overview.append(card);}); root.append(overview,el("h3","科学问题")); (workingPlan.scientific_questions||[]).forEach((item,index)=>root.append(el("p",`${index+1}. ${item.question}（证据：${item.evidence_target}）`))); root.append(el("h3","关键任务"));(workingPlan.tasks||[]).forEach((item,index)=>root.append(el("p",`${index+1}. ${item.name}；前置任务：${(item.prerequisites||[]).join("、")||"无"}；输出：${(item.target_data_forms||[]).join("、")}`))); root.append(el("h3","自然语言修改摘要"));naturalDiff(baselinePlan,workingPlan).forEach(message=>root.append(el("p",`• ${message}`))); renderTechnicalDiff($("summaryTechnicalDiff"),technicalDiff(baselinePlan,workingPlan)); $("summaryDialog").showModal();
}

function table(headers,rows) { const wrap=el("div",null,"table-wrap"),node=el("table"),thead=el("thead"),trh=el("tr");headers.forEach(value=>trh.append(el("th",value)));thead.append(trh);node.append(thead);const body=el("tbody");rows.forEach(row=>{const tr=el("tr");row.forEach(value=>tr.append(el("td",compact(value))));body.append(tr);});node.append(body);wrap.append(node);return wrap; }
function panel(title) { const box=el("div",null,"panel");box.append(el("h2",title));return box; }

function renderCurrent() {
  const root=$("currentContent");root.replaceChildren();const plan=state.plan,goal=plan.research_goal||{},overview=panel("研究目标与核心问题"),grid=el("div",null,"grid");[["研究对象",goal.research_object],["比较对象",goal.comparison_object],["实验现象",goal.experimental_phenomenon],["核心问题",goal.core_question],["目标结论",goal.target_conclusion]].forEach(([key,value])=>{const card=el("div",null,"card");card.append(el("strong",key),el("div",compact(value)));grid.append(card);});overview.append(grid);root.append(overview);
  const questions=panel("科学子问题");questions.append(table(["ID","科学问题","证据目标","依赖"],(plan.scientific_questions||[]).map(item=>[item.id,item.question,item.evidence_target,item.dependencies||item.depends_on||[]])));root.append(questions);
  const systemsPanel=panel("研究体系与对照体系");systemsPanel.append(el("h3","研究体系"),table(["ID","名称","角色","说明"],(plan.systems||[]).map(item=>[item.id,item.name,item.role,item.description])),el("h3","对照体系"),table(["ID","名称","隔离变量","一致性条件"],(plan.controls||[]).map(item=>[item.id,item.name,item.isolates,item.consistency_requirements])));root.append(systemsPanel);
  const tasksPanel=panel("计算任务");const fields=["id","name","scientific_question_id","systems","controls","software","module","method","target_parameters","target_data_forms","scientific_meaning","supported_conclusions","experimental_correspondence","corroborates_with","prerequisites","downstream_dependencies","evidence_role","scientific_weight","workload_weight","execution_priority_index","result_sensitivity","irreplaceability","priority","necessity","alternatives","redundancy","status","user_notes"];tasksPanel.append(table(fields,(plan.tasks||[]).map(task=>fields.map(field=>task[field]))));root.append(tasksPanel);
}

function renderHistory() { const root=$("historyContent");root.replaceChildren();const box=panel("版本历史");box.append(table(["时间","事件","版本","前一版本","来源/原因","状态变化"],(state.change_log||[]).map(item=>[item.timestamp,item.event,item.version||item.new_version,item.previous_version||item.source_version,item.reason,`${item.status_before||"—"} → ${item.status_after||"—"}`])));root.append(box);const select=$("restoreVersion");select.replaceChildren();(state.versions||[]).forEach(version=>{const option=el("option",version);option.value=version;select.append(option);}); }

function impactNaturalSentence(change) { const category=change.path.startsWith("research_goal")?"研究目标":change.path.startsWith("scientific_questions")?"科学问题":change.path.startsWith("tasks")?"计算任务":change.path.startsWith("systems")||change.path.startsWith("controls")?"体系或对照":change.path.startsWith("evidence_chain")?"证据链":change.path.startsWith("risks")?"风险":"方案字段"; return `${category}${change.kind==="added"?"新增":change.kind==="deleted"?"删除":"修改"}：${change.path}；由“${compact(change.before)}”变为“${compact(change.after)}”。影响等级 ${change.impact_level}：${change.impact_reason}`; }
function renderDiff() { const root=$("diffContent");root.replaceChildren();const analysis=state.analysis,box=panel("最近两个版本的前后差异");if(!analysis){box.append(el("p","初始版本尚无前后差异。"));root.append(box);return;}box.append(el("p","默认显示便于阅读的自然语言差异。","small"));(analysis.changes||[]).forEach(change=>box.append(el("p",`• ${impactNaturalSentence(change)}`)));const details=el("details");details.append(el("summary","查看技术差异"),table(["变化","路径","修改前","修改后","修改理由","影响等级","原因","建议"],(analysis.changes||[]).map(item=>[item.kind,item.path,item.before,item.after,item.user_reason,item.impact_level,item.impact_reason,item.recommendation])));box.append(details);root.append(box); }

function bars(containerId,key,title,className) { const root=$(containerId);root.replaceChildren();const box=panel(title),tasks=state.plan.tasks||[];tasks.forEach(task=>{const value=(task[key]||{}).value||0,row=el("div",null,"bar-row");row.append(el("span",`${task.id} ${task.name}`));const bar=el("div",null,`bar ${className||""}`),fill=el("span");fill.style.width=`${Math.max(0,Math.min(100,value))}%`;bar.append(fill);row.append(bar,el("span",value));box.append(row);});box.append(el("p",key==="workload_weight"?"工作量权重只表示当前方案内部相对复杂度，不是运行时间、内存或存储估计。":"科学权重由重要性、证据独立性、结果敏感性和不可替代性分别评分后计算。","small"));root.append(box); }
function weightChangeTable(kind){const analysis=state.analysis;if(!analysis)return null;const before=(analysis.weight_changes||{}).before||{},after=(analysis.weight_changes||{}).after||{},ids=[...new Set([...Object.keys(before),...Object.keys(after)])].sort();return table(["任务","修改前","修改后","变化"],ids.map(id=>{const old=(before[id]||{})[kind]||0,now=(after[id]||{})[kind]||0;return[id,old,now,Math.round((now-old)*100)/100];}));}
function renderScience(){bars("scienceContent","scientific_weight","当前科学权重","");const comparison=weightChangeTable("scientific");if(comparison){const box=panel("科学权重前后变化");box.append(comparison);$("scienceContent").prepend(box);}}
function renderWork(){bars("workContent","workload_weight","当前工作量权重","work");const analysis=state.analysis;if(analysis){const box=panel("总体工作量变化"),work=analysis.workload_change;box.append(el("p",`${work.label}；任务 ${work.task_count_before} → ${work.task_count_after}，体系 ${work.model_count_before} → ${work.model_count_after}，对照 ${work.control_count_before} → ${work.control_count_after}，相对权重变化 ${work.relative_weight_delta}。`),el("p",work.note,"small"));const comparison=weightChangeTable("workload");if(comparison)box.append(comparison);$("workContent").prepend(box);}}
function renderEvidence(){const root=$("evidenceContent");root.replaceChildren();const box=panel("证据链变化");box.append(table(["ID","证据功能","任务","支持结论","是否必需"],(state.plan.evidence_chain||[]).map(item=>[item.id,item.role,item.task_ids,item.supports,item.required])));const changes=((state.analysis||{}).changes||[]).filter(item=>item.path.startsWith("evidence_chain")||item.path.includes("evidence_role")||(item.path.startsWith("tasks[")&&["added","deleted","merged","split","replaced"].includes(item.kind)));if(changes.length)box.append(el("h3","证据链相关修改"),table(["变化","路径","修改前","修改后","影响"],changes.map(item=>[item.kind,item.path,item.before,item.after,`${item.impact_level}: ${item.impact_reason}`])));const gaps=(state.analysis||{}).evidence_gaps||[];if(gaps.length){const notice=el("div",null,"notice danger");notice.append(el("strong","检测到证据缺口"));gaps.forEach(gap=>notice.append(el("p",`${gap.id} · ${gap.role}：${gap.reason}`)));box.prepend(notice);}root.append(box);}
function renderResults(){const root=$("resultsContent");root.replaceChildren();const box=panel("对预期结果与最终结论的影响"),analysis=state.analysis;if(!analysis)box.append(el("p","初始版本尚无修改影响。"));else{(analysis.result_impacts||[]).forEach(item=>box.append(el("p",`• ${item}`)));box.append(el("h3","最终结论影响"),el("p",analysis.final_conclusion_impact));}root.append(box);}
function renderRisks(){const root=$("risksContent");root.replaceChildren();const analysis=state.analysis,box=panel("风险提示与系统建议"),status=state.status,errors=status.validation_errors||[],warnings=status.validation_warnings||[];if(analysis)box.append(el("p",`总体影响：${analysis.overall_impact_level} · ${analysis.impact_category}`,analysis.overall_impact_level));errors.forEach(item=>box.append(el("p",`错误：${item}`,"CRITICAL")));warnings.forEach(item=>box.append(el("p",`警告：${item}`,"MEDIUM")));(state.plan.risks||[]).forEach(item=>box.append(el("p",`方案风险：${compact(item)}`)));box.append(el("div","系统不会未经用户确认自动删除任务。删除核心证据、必要对照或关键方法时，最终决定仍由用户作出，但批准前必须解决格式与依赖错误。","notice"));root.append(box);}

function updateButtons(){const status=state.status.status;$("acceptEdit").disabled=!["IMPACT_ANALYSIS_READY","WAITING_FOR_USER_APPROVAL"].includes(status);$("rejectEdit").disabled=status!=="IMPACT_ANALYSIS_READY";$("approvePlan").disabled=status!=="WAITING_FOR_FINAL_APPROVAL";$("continueEdit").disabled=status==="APPROVED";$("restoreEdit").disabled=status==="APPROVED";$("saveDraft").disabled=status==="APPROVED";$("submitApproval").disabled=status==="APPROVED"||status==="WAITING_FOR_REVIEW_DECISION";}

async function loadState(options={}) {
  const response=await fetch("/api/state",{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"加载失败");state=data;
  $("statusBadge").textContent=`状态：${state.status.status}`;$("versionBadge").textContent=`版本：${state.status.current_candidate_version}`;$("riskBadge").textContent=`风险：${(state.analysis||{}).overall_impact_level||"—"}`;$("hashBadge").textContent=`哈希：${state.candidate_content_hash||"—"}`;
  if(!options.preserveEdits){baselinePlan=deepClone(state.plan);workingPlan=deepClone(state.plan);baselineUnknown=collectUnknown(baselinePlan);originalSuggestions=deepClone(state.plan.research_goal||{});dirty=false;}
  $("metaProject").textContent=workingPlan.project_id||"—";$("metaStage").textContent=workingPlan.stage??1;$("metaVersion").textContent=state.status.current_candidate_version;$("metaStatus").textContent=state.status.status;$("metaHash").textContent=state.candidate_content_hash||"—";$("metaUpdated").textContent=state.status.updated_at||workingPlan.generated_at||"—";$("editorTitle").textContent=`${state.status.current_candidate_version} · ${workingPlan.research_goal&&workingPlan.research_goal.research_object||"未命名方案"}`;
  $("draftStatus").textContent=state.draft?`草稿保存于 ${state.draft.saved_at}（未提交）`:"";
  renderCurrent();renderHistory();renderDiff();renderScience();renderWork();renderEvidence();renderResults();renderRisks();renderForm();updateButtons();markDirty();
}

async function post(url,payload,options={reload:true}) { const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}),data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||"操作失败");if(options.reload)await loadState();return data; }

async function backendCheck() { const data=await post("/api/check",{plan:workingPlan},{reload:false});return data.result; }
async function checkPlan(showToast=true) { const local=validateAndRender();let backend;try{backend=await backendCheck();}catch(error){toast(error.message,true);return {valid:false,errors:[{path:"server",message:error.message}],warnings:[]};}const errors=[...local.errors,...(backend.errors||[]).map(message=>({path:"schema",message}))],warnings=[...local.warnings,...(backend.warnings||[]).map(message=>({path:"schema",message}))];renderValidation({errors,warnings,completed:local.completed});if(showToast)toast(errors.length?`检查完成：发现 ${errors.length} 个阻塞问题。`:`检查通过；有 ${warnings.length} 项一般提醒。`,Boolean(errors.length));return {valid:!errors.length,errors,warnings,checkedPlan:backend.checked_plan}; }

async function saveDraft() { if(!$("jsonMode").classList.contains("hidden")&&!await applyJsonToModel({silent:true}))return;try{const result=await post("/api/draft",{plan:workingPlan},{reload:false});$("draftStatus").textContent=`草稿保存于 ${result.result.saved_at}（未提交；状态仍为 ${result.result.workflow_status}）`;toast("草稿已保存；未创建版本、未进入审批。 ");}catch(error){toast(error.message,true);} }

async function action(name){const reason=$("actionReason").value.trim(),payload={action:name,reason,version:$("restoreVersion").value,confirmed_by:"user"};try{await post("/api/action",payload);toast("工作流操作已完成。");}catch(error){toast(error.message,true);} }

async function startFinalReview() { try{const data=await post("/api/start-review",{},{reload:false});const result=data.result;toast(`哈希绑定审批已启动：${result.request_id||"请求生成中"} · ${result.content_hash||""}`);await loadState();}catch(error){toast(error.message,true);} }

async function submitApproval() {
  if(!$("jsonMode").classList.contains("hidden")&&!await applyJsonToModel({silent:true}))return;
  const check=await checkPlan(false);if(!check.valid){toast(`存在 ${check.errors.length} 个阻塞问题，不能提交审批。`,true);return;}
  if(dirty&&!$("editReason").value.trim()){const error=document.querySelector('[data-error-for="edit_reason"]');error.textContent="正式提交修改前必须填写本次修改理由。";$("editReason").focus();toast("请填写本次修改理由。",true);return;}
  renderSummary();if(!window.confirm("已生成方案摘要。确认将当前已校验内容提交版本化和哈希绑定网页审批？"))return;
  try{
    if(dirty){await post("/api/submit",{plan:workingPlan,reason:$("editReason").value.trim()});}
    if(["WAITING_FOR_USER_APPROVAL","IMPACT_ANALYSIS_READY"].includes(state.status.status))await post("/api/action",{action:"accept",reason:$("editReason").value.trim()||"User submitted reviewed candidate for final browser approval",confirmed_by:"user"});
    if(state.status.status!=="WAITING_FOR_FINAL_APPROVAL")throw new Error(`当前状态 ${state.status.status} 不能启动最终审批。`);
    await startFinalReview();
  }catch(error){toast(error.message,true);}
}

function reorder(list,index,direction){const target=index+direction;if(target<0||target>=list.length)return;[list[index],list[target]]=[list[target],list[index]];}
function dependentQuestions(id){return (workingPlan.scientific_questions||[]).filter(item=>currentQuestionDependencies(item)[1].map(String).includes(String(id)));}
function taskReferences(id){const refs=[];(workingPlan.tasks||[]).forEach(item=>{if((item.prerequisites||[]).map(String).includes(String(id))||(item.downstream_dependencies||[]).map(String).includes(String(id)))refs.push(`任务 ${item.id}`);});(workingPlan.evidence_chain||[]).forEach(item=>{if((item.task_ids||[]).map(String).includes(String(id)))refs.push(`证据 ${item.id}`);});return refs;}

function handleCardAction(kind,action,index){const key={question:"scientific_questions",task:"tasks",system:"systems",control:"controls",evidence:"evidence_chain",route:"execution_route"}[kind],list=workingPlan[key];if(!Array.isArray(list)||!list[index])return;
  if(action==="up"||action==="down")reorder(list,index,action==="up"?-1:1);
  if(action==="copy"){const copy=deepClone(list[index]);if(copy.id){const prefix={question:"SQ",task:"T",system:"S",control:"C",evidence:"E"}[kind];copy.id=nextId(list,prefix,kind==="task"?2:2);}list.splice(index+1,0,copy);}
  if(action==="delete"){
    if(kind==="question"){const refs=dependentQuestions(list[index].id);if(refs.length){toast(`不能删除：${refs.map(item=>`${item.id} ${itemSummary(item)}`).join("、")} 仍依赖该问题。请先重新设置依赖关系。`,true);return;}}
    if(kind==="task"){const refs=taskReferences(list[index].id);if(refs.length){toast(`不能删除：${refs.join("、")} 仍引用该任务。请先处理依赖和证据链。`,true);return;}}
    if(!window.confirm(`确认删除“${itemSummary(list[index])}”？内部历史版本不会被覆盖。`))return;list.splice(index,1);
  }
  renderForm();markDirty();
}

function addTemplate(kind){
  if(kind==="question"){workingPlan.scientific_questions ||= [];workingPlan.scientific_questions.push({id:nextId(workingPlan.scientific_questions,"SQ"),question:"",evidence_target:"",dependencies:[]});}
  if(kind==="task"){workingPlan.tasks ||= [];workingPlan.tasks.push({id:nextId(workingPlan.tasks,"T"),name:"新任务",scientific_question_id:"",systems:[],controls:[],software:"",module:"",method:"",target_parameters:[],target_data_forms:[],scientific_meaning:"",supported_conclusions:[],experimental_correspondence:[],corroborates_with:[],prerequisites:[],downstream_dependencies:[],evidence_role:"",scientific_weight:{I:0,U:0,S:0,N:0,rationale:{I:"待评估",U:"待评估",S:"待评估",N:"待评估"}},workload_weight:{M:0,C:0,K:0,P:0,H:0,rationale:{M:"待评估",C:"待评估",K:"待评估",P:"待评估",H:"待评估"}},result_sensitivity:"",irreplaceability:"",priority:"foundation",necessity:"necessary",alternatives:[],redundancy:"待审查",status:"proposed",user_notes:""});}
  if(kind==="system"){workingPlan.systems ||= [];workingPlan.systems.push({id:nextId(workingPlan.systems,"S"),name:"",role:"",description:""});}
  if(kind==="control"){workingPlan.controls ||= [];workingPlan.controls.push({id:nextId(workingPlan.controls,"C"),name:"",isolates:"",consistency_requirements:""});}
  if(kind==="evidence"){workingPlan.evidence_chain ||= [];workingPlan.evidence_chain.push({id:nextId(workingPlan.evidence_chain,"E"),role:"",task_ids:[],supports:"",required:false});}
  if(kind==="route"){workingPlan.execution_route ||= [];workingPlan.execution_route.push({order:workingPlan.execution_route.length+1,action:"",gate:""});}
  renderForm();markDirty();
}

function updateArrayCheckbox(input){const path=input.dataset.arrayPath,current=getPath(workingPlan,path),values=Array.isArray(current)?current:[];const id=String(input.dataset.value),filtered=values.filter(value=>String(value)!==id);if(input.checked)filtered.push(input.dataset.value);setPath(workingPlan,path,filtered);}

function openHelper(type,mode){const help=HELP[type];if(!help)return;$("helperTitle").textContent=mode==="explain"?`解释：${help.title}`:`示例：${help.title}`;const root=$("helperContent");root.replaceChildren();if(mode==="explain")root.append(el("p",help.explanation));else{const good=el("div",null,"notice");good.append(el("strong","合理示例"),el("p",help.good));const bad=el("div",null,"notice danger");bad.append(el("strong","常见错误"),el("p",help.bad));root.append(good,bad);}$("helperDialog").showModal();}
function suggestionFor(type){const help=HELP[type],goal=workingPlan.research_goal||{};if(!help)return "";if(type==="core_question")return goal.research_object?`在统一模型、理论方法和收敛标准下，${goal.comparison_object||"拟比较变量"}是否会显著改变与${goal.research_object}相关的目标指标？`:help.good;if(type==="target_conclusion")return `判断批准的比较变量是否在预设精度和证据范围内产生可辨别差异，并明确结果仅支持哪些结论。`;return help.good;}
function applySuggestion(type){const key=type,field=document.querySelector(`[data-path="research_goal.${key}"]`);if(!field)return;field.value=suggestionFor(type);field.dispatchEvent(new Event("input",{bubbles:true}));field.dataset.suggested="true";toast("建议内容已填入输入框，请审核修改；不会自动保存或批准。 ");}
function restoreSuggestion(type){const field=document.querySelector(`[data-path="research_goal.${type}"]`);if(!field)return;field.value=originalSuggestions[type]??"";field.dispatchEvent(new Event("input",{bubbles:true}));toast("已恢复首次加载时的内容。");}

function openProtectedDialog(){const select=$("protectedPath");select.replaceChildren();[["project_id",workingPlan.project_id],...flattenProtected(workingPlan.protected_records||{})].forEach(([path,value])=>{const option=el("option",path);option.value=path;option.dataset.value=JSON.stringify(value);select.append(option);});updateProtectedDialog();$("protectedReason").value="";$("protectedActor").value="user";$("protectedError").textContent="";$("protectedDialog").showModal();}
function updateProtectedDialog(){const path=$("protectedPath").value,value=getPath(workingPlan,path);$("protectedOldValue").value=compact(value);$("protectedNewValue").value=typeof value==="string"?value:JSON.stringify(value,null,2);$("protectedImpact").textContent=path==="project_id"?"项目标识变化会影响所有版本、注册表、证据链和审批追踪；必须确保外部引用同步。":"来源、软件版本或校验记录变化可能影响任务可复现性、结果可比性和审批内容哈希。";}
function submitProtected(event){event.preventDefault();const path=$("protectedPath").value,oldValue=deepClone(getPath(workingPlan,path)),raw=$("protectedNewValue").value,reason=$("protectedReason").value.trim();if(!reason){$("protectedError").textContent="修改理由不能为空。";return;}let newValue=raw;if(typeof oldValue!=="string"){try{newValue=JSON.parse(raw);}catch(error){$("protectedError").textContent=`拟修改值与原字段类型不匹配：${error.message}`;return;}}setPath(workingPlan,path,newValue);workingPlan.manual_overrides ||= [];workingPlan.manual_overrides.push({path,old_value:oldValue,new_value:deepClone(newValue),reason,modified_at:new Date().toISOString(),actor:$("protectedActor").value.trim()||"user",stage:workingPlan.stage??1,manual_override:true});$("protectedDialog").close();renderForm();markDirty();toast("受保护字段已修改，并自动生成 manual_overrides 记录。 ");}

function wireEvents(){
  $("tabs").addEventListener("click",event=>{if(event.target.tagName!=="BUTTON")return;document.querySelectorAll("nav button").forEach(node=>node.classList.remove("active"));document.querySelectorAll(".view").forEach(node=>node.classList.remove("active"));event.target.classList.add("active");$(event.target.dataset.view).classList.add("active");});
  $("formMode").addEventListener("input",event=>{const input=event.target;if(input.dataset.path)setPath(workingPlan,input.dataset.path,input.value,{deleteWhenEmpty:input.dataset.path==="research_goal.research_boundaries"});if(input.dataset.listPath)setPath(workingPlan,input.dataset.listPath,lines(input.value));if(input.dataset.numberPath)setPath(workingPlan,input.dataset.numberPath,input.value===""?null:Number(input.value));if(input.id==="assumptionsEditor")workingPlan.assumptions=lines(input.value);if(input.id==="risksEditor")workingPlan.risks=lines(input.value);markDirty();});
  $("formMode").addEventListener("change",event=>{const input=event.target;if(input.dataset.arrayPath)updateArrayCheckbox(input);if(input.dataset.booleanPath)setPath(workingPlan,input.dataset.booleanPath,input.checked);if(input.dataset.arrayPath||input.dataset.booleanPath)markDirty();});
  $("formMode").addEventListener("click",event=>{const button=event.target.closest("button");if(!button)return;if(button.dataset.cardAction)handleCardAction(button.dataset.cardKind,button.dataset.cardAction,Number(button.dataset.index));if(button.dataset.addAlternative!==undefined){const index=Number(button.dataset.addAlternative);workingPlan.tasks[index].alternatives ||= [];workingPlan.tasks[index].alternatives.push({condition:"",method:"",scientific_impact:"",workload_impact:"",risk:"",notes:""});renderTasks();markDirty();}if(button.dataset.removeAlternative){const [taskIndex,altIndex]=button.dataset.removeAlternative.split(":").map(Number);workingPlan.tasks[taskIndex].alternatives.splice(altIndex,1);renderTasks();markDirty();}if(button.dataset.help)openHelper(button.dataset.help,"explain");if(button.dataset.example)openHelper(button.dataset.example,"example");if(button.dataset.suggest)applySuggestion(button.dataset.suggest);if(button.dataset.restore)restoreSuggestion(button.dataset.restore);});
  $("experimentMode").addEventListener("change",()=>{const mode=$("experimentMode").value,input=$("goalExperiment");input.classList.toggle("hidden",mode!=="provided");if(mode==="not_provided")setPath(workingPlan,"research_goal.experimental_phenomenon","未提供实验现象");if(mode==="not_applicable")setPath(workingPlan,"research_goal.experimental_phenomenon","不适用：本任务不涉及实验现象");if(mode==="provided"&&/^(未提供|不适用|本任务不涉及)/.test(String(getPath(workingPlan,"research_goal.experimental_phenomenon")||""))){setPath(workingPlan,"research_goal.experimental_phenomenon","");input.value="";}markDirty();});
  [["addQuestion","question"],["addTask","task"],["addSystem","system"],["addControl","control"],["addEvidence","evidence"],["addRoute","route"]].forEach(([id,kind])=>$(id).addEventListener("click",()=>addTemplate(kind)));
  $("formModeButton").onclick=()=>{if(!$("jsonMode").classList.contains("hidden"))switchToForm();};$("jsonModeButton").onclick=switchToJson;$("returnForm").onclick=switchToForm;$("openJsonFromUnknown").onclick=switchToJson;
  $("planEditor").addEventListener("input",()=>{updateJsonPresentation();window.clearTimeout(jsonSnapshotTimer);jsonSnapshotTimer=window.setTimeout(()=>{const text=$("planEditor").value;if(jsonUndo[jsonUndo.length-1]!==text){jsonUndo.push(text);if(jsonUndo.length>80)jsonUndo.shift();jsonRedo=[];}},300);});
  $("planEditor").addEventListener("keyup",updateCursorStatus);$("planEditor").addEventListener("click",updateCursorStatus);$("planEditor").addEventListener("scroll",()=>{$("jsonLineNumbers").scrollTop=$("planEditor").scrollTop;});
  $("formatJson").onclick=()=>{try{$("planEditor").value=JSON.stringify(JSON.parse($("planEditor").value),null,2);updateJsonPresentation();showJsonMessages();}catch(error){const pos=syntaxPosition($("planEditor").value,error);showJsonMessages([{path:`第 ${pos.line} 行，第 ${pos.column} 列`,message:error.message}]);}};
  $("undoJson").onclick=()=>{if(jsonUndo.length<2)return;jsonRedo.push(jsonUndo.pop());$("planEditor").value=jsonUndo[jsonUndo.length-1];updateJsonPresentation();};$("redoJson").onclick=()=>{if(!jsonRedo.length)return;const value=jsonRedo.pop();jsonUndo.push(value);$("planEditor").value=value;updateJsonPresentation();};$("validateJson").onclick=()=>applyJsonToModel({silent:true});$("applyJson").onclick=()=>applyJsonToModel();$("previewJson").onclick=async()=>{if(await applyJsonToModel({silent:true}))renderSummary();};$("restoreJson").onclick=()=>{$("planEditor").value=lastValidJsonText||JSON.stringify(workingPlan,null,2);updateJsonPresentation();showJsonMessages();};
  $("saveDraft").onclick=saveDraft;$("checkPlan").onclick=()=>checkPlan();$("viewSummary").onclick=renderSummary;$("submitApproval").onclick=submitApproval;
  $("acceptEdit").onclick=()=>action("accept");$("continueEdit").onclick=()=>action("continue");$("restoreEdit").onclick=()=>action("restore");$("rejectEdit").onclick=()=>action("reject");$("approvePlan").onclick=startFinalReview;
  $("openProtectedDialog").onclick=openProtectedDialog;$("protectedPath").onchange=updateProtectedDialog;$("protectedForm").onsubmit=submitProtected;$("closeProtectedDialog").onclick=()=>$("protectedDialog").close();$("cancelProtectedDialog").onclick=()=>$("protectedDialog").close();
}

window.__stage1EditorTest = {
  getWorkingPlan:()=>deepClone(workingPlan), getBaselinePlan:()=>deepClone(baselinePlan), validatePlan, naturalDiff, technicalDiff,
  setWorkingPlan:value=>{workingPlan=deepClone(value);renderForm();markDirty();}, applyJsonText:async text=>{$("planEditor").value=text;return applyJsonToModel({silent:true});},
  switchToJson, switchToForm, saveDraft, checkPlan, renderSummary, collectUnknown:plan=>Object.fromEntries(collectUnknown(plan)),
};

wireEvents();
loadState().catch(error=>toast(`无法加载审查数据：${error.message}`,true));
