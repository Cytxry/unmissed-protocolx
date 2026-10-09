const SAMPLE = `[2026-10-09 10:15] Maya: I’ll send the revised budget by Thursday.
[2026-10-09 10:17] Dev: The planning sync is Friday at 3 PM. @Maya, could you prepare the updated deck by Thursday?
[2026-10-09 10:18] Maya: Agreed, the smaller venue works. I’ll update the budget with the $2,000 catering cap.
[2026-10-09 10:20] Lee: I can confirm the venue booking once the revised budget is ready.
[2026-10-09 10:22] Dev: Decision: we’re going with the smaller venue and the $2,000 catering cap.`;

const $ = (id) => document.getElementById(id);
const transcript = $('transcript');
const analyzeButton = $('analyze-button');
const notice = $('notice');
let activeTab = 'paste';
let analysisJobId = '';
let analysisJob = null;
let pollTimer = null;
let startTime = 0;
let questionTimer = null;
let questionStartTime = 0;
let quickQuestions = [];
const PHONE_NUMBER_PATTERN = /(^|[^\w])((?:\+\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]){1,3}\d{3,4}|\+?\d{7,15})(?![\w])/g;

function maskPhoneNumbers(value) {
  return String(value ?? '').replace(PHONE_NUMBER_PATTERN, (_match, prefix) => `${prefix}[phone number]`);
}

function setNotice(message, kind = '') {
  notice.textContent = maskPhoneNumbers(message);
  notice.className = `notice ${kind}`;
  notice.classList.remove('hidden');
}
function clearNotice() { notice.classList.add('hidden'); }
function currentText() { return activeTab === 'paste' ? transcript.value : transcript.dataset.fileText || ''; }
function updateAnalyzeButton() { analyzeButton.disabled = !currentText().trim() || !$('model-select').value; }
function updateAskButton() { $('ask-button').disabled = !$('custom-question').value.trim() || Boolean(questionTimer); }
function clockText(seconds) { return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`; }

document.querySelectorAll('.source-tab').forEach((tab) => tab.addEventListener('click', () => {
  activeTab = tab.id === 'paste-tab' ? 'paste' : 'file';
  document.querySelectorAll('.source-tab').forEach((el) => {
    const active = el === tab;
    el.classList.toggle('active', active);
    el.setAttribute('aria-selected', String(active));
  });
  $('paste-panel').classList.toggle('hidden', activeTab !== 'paste');
  $('file-panel').classList.toggle('hidden', activeTab !== 'file');
  clearNotice();
  updateAnalyzeButton();
}));
document.querySelectorAll('.source-tab').forEach((tab, index, tabs) => tab.addEventListener('keydown', (event) => {
  let nextIndex = index;
  if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
  else if (event.key === 'ArrowLeft') nextIndex = (index + tabs.length - 1) % tabs.length;
  else if (event.key === 'Home') nextIndex = 0;
  else if (event.key === 'End') nextIndex = tabs.length - 1;
  else return;
  event.preventDefault();
  tabs[nextIndex].focus();
  tabs[nextIndex].click();
}));

transcript.addEventListener('input', () => {
  $('char-count').textContent = `${transcript.value.length.toLocaleString()} characters`;
  updateAnalyzeButton();
});
$('sample-button').addEventListener('click', () => {
  transcript.value = SAMPLE;
  $('char-count').textContent = `${SAMPLE.length.toLocaleString()} characters`;
  $('paste-tab').click();
  updateAnalyzeButton();
});

async function readFile(file) {
  clearNotice();
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.txt') && file.type !== 'text/plain') {
    setNotice('Unsupported file type. Choose a plain-text .txt transcript.', 'error');
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    setNotice('This file is larger than 20 MB. Split it into smaller .txt files.', 'error');
    return;
  }
  try {
    const text = await file.text();
    if (!text.trim()) {
      setNotice('This file is empty. Choose another transcript.', 'error');
      return;
    }
    transcript.dataset.fileText = text;
    $('file-name').textContent = maskPhoneNumbers(`${file.name} · ${text.length.toLocaleString()} characters`);
    $('file-name').classList.remove('hidden');
    updateAnalyzeButton();
  } catch (error) {
    setNotice(`Couldn't read that file: ${error.message}`, 'error');
  }
}
$('file-input').addEventListener('change', (event) => readFile(event.target.files[0]));
const dropzone = $('dropzone');
['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => {
  event.preventDefault(); dropzone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => {
  event.preventDefault(); dropzone.classList.remove('dragging');
}));
dropzone.addEventListener('drop', (event) => readFile(event.dataTransfer.files[0]));

async function refreshStatus() {
  const dot = $('status-dot');
  const label = $('status-text');
  const modelLabel = $('local-model-label');
  try {
    const response = await fetch('/api/status');
    const status = await response.json();
    const select = $('model-select');
    select.replaceChildren();
    quickQuestions = status.quickQuestions || [];
    const defaultModel = status.defaultModel || 'qwen2.5:3b';
    const modelDisplay = defaultModel.toLowerCase() === 'qwen2.5:3b' ? 'Qwen2.5 3B' : defaultModel;
    const modelReady = Boolean(status.ollama && status.models?.includes(defaultModel));
      if (!status.ollama) {
      dot.className = 'status-dot offline';
      label.textContent = 'Ollama unavailable';
      modelLabel.textContent = `${modelDisplay} · unavailable`;
      select.add(new Option(`${modelDisplay} unavailable`, ''));
        setNotice(status.endpointError || `Ollama isn't responding at ${status.url}. Start Ollama, then try again.`, 'error');
        $('offline-live-status').textContent = 'Live check: Ollama is unavailable; analysis is disabled until it responds.';
      } else if (!modelReady) {
      dot.className = 'status-dot offline';
      label.textContent = `${modelDisplay} not installed`;
      modelLabel.textContent = `${modelDisplay} · not installed`;
      select.add(new Option(`${modelDisplay} unavailable`, ''));
        setNotice(`Ollama is running, but ${defaultModel} is not installed. Run “ollama pull ${defaultModel}”, then reload this page.`, 'error');
        $('offline-live-status').textContent = `Live check: Ollama responds, but ${defaultModel} is not installed; analysis is disabled.`;
      } else {
      dot.className = 'status-dot online';
      label.textContent = `${modelDisplay} ready`;
      modelLabel.textContent = `${modelDisplay} · on this device`;
        select.add(new Option(defaultModel, defaultModel, true, true));
        $('offline-live-status').textContent = `Live check: ${defaultModel} is installed and responding locally. This does not verify disconnected-network operation.`;
      if (notice.classList.contains('error') && /Ollama|qwen2\.5/i.test(notice.textContent)) clearNotice();
    }
  } catch {
    dot.className = 'status-dot offline';
    label.textContent = 'Local model status unavailable';
    modelLabel.textContent = 'Qwen2.5 3B · status unavailable';
    $('model-select').replaceChildren(new Option('Ollama status unavailable', ''));
    $('offline-live-status').textContent = 'Live check unavailable; local inference readiness could not be verified.';
  }
  updateAnalyzeButton();
}
$('model-select').addEventListener('change', updateAnalyzeButton);

function updateAnalysisProgress(job) {
  $('progress').classList.remove('hidden');
  $('progress-message').textContent = maskPhoneNumbers(job.message || 'Preparing your catch-up…');
  const seconds = Math.floor((Date.now() - startTime) / 1000);
  $('progress-time').textContent = clockText(seconds);
  const total = Math.max(1, Number(job.total) || 1);
  $('progress-fill').style.width = `${Math.min(96, Math.max(6, Math.round((job.completed || 0) / total * 100)))}%`;
  $('progress-hint').textContent = seconds > 25
    ? 'The local model is still working. Long conversations can take a few minutes; keep this tab open.'
    : 'Reviewing updates and linking each finding back to its original messages.';
}

async function fetchJob(jobId) {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  const job = await response.json();
  if (!response.ok) throw new Error(job.error || 'Could not read the job status.');
  return job;
}

async function pollAnalysis() {
  try {
    const job = await fetchJob(analysisJobId);
    updateAnalysisProgress(job);
    if (job.state === 'done') {
      clearInterval(pollTimer); pollTimer = null;
      analysisJob = job;
      analyzeButton.disabled = false;
      $('progress').classList.add('hidden');
      renderDashboard(job);
    } else if (job.state === 'error') {
      clearInterval(pollTimer); pollTimer = null;
      analyzeButton.disabled = false;
      $('progress').classList.add('hidden');
      setNotice(job.message || 'Analysis failed. Check that Ollama and the selected model are available.', 'error');
    }
  } catch (error) {
    clearInterval(pollTimer); pollTimer = null;
    analyzeButton.disabled = false;
    $('progress').classList.add('hidden');
    setNotice(error.message, 'error');
  }
}

analyzeButton.addEventListener('click', async () => {
  clearNotice();
  $('results').classList.add('hidden');
  analyzeButton.disabled = true;
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: currentText(), model: $('model-select').value, userName: $('user-name').value.trim()})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not start analysis.');
    analysisJobId = data.jobId;
    startTime = Date.now();
    updateAnalysisProgress({message: 'Preparing your conversation…'});
    pollTimer = setInterval(pollAnalysis, 700);
    pollAnalysis();
  } catch (error) {
    analyzeButton.disabled = false;
    setNotice(error.message, 'error');
  }
});

function statPill(label, value) {
  const pill = document.createElement('span');
  pill.className = 'stat-pill';
  const count = document.createElement('strong'); count.textContent = String(value);
  const text = document.createElement('span'); text.textContent = label;
  pill.append(count, text);
  return pill;
}

function renderDashboard(job) {
  const messages = job.messages || [];
  const findings = job.findings || [];
  const coverage = job.coverage || null;
  $('summary-text').textContent = maskPhoneNumbers(job.summary || 'The local model did not return a concise summary for this conversation.');
  $('result-model').textContent = maskPhoneNumbers(job.model || '');
  const coverageLabel = coverage && !coverage.analysisComplete
    ? ` · Partial analysis (${coverage.analyzedChunks}/${coverage.totalChunks} sections)`
    : coverage && !coverage.synthesisComplete ? ' · Cross-section synthesis incomplete' : '';
  $('result-count').textContent = `${messages.length} messages · ${findings.length} findings${coverageLabel}`;
  $('message-count').textContent = `${messages.length} messages`;
  $('analysis-disclosure').textContent = maskPhoneNumbers(`${job.model} · Local Ollama analysis · ${job.chunks} ${job.chunks === 1 ? 'chunk' : 'chunks'}`);

  const categories = [
    ['action', 'Action items'], ['decision', 'Decisions'], ['meeting', 'Meetings'],
    ['mention', 'Mentions'], ['other_update', 'Other updates'], ['unanswered', 'Unanswered'], ['moment', 'Notable moments']
  ];
  const stats = $('summary-stats'); stats.replaceChildren();
  categories.forEach(([category, label]) => {
    const count = findings.filter((finding) => finding.category === category).length;
    if (count) stats.append(statPill(label, count));
  });

  const count = (category) => findings.filter((finding) => category === 'mention_request'
    ? ['mention', 'unanswered'].includes(finding.category)
    : category === 'all' ? true : finding.category === category).length;
  [['action', 'nav-action-count'], ['decision', 'nav-decision-count'], ['meeting', 'nav-meeting-count'],
    ['mention_request', 'nav-mention-count'], ['other_update', 'nav-other-count'], ['all', 'nav-all-count']]
    .forEach(([category, id]) => { $(id).textContent = String(count(category)); });

  const attentionFindings = findings.filter((finding) => finding.priority?.level === 'high');
  $('attention-section').classList.toggle('hidden', attentionFindings.length === 0);
  $('attention-nav').classList.toggle('hidden', attentionFindings.length === 0);
  $('attention-count').textContent = attentionFindings.length ? `${attentionFindings.length} HIGH PRIORITY` : '';
  $('nav-attention-count').textContent = attentionFindings.length ? String(attentionFindings.length) : '';
  renderFindingCards($('attention-list'), attentionFindings);

  const warning = $('parse-warning');
  if (job.warnings?.length) {
    warning.textContent = maskPhoneNumbers(job.warnings.join(' '));
    warning.classList.remove('hidden');
  } else {
    warning.textContent = '';
    warning.classList.add('hidden');
  }

  renderMessages(messages);
  renderQuickQuestions();
  $('finding-filter').value = 'all';
  document.querySelectorAll('.results-nav-link').forEach((link) => link.classList.toggle('active', link.dataset.filter === 'all' || link.dataset.section === 'overview'));
  renderFindings(findings);
  $('answer-card').classList.add('hidden');
  $('custom-question').value = '';
  updateAskButton();
  $('results').classList.remove('hidden');
  $('results').scrollIntoView({behavior: 'smooth', block: 'start'});
}

function renderMessages(messages) {
  const list = $('messages'); list.replaceChildren();
  messages.forEach((message) => {
    const card = document.createElement('article');
    card.className = 'message'; card.id = `source-${message.id}`; card.tabIndex = -1;
    const meta = document.createElement('div'); meta.className = 'message-meta';
    const sender = document.createElement('span'); sender.className = 'message-sender'; sender.textContent = maskPhoneNumbers(message.sender);
    const timestamp = document.createElement('span'); timestamp.className = 'message-time'; timestamp.textContent = maskPhoneNumbers(message.timestamp);
    const body = document.createElement('div'); body.className = 'message-body'; body.textContent = maskPhoneNumbers(message.text);
    meta.append(sender, timestamp); card.append(meta, body); list.append(card);
  });
}

function revealEvidence(ids) {
  const valid = (ids || []).filter((id) => document.getElementById(`source-${id}`));
  if (!valid.length) return;
  document.querySelectorAll('.message.highlight').forEach((message) => message.classList.remove('highlight'));
  valid.forEach((id) => document.getElementById(`source-${id}`).classList.add('highlight'));
  const target = document.getElementById(`source-${valid[0]}`);
  target.scrollIntoView({behavior: 'smooth', block: 'center'});
  target.focus({preventScroll: true});
}

function categoryLabel(category) {
  return ({action: 'Action item', meeting: 'Meeting', decision: 'Decision', mention: 'Direct mention', unanswered: 'Unanswered request', moment: 'Notable moment', other_update: 'Other update'})[category] || 'Other update';
}

function renderFindings(allFindings) {
  const filter = $('finding-filter').value;
  const container = $('finding-list'); container.replaceChildren();
  let findings = allFindings.filter((finding) => filter === 'all'
    || (filter === 'mention_request' ? ['mention', 'unanswered'].includes(finding.category) : finding.category === filter));
  findings = findings.slice().sort((a, b) => {
    const priority = (b.priority?.score || 0) - (a.priority?.score || 0);
    if (priority) return priority;
    const confidence = {high: 0, medium: 1, low: 2};
    return (confidence[a.confidence] ?? 1) - (confidence[b.confidence] ?? 1);
  });
  $('empty-filter').classList.toggle('hidden', findings.length !== 0);
  renderFindingCards(container, findings);
}

function renderFindingCards(container, findings) {
  container.replaceChildren();
  findings.forEach((finding) => {
    const card = document.createElement('article'); card.className = 'finding';
    const header = document.createElement('div'); header.className = 'finding-header';
    const main = document.createElement('div'); main.className = 'finding-main';
    const title = document.createElement('button'); title.type = 'button'; title.className = 'finding-title-button'; title.textContent = maskPhoneNumbers(finding.title);
    title.setAttribute('aria-label', `Show source for ${maskPhoneNumbers(finding.title)}`);
    title.addEventListener('click', () => revealEvidence(finding.evidence));
    main.append(title);
    const pill = document.createElement('span'); pill.className = `category-pill category-${finding.category}`; pill.textContent = categoryLabel(finding.category);
    header.append(main, pill);
    const meta = document.createElement('div'); meta.className = 'finding-meta';
    if (finding.priority) {
      const priority = document.createElement('span'); priority.className = `priority-pill priority-${finding.priority.level}`;
      priority.textContent = `${finding.priority.level} priority`;
      priority.title = maskPhoneNumbers((finding.priority.reasons || []).join(' · '));
      meta.append(priority);
      if (finding.priority.reasons?.length) {
        const reason = document.createElement('span'); reason.className = 'priority-reason';
        reason.textContent = maskPhoneNumbers(finding.priority.reasons.join(' · '));
        meta.append(reason);
      }
    }
    if (finding.owner) { const owner = document.createElement('span'); owner.textContent = maskPhoneNumbers(`Owner · ${finding.owner}`); meta.append(owner); }
    if (finding.due) { const due = document.createElement('span'); due.textContent = maskPhoneNumbers(`Due · ${finding.due}`); meta.append(due); }
    if (finding.when) { const when = document.createElement('span'); when.textContent = maskPhoneNumbers(finding.when); meta.append(when); }
    if (finding.confidence === 'low') { const caution = document.createElement('span'); caution.className = 'confidence-note'; caution.textContent = 'Needs a source check'; meta.append(caution); }
    const evidence = document.createElement('button'); evidence.type = 'button'; evidence.className = 'evidence-button';
    evidence.textContent = `${finding.evidence.length} ${finding.evidence.length === 1 ? 'source message' : 'source messages'} ↗`;
    evidence.addEventListener('click', () => revealEvidence(finding.evidence));
    meta.append(evidence);
    card.append(header);
    if (finding.detail) { const detail = document.createElement('p'); detail.className = 'finding-detail'; detail.textContent = maskPhoneNumbers(finding.detail); card.append(detail); }
    card.append(meta);
    if (finding.conflict) {
      const conflict = document.createElement('div'); conflict.className = 'conflict-note';
      conflict.textContent = maskPhoneNumbers(finding.conflictNote || 'These messages may conflict or reflect a change. Check the original context.');
      card.append(conflict);
      if (finding.conflictEvidence?.length) {
        const conflictLink = document.createElement('button'); conflictLink.type = 'button'; conflictLink.className = 'evidence-button';
        conflictLink.textContent = 'View both messages ↗';
        conflictLink.addEventListener('click', () => revealEvidence([...finding.evidence, ...finding.conflictEvidence]));
        card.append(conflictLink);
      }
    }
    container.append(card);
  });
}

$('finding-filter').addEventListener('change', () => renderFindings(analysisJob?.findings || []));

document.querySelectorAll('.results-nav-link').forEach((link) => link.addEventListener('click', (event) => {
  document.querySelectorAll('.results-nav-link').forEach((item) => item.classList.remove('active'));
  link.classList.add('active');
  if (link.dataset.filter) {
    $('finding-filter').value = link.dataset.filter;
    renderFindings(analysisJob?.findings || []);
    $('feed-title').scrollIntoView({behavior: 'smooth', block: 'start'});
  } else if (link.dataset.section) {
    const target = document.getElementById(link.getAttribute('href').slice(1));
    target?.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
}));

function renderQuickQuestions() {
  const container = $('quick-questions'); container.replaceChildren();
  quickQuestions.forEach((question) => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'question-chip';
    button.textContent = question.label;
    button.addEventListener('click', () => startQuestion(question.question));
    container.append(button);
  });
}

$('custom-question').addEventListener('input', updateAskButton);
$('custom-question-form').addEventListener('submit', (event) => {
  event.preventDefault();
  startQuestion($('custom-question').value.trim());
});
$('close-answer').addEventListener('click', () => $('answer-card').classList.add('hidden'));

function updateAnswerProgress(job) {
  $('answer-progress').classList.remove('hidden');
  $('answer-progress-message').textContent = maskPhoneNumbers(job.message || 'Checking the conversation…');
  const seconds = Math.floor((Date.now() - questionStartTime) / 1000);
  $('answer-progress-time').textContent = clockText(seconds);
}

async function pollQuestion(jobId) {
  try {
    const job = await fetchJob(jobId);
    updateAnswerProgress(job);
    if (job.state === 'done') {
      clearInterval(questionTimer); questionTimer = null;
      $('answer-progress').classList.add('hidden');
      $('answer-text').textContent = maskPhoneNumbers(job.answer);
      $('answer-confidence').textContent = `${job.confidence || 'medium'} confidence`;
      $('answer-confidence').classList.toggle('low', job.confidence === 'low');
      const answerWarning = $('answer-warning');
      answerWarning.textContent = maskPhoneNumbers((job.warnings || []).join(' '));
      answerWarning.classList.toggle('hidden', !job.warnings?.length);
      const evidence = $('answer-evidence'); evidence.replaceChildren();
      (job.evidence || []).forEach((id) => {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'evidence-button';
        const source = (analysisJob?.messages || []).find((message) => message.id === id);
        const citation = source ? `${maskPhoneNumbers(source.sender)}${source.timestamp ? ` · ${maskPhoneNumbers(source.timestamp)}` : ''}` : id;
        button.textContent = `View ${citation} ↗`; button.addEventListener('click', () => revealEvidence([id]));
        evidence.append(button);
      });
      $('answer-card').classList.remove('hidden');
      unlockQuestionControls();
      updateAskButton();
    } else if (job.state === 'error') {
      clearInterval(questionTimer); questionTimer = null;
      $('answer-progress').classList.add('hidden');
      $('answer-text').textContent = maskPhoneNumbers(job.message || 'The local model could not answer this question.');
      $('answer-confidence').textContent = 'Not answered';
      $('answer-confidence').classList.add('low');
      $('answer-evidence').replaceChildren();
      $('answer-warning').classList.add('hidden');
      $('answer-card').classList.remove('hidden');
      unlockQuestionControls();
      updateAskButton();
    }
  } catch (error) {
    clearInterval(questionTimer); questionTimer = null;
    $('answer-progress').classList.add('hidden');
    setNotice(error.message, 'error');
    unlockQuestionControls();
    updateAskButton();
  }
}

async function startQuestion(question) {
  if (!analysisJobId || !question || questionTimer) return;
  clearNotice();
  $('answer-card').classList.add('hidden');
  document.querySelectorAll('.question-chip').forEach((button) => { button.disabled = true; });
  $('ask-button').disabled = true;
  $('custom-question').disabled = true;
  try {
    const response = await fetch('/api/ask', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({jobId: analysisJobId, question})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not start that question.');
    questionStartTime = Date.now();
    updateAnswerProgress({message: 'Checking the conversation against your question…'});
    questionTimer = setInterval(() => pollQuestion(data.jobId), 750);
    pollQuestion(data.jobId);
  } catch (error) {
    $('answer-progress').classList.add('hidden');
    setNotice(error.message, 'error');
    document.querySelectorAll('.question-chip').forEach((button) => { button.disabled = false; });
    $('custom-question').disabled = false;
    updateAskButton();
  }
}

function unlockQuestionControls() {
  document.querySelectorAll('.question-chip').forEach((button) => { button.disabled = false; });
  $('custom-question').disabled = false;
}

refreshStatus();
