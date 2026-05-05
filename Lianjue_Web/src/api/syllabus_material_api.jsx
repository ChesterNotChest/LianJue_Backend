import {
  RAW_GET_MATERIAL_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID,
  RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID,
  RAW_GET_MATERIAL_STATUS_RESPONSE_BY_MATERIAL_ID,
  RAW_GET_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW,
  RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW,
  RAW_GET_SYLLABUS_STATUS_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW,
  RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7,
  RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID,
} from './mock_payloads';
import { USE_MOCK_API, apiGet, apiPost, fileToUploadPayload } from './client';
import { listGraphFiles, listSyllabusFiles } from './file_transmit_api';
import { getJobLabel, getJobTone, listJobs } from './job_api';
import { requireUserId } from './session';

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function createInitialGraphStore() {
  const rows = Array.isArray(RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7?.syllabuses)
    ? RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7.syllabuses
    : [];

  return rows
    .filter((row) => row.graph_id != null && row.graph_name)
    .map((row) => ({
      graph_id: row.graph_id,
      graph_name: row.graph_name,
    }));
}

let mockGraphStore = createInitialGraphStore();
let mockUploadedSyllabusIdSeed = Math.max(
  0,
  ...((RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7?.syllabuses ?? []).map((row) => row.syllabus_id ?? 0)),
);
let mockSyllabusDetailResponseById = cloneData(RAW_GET_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW);
let mockSyllabusDraftDetailResponseById = cloneData(RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW);
let mockMaterialDetailResponseById = cloneData(RAW_GET_MATERIAL_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID);
let mockMaterialDraftDetailResponseById = cloneData(RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID);
const teacherVisibleInflight = new Map();
const teacherBuildInflight = new Map();
const teacherMaterialInflight = new Map();

function updateManageSyllabusTitle(syllabusId, title) {
  const rows = RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7?.syllabuses ?? [];
  const target = rows.find((row) => row.syllabus_id === syllabusId);
  if (target) {
    target.title = title;
  }
}

function updateMaterialBriefTitle(materialId, title) {
  Object.values(RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID).forEach((response) => {
    const rows = response?.materials ?? [];
    const target = rows.find((row) => row.material_id === materialId);
    if (target) {
      target.title = title;
    }
  });
}

function parseSyllabusStatusResponse(response) {
  return {
    isEduCalendarMissing: Boolean(response?.status?.is_edu_calendar_path_null),
    isDraftMissing: Boolean(response?.status?.is_syllabus_draft_path_null),
    isFinalMissing: Boolean(response?.status?.is_syllabus_path_null),
  };
}

function parseMaterialStatusResponse(response) {
  return {
    isDraftMissing: Boolean(response?.status?.is_material_draft_path_null),
    isFinalMissing: Boolean(response?.status?.is_material_path_null),
  };
}

function parseSyllabusListResponse(response) {
  const rows = Array.isArray(response?.syllabuses) ? response.syllabuses : [];

  return rows.map((row) => ({
    syllabusId: row.syllabus_id,
    title: row.title,
    permission: row.syllabus_permission,
    graphId: row.graph_id,
    graphName: row.graph_name,
    dayOneTime: row.day_one_time,
    eduCalendarPath: row.edu_calendar_path,
    draftPath: row.syllabus_draft_path,
    finalPath: row.syllabus_path,
  }));
}

function parseSyllabusDetailResponse(response) {
  return response?.syllabus ?? null;
}

function parseSyllabusDraftDetailResponse(response) {
  return response?.syllabus_draft ?? null;
}

function parseMaterialListResponse(response) {
  const rows = Array.isArray(response?.materials) ? response.materials : [];

  return rows.map((row) => ({
    materialId: row.material_id,
    fileId: row.file_id ?? null,
    title: row.title,
    draftPath: row.draft_path,
    finalPath: row.final_path,
    pdfPath: row.pdf_path,
    createTime: row.create_time,
  }));
}

function parseMaterialDetailResponse(response) {
  return response?.material ?? null;
}

function parseMaterialDraftResponse(response) {
  return response?.material_draft ?? null;
}

function parseSyllabusMutationResponse(response) {
  return {
    success: Boolean(response?.success),
    syllabusId: response?.syllabus?.syllabus_id ?? null,
    fileId: response?.file?.file_id ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

function parseGraphListResponse(response) {
  const rows = Array.isArray(response?.graphs) ? response.graphs : [];

  return rows.map((row) => ({
    graphId: row.graph_id,
    graphName: row.graph_name,
  }));
}

function parseGraphMutationResponse(response) {
  return {
    success: Boolean(response?.success),
    graphId: response?.graph?.graph_id ?? null,
    graphName: response?.graph?.graph_name ?? '',
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

function parseMaterialMutationResponse(response) {
  return {
    success: Boolean(response?.success),
    materialId: response?.material?.material_id ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

function createSuccessSyllabusMutation(syllabusId) {
  return {
    success: true,
    syllabus: { syllabus_id: syllabusId ?? null },
    error_message: '',
    error_code: '',
  };
}

function createSuccessMaterialMutation(materialId) {
  return {
    success: true,
    material: { material_id: materialId ?? null },
    error_message: '',
    error_code: '',
  };
}

function ensureSyllabusDraftJson(value) {
  return (
    value
    && typeof value === 'object'
    && !Array.isArray(value)
    && typeof value.title === 'string'
    && 'graph_name' in value
    && Array.isArray(value.period)
  );
}

function ensureSyllabusJson(value) {
  return (
    value
    && typeof value === 'object'
    && !Array.isArray(value)
    && typeof value.title === 'string'
    && 'graph_name' in value
    && typeof value.day_one === 'string'
    && Array.isArray(value.period)
  );
}

function ensureMaterialJson(value) {
  return (
    value
    && typeof value === 'object'
    && !Array.isArray(value)
    && typeof value.material_title === 'string'
    && Array.isArray(value.involved_weeks)
    && Array.isArray(value.questions)
  );
}

function mapGraphFiles(graphFiles, jobs) {
  return graphFiles.map((file) => {
    const job = jobs.find((item) => item.fileId === file.fileId) ?? null;

    return {
      fileId: file.fileId,
      title: file.title,
      source: file.source,
      weekLabel: file.weekIndexList.length ? `第 ${file.weekIndexList.join(', ')} 周` : '',
      tagText: job ? getJobLabel(job) : '',
      tagTone: job ? getJobTone(job.status) : 'neutral',
      job,
    };
  });
}

function mapMaterialShelf(syllabusFiles, graphFiles) {
  const syllabusItems = syllabusFiles.map((file) => ({
    fileId: file.fileId,
    title: file.title,
    source: file.source,
    weekLabel: file.weekIndexList.length ? `第 ${file.weekIndexList.join(', ')} 周` : '',
  }));

  return [...syllabusItems, ...graphFiles];
}

function createTeacherSyllabusBaseItem(item) {
  return {
    syllabusId: item.syllabusId,
    title: item.title,
    permission: item.permission,
    graphId: item.graphId,
    graphName: item.graphName,
    dayOneTime: item.dayOneTime,
    eduCalendarPath: item.eduCalendarPath ?? null,
    draftPath: item.draftPath ?? null,
    finalPath: item.finalPath ?? null,
    status: {
      isEduCalendarMissing: !item.eduCalendarPath,
      isDraftMissing: !item.draftPath,
      isFinalMissing: !item.finalPath,
    },
    draft: null,
    finalData: null,
    graphFiles: [],
    graphFileCount: 0,
    syllabusFiles: [],
    materialDrafts: [],
    materialShelf: [],
    isVisibleLoaded: false,
    isBuildLoaded: false,
    isMaterialDetailsLoaded: false,
  };
}

function normalizeTeacherSyllabusItem(item) {
  const base = createTeacherSyllabusBaseItem(item);

  return {
    ...base,
    ...item,
    status: item?.status ?? base.status,
    graphFiles: item?.graphFiles ?? base.graphFiles,
    materialDrafts: item?.materialDrafts ?? base.materialDrafts,
    syllabusFiles: item?.syllabusFiles ?? base.syllabusFiles,
    materialShelf: item?.materialShelf ?? base.materialShelf,
  };
}

async function reuseInflight(map, key, factory) {
  if (map.has(key)) {
    return map.get(key);
  }

  const promise = (async () => factory())().finally(() => {
    map.delete(key);
  });
  map.set(key, promise);
  return promise;
}

async function buildTeacherSyllabusVisibleData(item) {
  const status = parseSyllabusStatusResponse(await getSyllabusStatusRaw(item.syllabusId));
  const finalData = item.finalPath ? parseSyllabusDetailResponse(await getSyllabusDetailRaw(item.syllabusId)) : null;
  const rawGraphFiles = await listGraphFiles(item.graphId ? [item.graphId] : []);
  const jobs = item.graphId ? await listJobs(item.graphId) : [];
  const graphFiles = mapGraphFiles(rawGraphFiles, jobs);
  const materialList = parseMaterialListResponse(await listMaterialsRaw(item.syllabusId));
  const materialStatuses = await Promise.all(
    materialList.map(async (material) => parseMaterialStatusResponse(await getMaterialStatusRaw(material.materialId))),
  );
  const materialDrafts = materialList.map((material, index) => ({
    ...material,
    draft: null,
    finalData: null,
    status: materialStatuses[index],
  }));

  return {
    title: finalData?.title ?? item.title,
    graphName: finalData?.graph_name ?? item.graphName,
    status,
    finalData,
    graphFiles,
    graphFileCount: rawGraphFiles.length,
    materialDrafts,
    materialShelf: mapMaterialShelf([], graphFiles),
    isVisibleLoaded: true,
  };
}

async function buildTeacherSyllabusBuildData(item) {
  const status = parseSyllabusStatusResponse(await getSyllabusStatusRaw(item.syllabusId));
  const draft = item.draftPath ? parseSyllabusDraftDetailResponse(await getSyllabusDraftDetailRaw(item.syllabusId)) : null;
  const finalData = item.finalPath ? parseSyllabusDetailResponse(await getSyllabusDetailRaw(item.syllabusId)) : null;

  return {
    title: finalData?.title ?? draft?.title ?? item.title,
    graphName: finalData?.graph_name ?? draft?.graph_name ?? item.graphName,
    status,
    draft,
    finalData,
    isBuildLoaded: true,
  };
}

async function buildTeacherSyllabusMaterialDetails(item) {
  const syllabusFiles = await listSyllabusFiles([item.syllabusId]);
  const materialList = parseMaterialListResponse(await listMaterialsRaw(item.syllabusId));
  const materialDrafts = await Promise.all(
    materialList.map(async (material) => ({
      ...material,
      draft: parseMaterialDraftResponse(await getMaterialDraftDetailRaw(material.materialId)),
      finalData: material.finalPath ? parseMaterialDetailResponse(await getMaterialDetailRaw(material.materialId)) : null,
      status: parseMaterialStatusResponse(await getMaterialStatusRaw(material.materialId)),
    })),
  );

  return {
    syllabusFiles,
    materialDrafts,
    materialShelf: mapMaterialShelf(syllabusFiles, item.graphFiles ?? []),
    isMaterialDetailsLoaded: true,
  };
}

export async function listSyllabusesRaw(payload = {}) {
  const userId = requireUserId({ ...payload, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_list', {
      user_id: userId,
      manage: payload.manage ?? true,
    });
  }

  return cloneData(RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7);
}

export async function getSyllabusDetailRaw(syllabusId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_detail', { syllabus_id: syllabusId });
  }
  return cloneData(mockSyllabusDetailResponseById[syllabusId]);
}

export async function getSyllabusDraftDetailRaw(syllabusId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_draft_detail', { syllabus_id: syllabusId });
  }
  return cloneData(mockSyllabusDraftDetailResponseById[syllabusId]);
}

export async function getSyllabusStatusRaw(syllabusId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_status', { syllabus_id: syllabusId });
  }
  return cloneData(RAW_GET_SYLLABUS_STATUS_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW[syllabusId]);
}

export async function listMaterialsRaw(syllabusId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_material_list', { syllabus_id: syllabusId });
  }
  return cloneData(RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID[syllabusId] ?? { success: true, materials: [] });
}

export async function getMaterialDraftDetailRaw(materialId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_material_draft_detail', { material_id: materialId });
  }
  return cloneData(mockMaterialDraftDetailResponseById[materialId] ?? { success: true, material_draft: null });
}

export async function getMaterialDetailRaw(materialId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_material_detail', { material_id: materialId });
  }
  return cloneData(mockMaterialDetailResponseById[materialId] ?? { success: true, material: null });
}

export async function getMaterialStatusRaw(materialId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_material_status', { material_id: materialId });
  }

  return cloneData(
    RAW_GET_MATERIAL_STATUS_RESPONSE_BY_MATERIAL_ID[materialId] ?? {
      success: true,
      status: {
        is_material_draft_path_null: true,
        is_material_path_null: true,
      },
      error_message: '',
      error_code: '',
    },
  );
}

export async function getTeacherDashboardData() {
  const bootstrap = await getTeacherDashboardBootstrapData();

  const syllabuses = await Promise.all(
    bootstrap.syllabuses.map(async (item) => {
      const visibleData = await getTeacherSyllabusVisibleData(item);
      const buildData = await getTeacherSyllabusBuildData({ ...item, ...visibleData });
      const materialData = await getTeacherSyllabusMaterialDetails({ ...item, ...visibleData, ...buildData });

      return {
        ...item,
        ...visibleData,
        ...buildData,
        ...materialData,
      };
    }),
  );

  return { syllabuses };
}

export async function getTeacherDashboardBootstrapData() {
  const syllabusList = parseSyllabusListResponse(await listSyllabusesRaw());
  return {
    syllabuses: syllabusList.map(createTeacherSyllabusBaseItem),
  };
}

export async function getTeacherSyllabusVisibleData(syllabus) {
  const normalized = normalizeTeacherSyllabusItem(syllabus);
  return reuseInflight(
    teacherVisibleInflight,
    normalized.syllabusId,
    () => buildTeacherSyllabusVisibleData(normalized),
  );
}

export async function getTeacherSyllabusBuildData(syllabus) {
  const normalized = normalizeTeacherSyllabusItem(syllabus);
  return reuseInflight(
    teacherBuildInflight,
    normalized.syllabusId,
    () => buildTeacherSyllabusBuildData(normalized),
  );
}

export async function getTeacherSyllabusMaterialDetails(syllabus) {
  const normalized = normalizeTeacherSyllabusItem(syllabus);
  return reuseInflight(
    teacherMaterialInflight,
    normalized.syllabusId,
    () => buildTeacherSyllabusMaterialDetails(normalized),
  );
}

export async function listGraphsRaw() {
  if (!USE_MOCK_API) {
    return apiGet('/api/job_graph_list');
  }

  return cloneData({
    success: true,
    graphs: mockGraphStore,
    error_message: '',
    error_code: '',
  });
}

export async function createGraphRaw(payload = {}) {
  const graphName = String(payload.graphName ?? '').trim();

  if (!graphName) {
    return {
      success: false,
      graph: null,
      error_message: 'graph_name_required',
      error_code: 'graph_name_required',
    };
  }

  if (!USE_MOCK_API) {
    return apiPost('/api/job_graph_create', { graph_name: graphName });
  }

  const existing = mockGraphStore.find((item) => item.graph_name === graphName);
  if (existing) {
    return {
      success: true,
      graph: existing,
      error_message: '',
      error_code: '',
    };
  }

  const nextId = Math.max(0, ...mockGraphStore.map((item) => item.graph_id)) + 1;
  const graph = {
    graph_id: nextId,
    graph_name: graphName,
  };

  mockGraphStore = [...mockGraphStore, graph];

  return {
    success: true,
    graph,
    error_message: '',
    error_code: '',
  };
}

export async function listGraphs() {
  return parseGraphListResponse(await listGraphsRaw());
}

export async function createGraph(payload = {}) {
  return parseGraphMutationResponse(await createGraphRaw(payload));
}

export async function uploadCalendar(payload = {}) {
  if (!USE_MOCK_API) {
    const file = payload.file ?? payload.files?.[0] ?? null;
    if (!file && !(payload.fileName || payload.file_name) && !(payload.fileBytes || payload.file_bytes)) {
      return {
        success: false,
        file: null,
        syllabus: null,
        error_message: 'missing calendar file',
        error_code: 'missing_fields',
      };
    }

    const request = file
      ? await fileToUploadPayload(file, payload)
      : {
          file_name: payload.fileName ?? payload.file_name,
          file_bytes: payload.fileBytes ?? payload.file_bytes,
          upload_time: payload.uploadTime ?? payload.upload_time,
        };

    return parseSyllabusMutationResponse(await apiPost('/api/file_upload_calendar', request));
  }

  mockUploadedSyllabusIdSeed += 1;

  return parseSyllabusMutationResponse({
    success: true,
    file: { file_id: 901 },
    syllabus: { syllabus_id: mockUploadedSyllabusIdSeed },
    error_message: '',
    error_code: '',
  });
}

export async function buildSyllabusDraft(payload = {}) {
  if (!USE_MOCK_API) {
    return parseSyllabusMutationResponse(await apiPost('/api/syllabus_build_draft', {
      syllabus_id: payload.syllabusId ?? payload.syllabus_id,
      graph_id: payload.graphId ?? payload.graph_id,
      initial_prompt: payload.initialPrompt ?? payload.initial_prompt ?? '',
    }));
  }

  return parseSyllabusMutationResponse(createSuccessSyllabusMutation(payload.syllabusId ?? null));
}

export async function updateSyllabusDraft(payload = {}) {
  const syllabusId = payload.syllabusId ?? null;
  const syllabusDraftJson = payload.syllabusDraftJson;

  if (!syllabusId || !ensureSyllabusDraftJson(syllabusDraftJson)) {
    return parseSyllabusMutationResponse({
      success: false,
      syllabus: null,
      error_message: 'invalid_syllabus_draft_json',
      error_code: 'invalid_fields',
    });
  }

  if (!USE_MOCK_API) {
    return parseSyllabusMutationResponse(await apiPost('/api/syllabus_update_draft', {
      syllabus_id: syllabusId,
      syllabus_draft_json: syllabusDraftJson,
    }));
  }

  mockSyllabusDraftDetailResponseById[syllabusId] = {
    success: true,
    syllabus_draft: cloneData(syllabusDraftJson),
    error_message: '',
    error_code: '',
  };
  updateManageSyllabusTitle(syllabusId, syllabusDraftJson.title);

  return parseSyllabusMutationResponse(createSuccessSyllabusMutation(syllabusId));
}

export async function buildSyllabus(payload = {}) {
  const syllabusId = payload.syllabusId ?? null;

  if (!USE_MOCK_API) {
    return parseSyllabusMutationResponse(await apiPost('/api/syllabus_build', {
      syllabus_id: syllabusId,
    }));
  }

  const draftPayload = mockSyllabusDraftDetailResponseById[syllabusId]?.syllabus_draft ?? null;

  if (syllabusId && draftPayload && Array.isArray(draftPayload.period)) {
    mockSyllabusDetailResponseById[syllabusId] = {
      success: true,
      syllabus: {
        title: draftPayload.title,
        day_one: '2026-03-02',
        graph_name: draftPayload.graph_name,
        period: draftPayload.period.map((item) => ({
          ...cloneData(item),
          original_content: item.content ?? '',
          enhanced_content: item.content ?? '',
        })),
      },
      error_message: '',
      error_code: '',
    };
  }

  return parseSyllabusMutationResponse(createSuccessSyllabusMutation(syllabusId));
}

export async function updateSyllabus(payload = {}) {
  const syllabusId = payload.syllabusId ?? null;
  const syllabusJson = payload.syllabusJson;

  if (!syllabusId || !ensureSyllabusJson(syllabusJson)) {
    return parseSyllabusMutationResponse({
      success: false,
      syllabus: null,
      error_message: 'invalid_syllabus_json',
      error_code: 'invalid_fields',
    });
  }

  if (!USE_MOCK_API) {
    return parseSyllabusMutationResponse(await apiPost('/api/syllabus_update', {
      syllabus_id: syllabusId,
      syllabus_json: syllabusJson,
    }));
  }

  mockSyllabusDetailResponseById[syllabusId] = {
    success: true,
    syllabus: cloneData(syllabusJson),
    error_message: '',
    error_code: '',
  };
  updateManageSyllabusTitle(syllabusId, syllabusJson.title);

  return parseSyllabusMutationResponse(createSuccessSyllabusMutation(syllabusId));
}

export async function generateMaterialDraft(payload = {}) {
  if (!USE_MOCK_API) {
    return parseMaterialMutationResponse(await apiPost('/api/syllabus_material_generate_draft', {
      syllabus_id: payload.syllabusId ?? payload.syllabus_id,
      involved_weeks: payload.involvedWeeks ?? payload.involved_weeks,
      question_type_distribution: payload.questionTypeDistribution ?? payload.question_type_distribution,
    }));
  }

  const nextMaterialId = Math.max(
    0,
    ...Object.values(RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID)
      .flatMap((response) => response?.materials ?? [])
      .map((row) => row.material_id ?? 0),
  ) + 1;
  const syllabusId = payload.syllabusId ?? payload.syllabus_id;
  const materialDraft = {
    material_title: `material_${nextMaterialId}`,
    involved_weeks: cloneData(payload.involvedWeeks ?? payload.involved_weeks ?? []),
    questions: [],
  };

  if (!RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID[syllabusId]) {
    RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID[syllabusId] = {
      success: true,
      materials: [],
      error_message: '',
      error_code: '',
    };
  }
  RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID[syllabusId].materials.unshift({
    material_id: nextMaterialId,
    title: materialDraft.material_title,
    draft_path: `./material/draft_material_json/material_${nextMaterialId}.json`,
    final_path: null,
    pdf_path: null,
    create_time: new Date().toISOString(),
  });
  mockMaterialDraftDetailResponseById[nextMaterialId] = {
    success: true,
    material_draft: materialDraft,
    error_message: '',
    error_code: '',
  };

  return parseMaterialMutationResponse({
    success: true,
    material: { material_id: nextMaterialId },
    error_message: '',
    error_code: '',
  });
}

export async function updateMaterialDraft(payload = {}) {
  const materialId = payload.materialId ?? null;
  const materialDraftJson = payload.materialDraftJson;

  if (!materialId || !ensureMaterialJson(materialDraftJson)) {
    return parseMaterialMutationResponse({
      success: false,
      material: null,
      error_message: 'invalid_material_draft_json',
      error_code: 'invalid_fields',
    });
  }

  if (!USE_MOCK_API) {
    return parseMaterialMutationResponse(await apiPost('/api/syllabus_material_update_draft', {
      material_id: materialId,
      material_draft_json: materialDraftJson,
    }));
  }

  mockMaterialDraftDetailResponseById[materialId] = {
    success: true,
    material_draft: cloneData(materialDraftJson),
    error_message: '',
    error_code: '',
  };
  updateMaterialBriefTitle(materialId, materialDraftJson.material_title);

  return parseMaterialMutationResponse(createSuccessMaterialMutation(materialId));
}

export async function generateFinalMaterial(payload = {}) {
  if (!USE_MOCK_API) {
    return parseMaterialMutationResponse(await apiPost('/api/syllabus_material_generate_final', {
      material_id: payload.materialId ?? payload.material_id,
    }));
  }

  return parseMaterialMutationResponse({
    success: true,
    material: { material_id: payload.materialId ?? null },
    error_message: '',
    error_code: '',
  });
}

export async function updateFinalMaterial(payload = {}) {
  const materialId = payload.materialId ?? null;
  const materialJson = payload.materialJson;

  if (!materialId || !ensureMaterialJson(materialJson)) {
    return parseMaterialMutationResponse({
      success: false,
      material: null,
      error_message: 'invalid_material_json',
      error_code: 'invalid_fields',
    });
  }

  if (!USE_MOCK_API) {
    return parseMaterialMutationResponse(await apiPost('/api/syllabus_material_update', {
      material_id: materialId,
      material_json: materialJson,
    }));
  }

  mockMaterialDetailResponseById[materialId] = {
    success: true,
    material: cloneData(materialJson),
    error_message: '',
    error_code: '',
  };
  updateMaterialBriefTitle(materialId, materialJson.material_title);

  return parseMaterialMutationResponse(createSuccessMaterialMutation(materialId));
}

export async function publishMaterial(payload = {}) {
  if (!USE_MOCK_API) {
    return parseMaterialMutationResponse(await apiPost('/api/syllabus_material_publish', {
      material_id: payload.materialId ?? payload.material_id,
      new_pdf: payload.newPdf ?? payload.new_pdf,
      do_publish: payload.doPublish ?? payload.do_publish,
    }));
  }

  return parseMaterialMutationResponse({
    success: true,
    material: { material_id: payload.materialId ?? null },
    error_message: '',
    error_code: '',
  });
}

export {
  parseGraphListResponse,
  parseGraphMutationResponse,
  parseMaterialDetailResponse,
  parseMaterialDraftResponse,
  parseMaterialListResponse,
  parseMaterialMutationResponse,
  parseMaterialStatusResponse,
  parseSyllabusDraftDetailResponse,
  parseSyllabusDetailResponse,
  parseSyllabusListResponse,
  parseSyllabusMutationResponse,
  parseSyllabusStatusResponse,
};
