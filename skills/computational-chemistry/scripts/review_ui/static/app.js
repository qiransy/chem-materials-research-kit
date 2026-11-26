"use strict";

let activeRequest = null;
let submitting = false;

const byId = (id) => document.getElementById(id);

function setMessage(text, kind = "") {
  const element = byId("message");
  element.textContent = text;
  element.className = `message ${kind}`.trim();
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll("button[data-decision]").forEach((button) => {
    button.disabled = disabled;
  });
}

async function loadRequest() {
  try {
    const response = await fetch("/api/review-request", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "无法读取审查请求。");
    }
    activeRequest = payload;
    byId("review-title").textContent = payload.title;
    byId("stage").textContent = payload.stage;
    byId("request-id").textContent = payload.request_id;
    byId("content-file").textContent = payload.content_file;
    byId("created-at").textContent = payload.created_at;
    byId("content-hash").textContent = payload.content_hash;
    byId("review-content").textContent = payload.content;
    byId("request-status").textContent = payload.status;
    setMessage("请核对完整内容及哈希后作出决定。", "info");
  } catch (error) {
    setButtonsDisabled(true);
    setMessage(`读取失败：${error.message}`, "error");
  }
}

async function submitDecision(decision) {
  if (!activeRequest || submitting) {
    return;
  }
  submitting = true;
  setButtonsDisabled(true);
  setMessage("正在提交并校验审批结果…", "info");
  try {
    const response = await fetch("/api/review-decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: activeRequest.request_id,
        stage: activeRequest.stage,
        content_hash: activeRequest.content_hash,
        decision,
        comment: byId("comment").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "审批提交失败。");
    }
    byId("request-status").textContent = "confirmed";
    setMessage("审批结果已确认并写入。此页面可以关闭。", "success");
    window.setTimeout(() => window.close(), 700);
  } catch (error) {
    submitting = false;
    setButtonsDisabled(false);
    setMessage(`提交失败：${error.message}`, "error");
  }
}

document.querySelectorAll("button[data-decision]").forEach((button) => {
  button.addEventListener("click", () => submitDecision(button.dataset.decision));
});

loadRequest();
