import { useEffect, useMemo, useRef, useState } from 'react';
import MainLayout from '../layouts/MainLayout';
import {
  Button,
  DisabledBlock,
  EmptyState,
  LoadingPlaceholder,
  MaterialShelf,
  ModalShell,
  StatusPill,
  Stepper,
  SyllabusSwitcher,
  WeekAxis,
} from '../components/DashboardShared';
import {
  buildSyllabus,
  buildSyllabusDraft,
  createGraph,
  generateFinalMaterial,
  generateMaterialDraft,
  getTeacherDashboardBootstrapData,
  getTeacherSyllabusBuildData,
  getTeacherSyllabusMaterialDetails,
  getTeacherSyllabusVisibleData,
  getMaterialDraftDetailRaw,
  getMaterialStatusRaw,
  listGraphs,
  parseMaterialDraftResponse,
  parseMaterialStatusResponse,
  publishMaterial,
  updateFinalMaterial,
  updateMaterialDraft,
  updateSyllabus,
  updateSyllabusDraft,
  uploadCalendar,
} from '../api/syllabus_material_api';
import { downloadFile, getFileDetail, uploadFile } from '../api/file_transmit_api';
import { createJob } from '../api/job_api';
import { getCurrentUserId } from '../api/session';

const BUILD_STEPS = ['上传', '生成草稿', '修正草稿', '生成终稿', '修正终稿', '完成'];
const MATERIAL_STEPS = ['选择草稿', '修正草稿', '生成终稿', '修正终稿', '发布'];

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function getCurrentWeekIndex(dayOneValue, periodLength) {
  if (!dayOneValue || !periodLength) {
    return null;
  }

  let dayOneDate = null;
  if (typeof dayOneValue === 'string' && /^\d{1,2}-\d{1,2}$/.test(dayOneValue)) {
    const [month, day] = dayOneValue.split('-').map(Number);
    dayOneDate = new Date(new Date().getFullYear(), month - 1, day);
  } else {
    dayOneDate = new Date(dayOneValue);
  }

  if (Number.isNaN(dayOneDate?.getTime?.())) {
    return null;
  }

  const diffMs = Date.now() - dayOneDate.getTime();
  if (diffMs < 0) {
    return 1;
  }

  const weekIndex = Math.floor(diffMs / (7 * 24 * 60 * 60 * 1000)) + 1;
  return Math.min(Math.max(weekIndex, 1), periodLength);
}

function createEmptySyllabus(nextId = null) {
  return {
    syllabusId: nextId,
    title: '新的教学大纲',
    permission: 'owner',
    graphId: null,
    graphName: null,
    dayOneTime: null,
    status: {
      isEduCalendarMissing: true,
      isDraftMissing: true,
      isFinalMissing: true,
    },
    draft: { title: '新的教学大纲', graph_name: '', period: [] },
    finalData: { title: '新的教学大纲', day_one: '', graph_name: '', period: [] },
    graphFiles: [],
    graphFileCount: 0,
    syllabusFiles: [],
    materialDrafts: [],
    materialShelf: [],
  };
}

function createEmptyDraftPeriod() {
  return Array.from({ length: 16 }, (_, index) => ({
    week_index: String(index + 1),
    content: '',
    importance: 'medium',
    day_one: '',
  }));
}

function createFinalPeriodFromDraft(period = []) {
  return period.map((item) => ({
    week_index: item.week_index,
    content: item.content ?? '',
    original_content: item.content ?? '',
    enhanced_content: item.content ?? '',
    importance: item.importance ?? 'medium',
    day_one: item.day_one ?? '',
  }));
}

function normalizeFinalPeriod(period = [], draftPeriod = []) {
  if (Array.isArray(period) && period.length) {
    return period.map((item, index) => {
      const fallback = draftPeriod.find((entry) => entry.week_index === item.week_index) ?? draftPeriod[index] ?? {};
      const originalContent = item.original_content ?? item.content ?? fallback.content ?? '';

      return {
        ...cloneData(item),
        content: item.content ?? originalContent,
        original_content: originalContent,
        enhanced_content: item.enhanced_content ?? originalContent,
        importance: item.importance ?? fallback.importance ?? 'medium',
        day_one: item.day_one ?? fallback.day_one ?? '',
      };
    });
  }

  return createFinalPeriodFromDraft(draftPeriod);
}

function buildDraftJson(state) {
  return {
    title: state.draftTitle,
    graph_name: state.selectedGraphName || state.syllabus.graphName || '',
    period: cloneData(state.draftPeriod),
  };
}

function buildFinalJson(state) {
  return {
    title: state.finalTitle,
    day_one: state.finalDayOne,
    graph_name: state.selectedGraphName || state.syllabus.graphName || '',
    period: cloneData(state.finalPeriod),
  };
}

function isSingleQuestion(question) {
  return String(question?.type ?? '').toLowerCase() === 'single';
}

function isJudgeQuestion(question) {
  return String(question?.type ?? '').toLowerCase() === 'judge';
}

function ensureSingleOptions(question) {
  const source = question?.options ?? {};

  return {
    A: source.A ?? '',
    B: source.B ?? '',
    C: source.C ?? '',
    D: source.D ?? '',
  };
}

function hydrateFinalQuestion(question) {
  const next = cloneData(question);

  if (isSingleQuestion(next)) {
    next.options = ensureSingleOptions(next);
    next.answer = typeof next.answer === 'string' ? next.answer : '';
  }

  if (isJudgeQuestion(next) && typeof next.answer !== 'boolean') {
    next.answer = Boolean(next.answer);
  }

  return next;
}

function createBuildState(active, graphOptions = []) {
  const draftPeriod = active.draft?.period?.length ? cloneData(active.draft.period) : createEmptyDraftPeriod();

  return {
    open: true,
    syllabus: cloneData(active),
    step: active.status.isFinalMissing
      ? (active.status.isDraftMissing ? (active.status.isEduCalendarMissing ? 0 : 1) : 2)
      : 4,
    busy: '',
    draftPeriod,
    draftTitle: active.title,
    draftDayOne: active.finalData?.day_one ?? '',
    finalTitle: active.finalData?.title ?? active.title,
    finalDayOne: active.finalData?.day_one ?? '',
    finalPeriod: normalizeFinalPeriod(active.finalData?.period ?? [], draftPeriod),
    expandedFinalWeekId: '',
    selectedGraphName: active.graphName ?? graphOptions.find((item) => item.graphId === active.graphId)?.graphName ?? '',
    newGraphName: '',
    selectedGraphId: active.graphId ?? '',
    calendarFiles: [],
  };
}

function createMaterialState(active) {
  return {
    open: true,
    step: 0,
    busy: '',
    materialId: null,
    draftTitle: `${active.title}_draft`,
    involvedWeeks: [],
    distribution: { single: 2, judge: 2, short: 1 },
    draftQuestions: [],
    finalQuestions: [],
    publish: { new_pdf: true, do_publish: false },
  };
}

function getMaterialWeekOptions(syllabus) {
  const period = Array.isArray(syllabus?.finalData?.period) ? syllabus.finalData.period : [];
  if (period.length) {
    return period.map((item) => ({
      weekIndex: Number(item.week_index),
      label: `第${item.week_index}周`,
    }));
  }

  return Array.from({ length: 16 }, (_, index) => ({
    weekIndex: index + 1,
    label: `第${index + 1}周`,
  }));
}

function mergeSyllabusData(source, patch) {
  return {
    ...source,
    ...patch,
    status: patch.status ?? source.status,
    draft: patch.draft ?? source.draft,
    finalData: patch.finalData ?? source.finalData,
    graphFiles: patch.graphFiles ?? source.graphFiles,
    graphFileCount: patch.graphFileCount ?? source.graphFileCount,
    syllabusFiles: patch.syllabusFiles ?? source.syllabusFiles,
    materialDrafts: patch.materialDrafts ?? source.materialDrafts,
    materialShelf: patch.materialShelf ?? source.materialShelf,
    isVisibleLoaded: patch.isVisibleLoaded ?? source.isVisibleLoaded,
    isBuildLoaded: patch.isBuildLoaded ?? source.isBuildLoaded,
    isMaterialDetailsLoaded: patch.isMaterialDetailsLoaded ?? source.isMaterialDetailsLoaded,
  };
}

function getSyllabusProgress(status) {
  if (!status.isFinalMissing) return { label: '教学大纲就绪', tone: 'success' };
  if (!status.isDraftMissing) return { label: '已构建草稿', tone: 'warning' };
  if (!status.isEduCalendarMissing) return { label: '已上传', tone: 'neutral' };
  return { label: '待创建', tone: 'warning' };
}

function getMaterialTag(status) {
  if (!status?.isFinalMissing) {
    return { text: '终稿就绪', tone: 'success' };
  }
  if (!status?.isDraftMissing) {
    return { text: '仅草稿', tone: 'warning' };
  }
  return { text: '待生成', tone: 'neutral' };
}

function getMaterialShelfItems(materialDrafts) {
  return materialDrafts.map((item) => {
    const tag = getMaterialTag(item.status);
    const involvedWeeks = item.finalData?.involved_weeks ?? item.draft?.involved_weeks ?? [];

    return {
      fileId: item.fileId ?? null,
      title: item.title,
      source: `material ${item.materialId}`,
      weekLabel: involvedWeeks.length ? `第 ${involvedWeeks.join(', ')} 周` : '',
      tagText: tag.text,
      tagTone: tag.tone,
    };
  });
}

function DraftEditorAxis({ items, currentWeek, onChange }) {
  return (
    <WeekAxis
      items={items}
      currentWeek={currentWeek}
      renderContent={(item) => (
        <textarea
          className="week-axis-input"
          rows="6"
          value={item.content}
          onChange={(event) => onChange(item.week_index, event.target.value)}
        />
      )}
    />
  );
}

function FinalEditorAxis({ items, currentWeek, expandedItemId, onExpand, onChange }) {
  return (
    <WeekAxis
      className="final-editor-axis"
      items={items}
      currentWeek={currentWeek}
      expandedItemId={expandedItemId}
      renderContent={(item) => (
        <div className={['week-axis-editor-stack', 'final-editor-layout', expandedItemId === `week-axis-importance-${item.week_index}` ? 'is-expanded' : ''].filter(Boolean).join(' ')}>
          <label className={['field', 'final-editor-field', 'final-editor-field-enhanced'].join(' ')}>
            <span>enhanced_content</span>
            <textarea
              className={['week-axis-input', 'week-axis-input-enhanced'].join(' ')}
              rows="8"
              value={item.enhanced_content ?? ''}
              onFocus={() => onExpand(`week-axis-importance-${item.week_index}`)}
              onClick={() => onExpand(`week-axis-importance-${item.week_index}`)}
              onChange={(event) => onChange(item.week_index, event.target.value)}
            />
          </label>
          <label className={['field', 'final-editor-field', 'final-editor-field-original'].join(' ')}>
            <span>original_content</span>
            <div className={['week-axis-readonly', 'week-axis-readonly-muted'].join(' ')}>
              {item.original_content ?? item.content ?? ''}
            </div>
          </label>
        </div>
      )}
    />
  );
}

function SingleChoiceOptionsEditor({ question, onChangeOption }) {
  const options = ensureSingleOptions(question);

  return (
    <div className="options-grid">
      {['A', 'B', 'C', 'D'].map((key) => (
        <label key={key} className="field">
          <span>{`option_${key}`}</span>
          <input
            value={options[key]}
            onChange={(event) => onChangeOption(key, event.target.value)}
          />
        </label>
      ))}
    </div>
  );
}

function FileDropzone({
  files,
  onFilesChange,
  multiple = false,
  compact = false,
  title = '选择文件 / dropbox',
}) {
  const [isDragging, setIsDragging] = useState(false);

  const applyFiles = (fileList) => {
    const nextFiles = Array.from(fileList ?? []);
    onFilesChange(multiple ? nextFiles : nextFiles.slice(0, 1));
  };

  return (
    <label
      className={['dropzone', 'file-dropzone', compact ? 'compact-dropzone' : '', isDragging ? 'is-dragging' : ''].filter(Boolean).join(' ')}
      onDragOver={(event) => {
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        applyFiles(event.dataTransfer?.files);
      }}
    >
      <input
        className="file-dropzone-input"
        type="file"
        multiple={multiple}
        onChange={(event) => applyFiles(event.target.files)}
      />
      <div className="file-dropzone-copy">
        <strong>{title}</strong>
        <small>
          {files.length
            ? files.map((file) => file.name).join(' / ')
            : '支持点击选择或拖拽到这里'}
        </small>
      </div>
    </label>
  );
}

function BuildSyllabusModal({
  syllabus,
  state,
  setState,
  draftCurrentWeek,
  finalCurrentWeek,
  graphOptions,
  onClose,
  onCreateGraph,
  onUpload,
  onGenerateDraft,
  onSaveDraft,
  onGenerateFinal,
  onSaveFinal,
}) {
  const finalEditorRef = useRef(null);
  const allowStep = (index) => {
    if (index === 0) return true;
    if (index === 1) return !syllabus.status.isEduCalendarMissing;
    if (index === 2 || index === 3) return !syllabus.status.isDraftMissing;
    return !syllabus.status.isFinalMissing;
  };

  return (
    <ModalShell title="构建教学大纲" onClose={onClose} className={state.step === 4 ? 'modal-shell-tall' : ''}>
      <Stepper
        steps={BUILD_STEPS}
        currentStep={state.step}
        allowStep={allowStep}
        onSelect={(index) => allowStep(index) && setState((current) => ({ ...current, step: index }))}
      />

      {state.step === 0 ? (
        <section className="modal-section">
          <div className="build-step-grid">
            <div className="study-mode graph-picker-panel">
              <div className="subsection-head">
                <strong className="study-mode-title">图谱选择</strong>
                <StatusPill tone={state.selectedGraphId ? 'success' : 'warning'}>
                  {state.selectedGraphId ? '已选图谱' : '待选择'}
                </StatusPill>
              </div>
              <div className="graph-create-row">
                <Button
                  variant="secondary"
                  onClick={onCreateGraph}
                  disabled={Boolean(state.busy) || !state.newGraphName.trim()}
                >
                  {state.busy === 'graph' ? '处理中...' : '创建新图谱'}
                </Button>
                <input
                  className="select-field"
                  value={state.newGraphName}
                  placeholder="输入图谱名称"
                  onChange={(event) => setState((current) => ({ ...current, newGraphName: event.target.value }))}
                />
              </div>
              <label className="field">
                <span>graph_id</span>
                <select
                  className="select-field"
                  value={state.selectedGraphId}
                  onChange={(event) => {
                    const nextId = Number(event.target.value) || '';
                    const nextGraph = graphOptions.find((graph) => graph.graphId === nextId);
                    setState((current) => ({
                      ...current,
                      selectedGraphId: nextId,
                      selectedGraphName: nextGraph?.graphName ?? '',
                    }));
                  }}
                >
                  <option value="">请选择图谱</option>
                  {graphOptions.map((graph) => (
                    <option key={graph.graphId} value={graph.graphId}>
                      {graph.graphName}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>graph_name</span>
                <input value={state.selectedGraphName} readOnly placeholder="当前所选图谱名称" />
              </label>
            </div>

            <DisabledBlock disabled={!state.selectedGraphId} message="请先在左侧选择一个图谱">
              <div className="study-mode">
                <div className="subsection-head">
                  <strong className="study-mode-title">上传教学日历</strong>
                  <StatusPill tone={!syllabus.status.isEduCalendarMissing ? 'success' : 'warning'}>
                    {!syllabus.status.isEduCalendarMissing ? '已存在' : '待上传'}
                  </StatusPill>
                </div>
                <FileDropzone
                  files={state.calendarFiles}
                  onFilesChange={(files) => setState((current) => ({ ...current, calendarFiles: files }))}
                  title="选择教学日历 / dropbox"
                />
                <div className="tile-actions">
                  <Button
                    variant="primary"
                    onClick={onUpload}
                    disabled={Boolean(state.busy) || !state.selectedGraphId || !state.calendarFiles.length}
                  >
                    {state.busy === 'upload' ? '处理中...' : '上传'}
                  </Button>
                  <Button variant="ghost" onClick={onClose}>取消</Button>
                </div>
              </div>
            </DisabledBlock>
          </div>
        </section>
      ) : null}

      {state.step === 1 ? (
        <section className="modal-section">
          <div className="study-mode">
            <strong className="study-mode-title">生成草稿</strong>
            <div className="processing-panel">
              <span>status</span>
              <strong>
                {state.busy === 'draft'
                  ? '正在处理，稍后再看'
                  : syllabus.status.isDraftMissing
                    ? '等待生成'
                    : '草稿已就绪'}
              </strong>
            </div>
            <div className="tile-actions">
              <Button variant="primary" onClick={onGenerateDraft} disabled={Boolean(state.busy)}>
                {state.busy === 'draft' ? '处理中...' : '生成大纲草稿'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => setState((current) => ({ ...current, step: 2 }))}
                disabled={syllabus.status.isDraftMissing}
              >
                修正草稿
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {state.step === 2 ? (
        <section className="modal-section">
          <div className="modal-form-grid">
            <label className="field">
              <span>new_title</span>
              <input
                value={state.draftTitle}
                onChange={(event) => setState((current) => ({ ...current, draftTitle: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>day_one</span>
              <input
                value={state.draftDayOne}
                onChange={(event) => setState((current) => ({ ...current, draftDayOne: event.target.value }))}
              />
            </label>
          </div>
          <DraftEditorAxis
            items={state.draftPeriod}
            currentWeek={draftCurrentWeek}
            onChange={(weekIndex, value) => {
              const next = cloneData(state.draftPeriod);
              const target = next.find((item) => item.week_index === weekIndex);
              if (target) target.content = value;
              setState((current) => ({ ...current, draftPeriod: next }));
            }}
          />
          <div className="tile-actions">
            <Button variant="primary" onClick={onSaveDraft}>保存</Button>
            <Button
              variant="secondary"
              onClick={() => setState((current) => ({ ...current, step: 1 }))}
            >
              重新生成草稿
            </Button>
          </div>
        </section>
      ) : null}

      {state.step === 3 ? (
        <section className="modal-section">
          <div className="study-mode">
            <strong className="study-mode-title">生成终稿</strong>
            <div className="processing-panel">
              <span>status</span>
              <strong>
                {state.busy === 'final'
                  ? '正在处理，稍后再看'
                  : syllabus.status.isFinalMissing
                    ? '等待生成'
                    : '终稿已就绪'}
              </strong>
            </div>
            <div className="tile-actions">
              <Button variant="primary" onClick={onGenerateFinal} disabled={Boolean(state.busy)}>
                {state.busy === 'final' ? '处理中...' : '生成教学大纲'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => setState((current) => ({ ...current, step: 4 }))}
                disabled={syllabus.status.isFinalMissing}
              >
                修正终稿
              </Button>
            </div>
          </div>
        </section>
      ) : null}

        {state.step === 4 ? (
          <section className="modal-section final-editor-section">
            <div className="modal-form-grid">
              <label className="field">
                <span>title</span>
              <input
                value={state.finalTitle}
                onChange={(event) => setState((current) => ({ ...current, finalTitle: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>day_one</span>
              <input
                value={state.finalDayOne}
                onChange={(event) => setState((current) => ({ ...current, finalDayOne: event.target.value }))}
              />
            </label>
          </div>
            <FinalEditorAxis
              items={state.finalPeriod}
              currentWeek={finalCurrentWeek}
              expandedItemId={state.expandedFinalWeekId}
              onExpand={(itemId) => setState((current) => ({
                ...current,
                expandedFinalWeekId: current.expandedFinalWeekId === itemId ? '' : itemId,
              }))}
              onChange={(weekIndex, value) => {
                const next = cloneData(state.finalPeriod);
                const target = next.find((item) => item.week_index === weekIndex);
              if (target) target.enhanced_content = value;
              setState((current) => ({ ...current, finalPeriod: next }));
            }}
          />
          <div className="tile-actions">
            <Button variant="primary" onClick={onSaveFinal}>保存</Button>
            <Button
              variant="secondary"
              onClick={() => setState((current) => ({ ...current, step: 3 }))}
            >
              重新生成
            </Button>
          </div>
        </section>
      ) : null}

      {state.step === 5 ? (
        <section className="modal-section">
          <div className="completion-panel">
            <strong>教学大纲已完成</strong>
            <div className="tile-actions">
              <Button variant="primary" onClick={onClose}>完成</Button>
            </div>
          </div>
        </section>
      ) : null}
    </ModalShell>
  );
}

function MaterialModal({
  syllabus,
  state,
  setState,
  onClose,
  onGenerateDraft,
  onSaveDraft,
  onGenerateFinal,
  onSaveFinal,
  onPublish,
}) {
  const selectedMaterial = syllabus.materialDrafts.find((item) => item.materialId === state.materialId) ?? null;
  const weekOptions = getMaterialWeekOptions(syllabus);
  const allowStep = (index) => {
    if (index === 0) return true;
    if (index === 1 || index === 2) return Boolean(selectedMaterial || state.draftQuestions.length);
    return Boolean(state.finalQuestions.length || (selectedMaterial && !selectedMaterial.status.isFinalMissing));
  };

  return (
    <ModalShell title="教学习题构建 / 编辑" onClose={onClose}>
      <Stepper
        steps={MATERIAL_STEPS}
        currentStep={state.step}
        allowStep={allowStep}
        onSelect={(index) => allowStep(index) && setState((current) => ({ ...current, step: index }))}
        />

      {selectedMaterial ? (
        <div className="selected-banner">
          <strong>{`已选择 ${selectedMaterial.draft?.material_title ?? selectedMaterial.title}`}</strong>
        </div>
      ) : null}

        {state.step === 0 ? (
          <section className="modal-section">
            <div className="study-mode">
              <div className="subsection-head">
                <strong className="study-mode-title">选择习题</strong>
                <StatusPill tone={syllabus.materialDrafts.length ? 'success' : 'warning'}>
                  {syllabus.materialDrafts.length ? '已有草稿' : '暂无草稿'}
                </StatusPill>
            </div>

            {syllabus.materialDrafts.length ? (
              <div className="resource-table">
                <div className="resource-table-head">
                  <span>material_id</span>
                  <span>title</span>
                  <span>create_time</span>
                </div>
                {syllabus.materialDrafts.map((item) => (
                  <button
                    key={item.materialId}
                    type="button"
                    className={`resource-table-row resource-table-button ${item.materialId === state.materialId ? 'is-selected' : ''}`}
                    onClick={() => setState((current) => ({
                      ...current,
                      materialId: item.materialId,
                      draftTitle: item.draft?.material_title ?? item.title,
                      involvedWeeks: cloneData(item.draft?.involved_weeks ?? [4]),
                      draftQuestions: cloneData(item.draft?.questions ?? []),
                      finalQuestions: cloneData(item.finalData?.questions ?? []).map(hydrateFinalQuestion),
                    }))}
                  >
                    <span>{item.materialId}</span>
                    <span>{item.title}</span>
                    <span>{item.createTime}</span>
                  </button>
                ))}
              </div>
            ) : (
                <EmptyState>暂无草稿。</EmptyState>
              )}
            </div>

            <div className="study-mode">
              <div className="subsection-head">
                <strong className="study-mode-title">生成习题草稿</strong>
              </div>
              <div className="week-checkbox-grid">
                {weekOptions.map((item) => (
                  <label key={item.weekIndex} className="checkbox-row week-checkbox-row">
                    <input
                      type="checkbox"
                      checked={state.involvedWeeks.includes(item.weekIndex)}
                      onChange={(event) => setState((current) => ({
                        ...current,
                        involvedWeeks: event.target.checked
                          ? [...current.involvedWeeks, item.weekIndex].sort((a, b) => a - b)
                          : current.involvedWeeks.filter((value) => value !== item.weekIndex),
                      }))}
                    />
                    <span>{item.label}</span>
                  </label>
                ))}
              </div>
              <div className="material-setup-grid">
                <label className="field">
                  <span>involved_weeks</span>
                  <input value={state.involvedWeeks.join(', ')} readOnly />
                </label>
                {['single', 'judge', 'short'].map((key) => (
                  <label key={key} className="field">
                  <span>{key}</span>
                  <input
                    value={state.distribution[key]}
                    onChange={(event) => setState((current) => ({
                      ...current,
                      distribution: {
                        ...current.distribution,
                        [key]: Number(event.target.value) || 0,
                      },
                    }))}
                  />
                </label>
              ))}
            </div>

              <div className="tile-actions">
                <Button variant="primary" onClick={onGenerateDraft} disabled={Boolean(state.busy)}>
                  {state.busy === 'material-draft' ? '处理中...' : '生成习题草稿'}
                </Button>
              </div>
            </div>
        </section>
      ) : null}

      {state.step === 1 ? (
        <section className="modal-section">
          <label className="field">
            <span>material_title</span>
            <input
              value={state.draftTitle}
              onChange={(event) => setState((current) => ({ ...current, draftTitle: event.target.value }))}
            />
          </label>
          <div className="editor-list">
            {state.draftQuestions.map((question, index) => (
              <article key={question.question_index} className="editor-card">
                <div className="editor-card-head">
                  <strong>{`Q${question.question_index} · ${String(question.type).toUpperCase()}`}</strong>
                </div>
                <label className="field">
                  <span>related_knowledge</span>
                  <textarea
                    rows="2"
                    value={question.related_knowledge}
                    onChange={(event) => {
                      const next = cloneData(state.draftQuestions);
                      next[index].related_knowledge = event.target.value;
                      setState((current) => ({ ...current, draftQuestions: next }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>query_key</span>
                  <input
                    value={question.query_key}
                    onChange={(event) => {
                      const next = cloneData(state.draftQuestions);
                      next[index].query_key = event.target.value;
                      setState((current) => ({ ...current, draftQuestions: next }));
                    }}
                  />
                </label>
              </article>
            ))}
          </div>
          <div className="tile-actions">
            <Button variant="primary" onClick={onSaveDraft}>保存</Button>
          </div>
        </section>
      ) : null}

      {state.step === 2 ? (
        <section className="modal-section">
          <div className="study-mode">
            <strong className="study-mode-title">生成终稿</strong>
            <div className="processing-panel">
              <span>status</span>
              <strong>
                {state.busy === 'material-final'
                  ? '正在处理...'
                  : state.finalQuestions.length
                    ? '终稿已就绪'
                    : '等待终稿'}
              </strong>
            </div>
            <div className="tile-actions">
              <Button variant="primary" onClick={onGenerateFinal} disabled={Boolean(state.busy)}>
                {state.busy === 'material-final' ? '处理中...' : '生成习题终稿'}
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {state.step === 3 ? (
        <section className="modal-section">
          <div className="editor-list">
            {state.finalQuestions.map((question, index) => (
              <article key={question.question_index} className="editor-card">
                <div className="editor-card-head">
                  <strong>{`Q${question.question_index} · ${String(question.type).toUpperCase()}`}</strong>
                  <StatusPill tone="neutral">{question.query_key}</StatusPill>
                </div>
                <label className="field">
                  <span>question_content</span>
                  <textarea
                    rows="2"
                    value={question.question_content ?? ''}
                    onChange={(event) => {
                      const next = cloneData(state.finalQuestions);
                      next[index].question_content = event.target.value;
                      setState((current) => ({ ...current, finalQuestions: next }));
                    }}
                  />
                </label>

                {isSingleQuestion(question) ? (
                  <SingleChoiceOptionsEditor
                    question={question}
                    onChangeOption={(key, value) => {
                      const next = cloneData(state.finalQuestions);
                      next[index].options = ensureSingleOptions(next[index]);
                      next[index].options[key] = value;
                      setState((current) => ({ ...current, finalQuestions: next }));
                    }}
                  />
                ) : null}

                <label className="field">
                  <span>answer</span>
                  {isSingleQuestion(question) ? (
                    <select
                      className="select-field"
                      value={String(question.answer ?? '')}
                      onChange={(event) => {
                        const next = cloneData(state.finalQuestions);
                        next[index].answer = event.target.value;
                        setState((current) => ({ ...current, finalQuestions: next }));
                      }}
                    >
                      <option value="">请选择</option>
                      {['A', 'B', 'C', 'D'].map((key) => (
                        <option key={key} value={key}>{key}</option>
                      ))}
                    </select>
                  ) : isJudgeQuestion(question) ? (
                    <select
                      className="select-field"
                      value={String(Boolean(question.answer))}
                      onChange={(event) => {
                        const next = cloneData(state.finalQuestions);
                        next[index].answer = event.target.value === 'true';
                        setState((current) => ({ ...current, finalQuestions: next }));
                      }}
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    <input
                      value={String(question.answer ?? '')}
                      onChange={(event) => {
                        const next = cloneData(state.finalQuestions);
                        next[index].answer = event.target.value;
                        setState((current) => ({ ...current, finalQuestions: next }));
                      }}
                    />
                  )}
                </label>
                <label className="field">
                  <span>reason</span>
                  <textarea
                    rows="3"
                    value={question.reason ?? ''}
                    onChange={(event) => {
                      const next = cloneData(state.finalQuestions);
                      next[index].reason = event.target.value;
                      setState((current) => ({ ...current, finalQuestions: next }));
                    }}
                  />
                </label>
              </article>
            ))}
          </div>
          <div className="tile-actions">
            <Button variant="primary" onClick={onSaveFinal}>保存</Button>
          </div>
        </section>
      ) : null}

      {state.step === 4 ? (
        <section className="modal-section">
          <div className="publish-grid">
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={state.publish.new_pdf}
                onChange={(event) => setState((current) => ({
                  ...current,
                  publish: { ...current.publish, new_pdf: event.target.checked },
                }))}
              />
              <span>生成新的 PDF</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={state.publish.do_publish}
                onChange={(event) => setState((current) => ({
                  ...current,
                  publish: { ...current.publish, do_publish: event.target.checked },
                }))}
              />
              <span>公开给学生</span>
            </label>
          </div>
          <div className="tile-actions">
            <Button variant="primary" onClick={onPublish}>执行</Button>
          </div>
        </section>
      ) : null}
    </ModalShell>
  );
}

export default function TeacherDashboard({ navigate }) {
  const [syllabuses, setSyllabuses] = useState([]);
  const [graphOptions, setGraphOptions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [isBooting, setIsBooting] = useState(true);
  const [error, setError] = useState('');
  const [buildModal, setBuildModal] = useState({ open: false });
  const [materialModal, setMaterialModal] = useState({ open: false });
  const [materialUploadFiles, setMaterialUploadFiles] = useState([]);
  const [materialUploadBusy, setMaterialUploadBusy] = useState(false);

  const handleDownloadFile = async (item) => {
    if (!item?.fileId) {
      return;
    }

    const result = await downloadFile(item.fileId, item.title);
    if (!result.success) {
      throw new Error(result.error_message || '下载失败');
    }
  };
  const [expandedTeacherWeekId, setExpandedTeacherWeekId] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!getCurrentUserId()) {
        navigate('/login');
        setIsBooting(false);
        return;
      }

      setIsBooting(true);
      setError('');

      try {
        const [bootstrap, graphs] = await Promise.all([getTeacherDashboardBootstrapData(), listGraphs()]);
        const firstSyllabusId = bootstrap.syllabuses[0]?.syllabusId ?? null;
        const firstSyllabus = bootstrap.syllabuses[0] ?? null;
        const firstVisibleData = firstSyllabus ? await getTeacherSyllabusVisibleData(firstSyllabus) : null;

        if (!cancelled) {
          setSyllabuses(
            bootstrap.syllabuses.map((item) => (
              item.syllabusId === firstSyllabusId && firstVisibleData
                ? mergeSyllabusData(item, firstVisibleData)
                : item
            )),
          );
          setGraphOptions(graphs);
          setActiveId(firstSyllabusId);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '加载失败');
        }
      } finally {
        if (!cancelled) {
          window.setTimeout(() => setIsBooting(false), 240);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    if (!activeId) {
      return undefined;
    }

    const target = syllabuses.find((item) => item.syllabusId === activeId);
    if (!target || target.isVisibleLoaded) {
      return undefined;
    }

    let cancelled = false;

    async function hydrateVisible() {
      try {
        const visibleData = await getTeacherSyllabusVisibleData(target);
        if (cancelled) {
          return;
        }
        patchSyllabusById(activeId, (item) => mergeSyllabusData(item, visibleData));
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '加载失败');
        }
      }
    }

    hydrateVisible();

    return () => {
      cancelled = true;
    };
  }, [activeId, syllabuses]);

  useEffect(() => {
    if (!activeId) {
      return undefined;
    }

    const target = syllabuses.find((item) => item.syllabusId === activeId);
    if (!target || !target.isVisibleLoaded || target.isMaterialDetailsLoaded) {
      return undefined;
    }

    let cancelled = false;

    async function hydrateMaterialDetails() {
      try {
        const materialData = await getTeacherSyllabusMaterialDetails(target);
        if (cancelled) {
          return;
        }
        patchSyllabusById(activeId, (item) => mergeSyllabusData(item, materialData));
      } catch {
        // Silent hydration should not block the page.
      }
    }

    hydrateMaterialDetails();

    return () => {
      cancelled = true;
    };
  }, [activeId, syllabuses]);

  const active = useMemo(
    () => syllabuses.find((item) => item.syllabusId === activeId) ?? syllabuses[0] ?? null,
    [activeId, syllabuses],
  );
  const buildTarget = buildModal.open ? (buildModal.syllabus ?? active) : null;
  const activeCurrentWeek = useMemo(
    () => getCurrentWeekIndex(active?.dayOneTime ?? active?.finalData?.day_one, active?.finalData?.period?.length ?? 0),
    [active?.dayOneTime, active?.finalData?.day_one, active?.finalData?.period],
  );

  useEffect(() => {
    setExpandedTeacherWeekId(null);
  }, [activeId]);
  const buildDraftCurrentWeek = useMemo(
    () => getCurrentWeekIndex(buildModal.draftDayOne || buildTarget?.dayOneTime, buildModal.draftPeriod?.length ?? 0),
    [buildModal.draftDayOne, buildModal.draftPeriod, buildTarget?.dayOneTime],
  );
  const buildFinalCurrentWeek = useMemo(
    () => getCurrentWeekIndex(buildModal.finalDayOne || buildTarget?.dayOneTime, buildModal.finalPeriod?.length ?? 0),
    [buildModal.finalDayOne, buildModal.finalPeriod, buildTarget?.dayOneTime],
  );
  const weakKnowledge = active ? active.graphFileCount <= 2 : true;
  const overviewDisabled = isBooting || !active || active.status.isEduCalendarMissing || weakKnowledge;
  const materialDisabled = isBooting || !active;
  const syllabusProgress = active ? getSyllabusProgress(active.status) : { label: '待创建', tone: 'warning' };
  const materialDraftShelfItems = useMemo(
    () => getMaterialShelfItems(active?.materialDrafts ?? []),
    [active?.materialDrafts],
  );
  const showTeacherShell = Boolean(active) || isBooting;
  const isTeacherVisibleLoading = isBooting || Boolean(active && !active.isVisibleLoaded);

  const patchActive = (updater) => {
    setSyllabuses((current) =>
      current.map((item) => (item.syllabusId === activeId ? updater(cloneData(item)) : item)),
    );
  };

  const patchSyllabusById = (syllabusId, updater) => {
    setSyllabuses((current) =>
      current.map((item) => (item.syllabusId === syllabusId ? updater(cloneData(item)) : item)),
    );
  };

  const ensureBuildData = async (syllabus) => {
    if (!syllabus?.syllabusId || syllabus.isBuildLoaded) {
      return syllabus;
    }

    const buildData = await getTeacherSyllabusBuildData(syllabus);
    const nextSyllabus = mergeSyllabusData(syllabus, buildData);
    patchSyllabusById(syllabus.syllabusId, (item) => mergeSyllabusData(item, buildData));
    return nextSyllabus;
  };

  const ensureMaterialDetails = async (syllabus) => {
    if (!syllabus?.syllabusId || syllabus.isMaterialDetailsLoaded) {
      return syllabus;
    }

    const materialData = await getTeacherSyllabusMaterialDetails(syllabus);
    const nextSyllabus = mergeSyllabusData(syllabus, materialData);
    patchSyllabusById(syllabus.syllabusId, (item) => mergeSyllabusData(item, materialData));
    return nextSyllabus;
  };

  const switchSyllabus = (offset) => {
    if (!syllabuses.length) return;
    const currentIndex = syllabuses.findIndex((item) => item.syllabusId === activeId);
    const nextIndex = (currentIndex + offset + syllabuses.length) % syllabuses.length;
    setActiveId(syllabuses[nextIndex].syllabusId);
    setMaterialUploadFiles([]);
    setBuildModal({ open: false });
    setMaterialModal({ open: false });
  };

  const createNewSyllabus = () => {
    setMaterialUploadFiles([]);
    setBuildModal(createBuildState(createEmptySyllabus(), graphOptions));
  };

  const softRefreshGraphs = async (nextSelectedGraphId = '') => {
    const graphs = await listGraphs();
    setGraphOptions(graphs);
    const nextGraph = graphs.find((item) => item.graphId === (nextSelectedGraphId || buildModal.selectedGraphId));
    setBuildModal((current) => ({
      ...current,
      selectedGraphId: nextSelectedGraphId || current.selectedGraphId,
      selectedGraphName: nextGraph?.graphName ?? current.selectedGraphName,
      busy: '',
    }));
  };

  return (
    <>
      <MainLayout
        title="教师 Dashboard"
        actions={(
          <div className="header-actions">
            <Button variant="secondary" onClick={() => navigate('/login')}>返回登录</Button>
            <Button variant="primary" onClick={createNewSyllabus}>创建新的教学大纲</Button>
          </div>
        )}
      >
        <section className="dashboard-shell">
          <section className="dashboard-hero">
            <SyllabusSwitcher
              items={syllabuses}
              activeId={activeId ?? 0}
              onChange={setActiveId}
              onPrev={() => switchSyllabus(-1)}
              onNext={() => switchSyllabus(1)}
              disabled={isBooting || !syllabuses.length}
            />
          </section>

          {error ? <EmptyState>{error}</EmptyState> : null}
          {!error && !active && !isBooting ? <EmptyState>暂无教学大纲。</EmptyState> : null}

          {showTeacherShell ? (
            <section className="dashboard-grid dashboard-grid-teacher">
              <article className="tile-card tile-teal tile-span-full">
                <div className="tile-card-head">
                  <h3>教学大纲总览</h3>
                  <StatusPill tone={weakKnowledge ? 'danger' : 'success'}>
                    {weakKnowledge ? '知识来源过少' : '可交互'}
                  </StatusPill>
                </div>
                {isTeacherVisibleLoading ? (
                  <LoadingPlaceholder size="axis" />
                ) : (
                <DisabledBlock
                  disabled={overviewDisabled}
                  message={weakKnowledge ? '知识来源过少' : '等待数据加载或教学日历上传'}
                >
                  <WeekAxis
                    items={active.finalData?.period ?? []}
                    currentWeek={activeCurrentWeek}
                    expandedItemId={expandedTeacherWeekId}
                    onToggleExpand={(itemId) => {
                      setExpandedTeacherWeekId((current) => (current === itemId ? null : itemId));
                    }}
                  />
                </DisabledBlock>
                )}
              </article>

              <div className="teacher-side-stack">
                <article className="tile-card tile-amber tile-third">
                  <div className="tile-card-head">
                    <h3>教学大纲</h3>
                    <StatusPill tone={syllabusProgress.tone}>{syllabusProgress.label}</StatusPill>
                  </div>
                  {isTeacherVisibleLoading ? (
                    <LoadingPlaceholder size="panel" />
                  ) : (
                    <DisabledBlock disabled={weakKnowledge} message="知识过少，暂不允许交互">
                      <div className="tile-actions">
                        <Button
                          variant="primary"
                          onClick={async () => {
                            try {
                              const syllabusForBuild = await ensureBuildData(active);
                              setBuildModal(createBuildState(syllabusForBuild, graphOptions));
                            } catch (actionError) {
                              setError(actionError instanceof Error ? actionError.message : '加载教学大纲详情失败');
                            }
                          }}
                        >
                          {active.status.isFinalMissing ? '创建教学大纲' : '编辑教学大纲'}
                        </Button>
                      </div>
                    </DisabledBlock>
                  )}
                </article>
                <article className="tile-card tile-blue tile-third">
                  <div className="tile-card-head">
                    <h3>教学习题构建</h3>
                    <StatusPill tone={materialDisabled || weakKnowledge ? 'warning' : 'success'}>
                      {materialDisabled || weakKnowledge ? '不可用' : '可编辑'}
                    </StatusPill>
                  </div>
                  {isTeacherVisibleLoading ? (
                    <LoadingPlaceholder size="shelf" />
                  ) : (
                    <DisabledBlock
                      disabled={materialDisabled || weakKnowledge}
                      message={weakKnowledge ? '知识来源过少' : '等待数据加载'}
                    >
                      <MaterialShelf
                        items={materialDraftShelfItems.map((item) => ({
                          ...item,
                          onDownload: async (downloadItem) => {
                            try {
                              await handleDownloadFile(downloadItem);
                            } catch (actionError) {
                              setError(actionError instanceof Error ? actionError.message : '下载失败');
                            }
                          },
                        }))}
                        rows={2}
                        emptyText="暂无习题文件。"
                      />
                      <div className="tile-actions">
                        <Button
                          variant="primary"
                          onClick={async () => {
                            try {
                              const syllabusForMaterial = await ensureMaterialDetails(active);
                              setMaterialModal(createMaterialState(syllabusForMaterial));
                            } catch (actionError) {
                              setError(actionError instanceof Error ? actionError.message : '加载习题详情失败');
                            }
                          }}
                        >
                          打开弹窗
                        </Button>
                      </div>
                    </DisabledBlock>
                  )}
                </article>
              </div>
              <article className="tile-card tile-slate tile-two-thirds">
                <div className="tile-card-head">
                  <h3>教学材料</h3>
                  <StatusPill tone={materialDisabled ? 'warning' : 'success'}>
                    {`graph-file ${active?.graphFiles?.length ?? 0}`}
                  </StatusPill>
                </div>
                {isTeacherVisibleLoading ? (
                  <>
                    <LoadingPlaceholder size="panel" />
                    <LoadingPlaceholder size="shelf" />
                  </>
                ) : (
                  <>
                    <div className="study-mode compact-mode">
                      <FileDropzone
                        files={materialUploadFiles}
                        onFilesChange={setMaterialUploadFiles}
                        multiple
                        compact
                        title="选择教学材料 / dropbox"
                      />
                      <div className="tile-actions">
                        <Button
                          variant="secondary"
                          disabled={materialUploadBusy || !materialUploadFiles.length || !active.graphId}
                          onClick={async () => {
                            setMaterialUploadBusy(true);
                            try {
                              const nextFiles = await Promise.all(
                                materialUploadFiles.map(async (file) => {
                                  const uploadResponse = await uploadFile({ file });
                                  if (!uploadResponse.success || !uploadResponse.file?.file_id) {
                                    throw new Error(uploadResponse.error_message || '上传教学材料失败');
                                  }
                                  const fileDetail = await getFileDetail(uploadResponse.file.file_id);
                                  if (!fileDetail?.fileId) {
                                    throw new Error('get file detail failed');
                                  }
                                  const jobResponse = await createJob({
                                    graphId: active.graphId,
                                    fileId: uploadResponse.file.file_id,
                                  });
                                  if (!jobResponse.success) {
                                    throw new Error(jobResponse.errorMessage || '创建解析任务失败');
                                  }
                                  return {
                                    fileId: fileDetail.fileId,
                                    title: fileDetail.title,
                                    source: 'graph-file',
                                    weekLabel: '',
                                    tagText: 'pending / pdf_to_md',
                                    tagTone: 'warning',
                                  };
                                }),
                              );
                              patchActive((item) => {
                                item.graphFiles = [...nextFiles, ...item.graphFiles];
                                item.graphFileCount = item.graphFiles.length;
                                return item;
                              });
                              setMaterialUploadFiles([]);
                            } catch (actionError) {
                              setError(actionError instanceof Error ? actionError.message : '上传教学材料失败');
                            } finally {
                              setMaterialUploadBusy(false);
                            }
                          }}
                        >
                          {materialUploadBusy ? '处理中...' : '上传教学材料'}
                        </Button>
                      </div>
                    </div>
                    <DisabledBlock disabled={materialDisabled} message="等待数据加载">
                      <MaterialShelf
                        items={(active.graphFiles ?? []).map((item) => ({
                          ...item,
                          onDownload: async (downloadItem) => {
                            try {
                              await handleDownloadFile(downloadItem);
                            } catch (actionError) {
                              setError(actionError instanceof Error ? actionError.message : '下载失败');
                            }
                          },
                        }))}
                        emptyText="暂无 graph-file。"
                      />
                    </DisabledBlock>
                  </>
                )}
              </article>
            </section>
          ) : null}
        </section>
      </MainLayout>

      {buildModal.open && buildTarget ? (
        <BuildSyllabusModal
          syllabus={buildTarget}
          state={buildModal}
          setState={setBuildModal}
          draftCurrentWeek={buildDraftCurrentWeek}
          finalCurrentWeek={buildFinalCurrentWeek}
          graphOptions={graphOptions}
          onClose={() => setBuildModal({ open: false })}
          onCreateGraph={async () => {
            setBuildModal((current) => ({ ...current, busy: 'graph' }));
            setError('');
            try {
              const response = await createGraph({ graphName: buildModal.newGraphName });
              if (!response.success || !response.graphId) {
                throw new Error(response.errorMessage || '创建图谱失败');
              }
              await softRefreshGraphs(response.graphId);
              setBuildModal((current) => ({
                ...current,
                newGraphName: '',
                selectedGraphId: response.graphId,
                selectedGraphName: response.graphName,
                busy: '',
              }));
            } catch (actionError) {
              setBuildModal((current) => ({ ...current, busy: '' }));
              setError(actionError instanceof Error ? actionError.message : '创建图谱失败');
            }
          }}
          onUpload={async () => {
            setBuildModal((current) => ({ ...current, busy: 'upload' }));
            setError('');
            try {
              const response = await uploadCalendar({
                graphId: buildModal.selectedGraphId,
                file: buildModal.calendarFiles[0],
              });
              if (!response.success || !response.syllabusId) {
                throw new Error(response.errorMessage || '上传失败');
              }
              const selectedGraph = graphOptions.find((item) => item.graphId === buildModal.selectedGraphId);
              const nextSyllabus = {
                ...cloneData(buildTarget),
                syllabusId: response.syllabusId,
                graphId: buildModal.selectedGraphId || buildTarget.graphId,
                graphName: selectedGraph?.graphName ?? buildTarget.graphName,
                status: {
                  ...buildTarget.status,
                  isEduCalendarMissing: false,
                },
              };
              setSyllabuses((current) => {
                const next = [...current];
                const currentIndex = buildTarget.syllabusId == null
                  ? -1
                  : next.findIndex((item) => item.syllabusId === buildTarget.syllabusId);
                const uploadedIndex = next.findIndex((item) => item.syllabusId === response.syllabusId);

                if (currentIndex >= 0) {
                  next[currentIndex] = nextSyllabus;
                } else if (uploadedIndex >= 0) {
                  next[uploadedIndex] = nextSyllabus;
                } else {
                  next.push(nextSyllabus);
                }

                return next;
              });
              setActiveId(response.syllabusId);
              setBuildModal((current) => ({
                ...current,
                syllabus: nextSyllabus,
                busy: '',
                step: 1,
                selectedGraphName: selectedGraph?.graphName ?? current.selectedGraphName,
                calendarFiles: [],
              }));
            } catch (actionError) {
              setBuildModal((current) => ({ ...current, busy: '' }));
              setError(actionError instanceof Error ? actionError.message : '上传失败');
            }
          }}
          onGenerateDraft={async () => {
            setBuildModal((current) => ({ ...current, busy: 'draft' }));
            setError('');
            try {
              await buildSyllabusDraft({
                syllabusId: buildTarget.syllabusId,
                graphId: buildModal.selectedGraphId || buildTarget.graphId,
              });
              patchSyllabusById(buildTarget.syllabusId, (item) => {
                item.status.isDraftMissing = false;
                item.draft = buildDraftJson(buildModal);
                item.graphId = buildModal.selectedGraphId || item.graphId;
                item.graphName = buildModal.selectedGraphName || item.graphName;
                return item;
              });
              setBuildModal((current) => ({
                ...current,
                syllabus: {
                  ...current.syllabus,
                  status: {
                    ...current.syllabus.status,
                    isDraftMissing: false,
                  },
                  draft: buildDraftJson(current),
                  graphId: current.selectedGraphId || current.syllabus.graphId,
                  graphName: current.selectedGraphName || current.syllabus.graphName,
                },
                finalPeriod: createFinalPeriodFromDraft(current.draftPeriod),
                busy: '',
                step: 2,
              }));
            } catch (actionError) {
              setBuildModal((current) => ({ ...current, busy: '' }));
              setError(actionError instanceof Error ? actionError.message : '生成草稿失败');
            }
          }}
          onSaveDraft={async () => {
            setError('');
            try {
              await updateSyllabusDraft({
                syllabusId: buildTarget.syllabusId,
                syllabusDraftJson: buildDraftJson(buildModal),
              });
              patchSyllabusById(buildTarget.syllabusId, (item) => {
                item.title = buildModal.draftTitle;
                item.draft = buildDraftJson(buildModal);
                return item;
              });
              setBuildModal((current) => ({
                ...current,
                syllabus: {
                  ...current.syllabus,
                  title: current.draftTitle,
                  draft: buildDraftJson(current),
                },
                finalTitle: current.draftTitle,
                finalDayOne: current.draftDayOne,
                finalPeriod: createFinalPeriodFromDraft(current.draftPeriod),
                step: 3,
              }));
            } catch (actionError) {
              setError(actionError instanceof Error ? actionError.message : '保存草稿失败');
            }
          }}
          onGenerateFinal={async () => {
            setBuildModal((current) => ({ ...current, busy: 'final' }));
            setError('');
            try {
              const selectedGraph = graphOptions.find(
                (item) => item.graphId === (buildModal.selectedGraphId || buildTarget.graphId),
              );
              await buildSyllabus({
                syllabusId: buildTarget.syllabusId,
              });
              patchSyllabusById(buildTarget.syllabusId, (item) => {
                const nextFinalPeriod = createFinalPeriodFromDraft(buildModal.draftPeriod);
                item.status.isFinalMissing = false;
                item.graphName = selectedGraph?.graphName ?? item.graphName;
                item.finalData = {
                  title: buildModal.draftTitle,
                  day_one: buildModal.draftDayOne,
                  graph_name: selectedGraph?.graphName ?? item.graphName ?? '',
                  period: nextFinalPeriod,
                };
                return item;
              });
              setBuildModal((current) => {
                const nextFinalPeriod = createFinalPeriodFromDraft(current.draftPeriod);

                return {
                  ...current,
                  syllabus: {
                    ...current.syllabus,
                    graphName: selectedGraph?.graphName ?? current.syllabus.graphName,
                    status: {
                      ...current.syllabus.status,
                      isFinalMissing: false,
                    },
                    finalData: {
                      title: current.draftTitle,
                      day_one: current.draftDayOne,
                      graph_name: selectedGraph?.graphName ?? current.syllabus.graphName ?? '',
                      period: nextFinalPeriod,
                    },
                  },
                  finalPeriod: nextFinalPeriod,
                  busy: '',
                  step: 4,
                };
              });
            } catch (actionError) {
              setBuildModal((current) => ({ ...current, busy: '' }));
              setError(actionError instanceof Error ? actionError.message : '生成终稿失败');
            }
          }}
          onSaveFinal={async () => {
            setError('');
            try {
              await updateSyllabus({
                syllabusId: buildTarget.syllabusId,
                syllabusJson: buildFinalJson(buildModal),
              });
              patchSyllabusById(buildTarget.syllabusId, (item) => {
                item.title = buildModal.finalTitle;
                item.finalData = buildFinalJson(buildModal);
                return item;
              });
              setBuildModal((current) => ({
                ...current,
                syllabus: {
                  ...current.syllabus,
                  title: current.finalTitle,
                  finalData: buildFinalJson(current),
                },
                step: 5,
              }));
            } catch (actionError) {
              setError(actionError instanceof Error ? actionError.message : '保存终稿失败');
            }
          }}
        />
      ) : null}

      {materialModal.open && active ? (
        <MaterialModal
          syllabus={active}
          state={materialModal}
          setState={setMaterialModal}
          onClose={() => setMaterialModal({ open: false })}
          onGenerateDraft={async () => {
            setMaterialModal((current) => ({ ...current, busy: 'material-draft' }));
            setError('');
            try {
              const response = await generateMaterialDraft({
                syllabusId: active.syllabusId,
                involvedWeeks: materialModal.involvedWeeks,
                questionTypeDistribution: materialModal.distribution,
              });
              if (!response.success || !response.materialId) {
                throw new Error(response.errorMessage || 'generate material draft failed');
              }

              const [draftResponse, statusResponse] = await Promise.all([
                getMaterialDraftDetailRaw(response.materialId),
                getMaterialStatusRaw(response.materialId),
              ]);
              const draft = parseMaterialDraftResponse(draftResponse);
              const status = parseMaterialStatusResponse(statusResponse);

              patchActive((item) => {
                const existingIndex = item.materialDrafts.findIndex(
                  (draftItem) => draftItem.materialId === response.materialId,
                );
                const nextMaterial = {
                  materialId: response.materialId,
                  title: draft?.material_title ?? `material_${response.materialId}`,
                  draftPath: null,
                  finalPath: null,
                  pdfPath: null,
                  createTime: null,
                  draft,
                  finalData: null,
                  status,
                };

                if (existingIndex >= 0) {
                  item.materialDrafts[existingIndex] = nextMaterial;
                } else {
                  item.materialDrafts = [nextMaterial, ...item.materialDrafts];
                }

                return item;
              });

              setMaterialModal((current) => ({
                ...current,
                busy: '',
                step: 1,
                materialId: response.materialId,
                draftTitle: draft?.material_title ?? current.draftTitle,
                involvedWeeks: cloneData(draft?.involved_weeks ?? current.involvedWeeks),
                draftQuestions: cloneData(draft?.questions ?? []),
                finalQuestions: [],
              }));
            } catch (actionError) {
              setMaterialModal((current) => ({ ...current, busy: '' }));
              setError(actionError instanceof Error ? actionError.message : '生成习题草稿失败');
            }
          }}
          onSaveDraft={async () => {
            setError('');
            try {
              await updateMaterialDraft({
                materialId: materialModal.materialId,
                materialDraftJson: {
                  material_title: materialModal.draftTitle,
                  involved_weeks: cloneData(materialModal.involvedWeeks),
                  questions: cloneData(materialModal.draftQuestions),
                },
              });
              patchActive((item) => {
                const target = item.materialDrafts.find(
                  (draft) => draft.materialId === materialModal.materialId,
                );
                if (target) {
                  target.draft = {
                    ...target.draft,
                    material_title: materialModal.draftTitle,
                    involved_weeks: cloneData(materialModal.involvedWeeks),
                    questions: cloneData(materialModal.draftQuestions),
                  };
                }
                return item;
              });
              setMaterialModal((current) => ({ ...current, step: 2 }));
            } catch (actionError) {
              setError(actionError instanceof Error ? actionError.message : '保存习题草稿失败');
            }
          }}
          onGenerateFinal={async () => {
            setMaterialModal((current) => ({ ...current, busy: 'material-final' }));
            setError('');
            try {
              await generateFinalMaterial({ materialId: materialModal.materialId });
              const nextQuestions = (
                materialModal.finalQuestions.length
                  ? materialModal.finalQuestions
                  : cloneData(materialModal.draftQuestions)
              ).map(hydrateFinalQuestion);

              patchActive((item) => {
                const target = item.materialDrafts.find(
                  (draft) => draft.materialId === materialModal.materialId,
                );
                if (target) {
                  target.status.isFinalMissing = false;
                  target.finalData = {
                    material_title: materialModal.draftTitle,
                    involved_weeks: cloneData(materialModal.involvedWeeks),
                    questions: cloneData(nextQuestions),
                  };
                }
                return item;
              });

              setMaterialModal((current) => ({
                ...current,
                busy: '',
                finalQuestions: nextQuestions,
                step: 3,
              }));
            } catch (actionError) {
              setMaterialModal((current) => ({ ...current, busy: '' }));
              setError(actionError instanceof Error ? actionError.message : '生成习题终稿失败');
            }
          }}
          onSaveFinal={async () => {
            setError('');
            try {
              await updateFinalMaterial({
                materialId: materialModal.materialId,
                materialJson: {
                  material_title: materialModal.draftTitle,
                  involved_weeks: cloneData(materialModal.involvedWeeks),
                  questions: cloneData(materialModal.finalQuestions),
                },
              });
              patchActive((item) => {
                const target = item.materialDrafts.find(
                  (draft) => draft.materialId === materialModal.materialId,
                );
                if (target) {
                  target.finalData = {
                    ...target.finalData,
                    questions: cloneData(materialModal.finalQuestions),
                  };
                }
                return item;
              });
              setMaterialModal((current) => ({ ...current, step: 4 }));
            } catch (actionError) {
              setError(actionError instanceof Error ? actionError.message : '保存习题终稿失败');
            }
          }}
          onPublish={async () => {
            setError('');
            try {
              await publishMaterial({
                materialId: materialModal.materialId,
                ...materialModal.publish,
              });
              setMaterialModal({ open: false });
            } catch (actionError) {
              setError(actionError instanceof Error ? actionError.message : '发布失败');
            }
          }}
        />
      ) : null}
    </>
  );
}



