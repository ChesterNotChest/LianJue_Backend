import {
  RAW_ASK_QUESTION_RESPONSE_FOR_USER_7_SYLLABUS_1,
  RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7,
  RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_LEARNING_RESPONSE_FOR_USER_7,
} from './mock_payloads';
import { USE_MOCK_API, apiPost } from './client';
import { getFileDetail, listSyllabusFiles } from './file_transmit_api';
import { getCurrentUserId, requireUserId } from './session';

const RECOMMENDATION_STORAGE_PREFIX = 'student_recommendations_v1';
const RECOMMENDATION_EXPIRE_ASKS = 5;

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function parseStudentSyllabusListResponse(response) {
  const rows = Array.isArray(response?.syllabuses) ? response.syllabuses : [];

  return rows.map((row) => ({
    syllabusId: row.syllabus_id,
    title: row.title,
    isLearning: Boolean(row.isLearning),
    personalSyllabusPath: row.personal_syllabus_path,
    dayOneTime: row.day_one_time,
  }));
}

function parsePersonalSyllabusResponse(response) {
  return response?.syllabus ?? response?.personal_syllabus ?? null;
}

function parseAskQuestionResponse(response) {
  return {
    answer: response?.answer ?? '',
    matchedFiles: Array.isArray(response?.matched_files) ? response.matched_files : [],
    competanceList: Array.isArray(response?.competance_list) ? response.competance_list : [],
    raw: response?.raw ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

function parseInitPersonalSyllabusResponse(response) {
  return {
    success: Boolean(response?.success),
    syllabusId: response?.syllabus?.syllabus_id ?? null,
    personalSyllabusPath: response?.syllabus?.personal_syllabus_path ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

function parseUpdatePersonalSyllabusResponse(response) {
  return {
    success: Boolean(response?.success),
    syllabus: response?.syllabus ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

function formatWeekLabel(weekIndexList = []) {
  return weekIndexList.length ? `week ${weekIndexList.join(', ')}` : '';
}

function buildRecommendationItems(files, options = {}) {
  const matchedIds = Array.isArray(options.matchedIds) ? options.matchedIds : null;
  const weekIndexes = Array.isArray(options.weekIndexes) ? options.weekIndexes : null;

  return files
    .filter((file) => {
      if (matchedIds?.length) {
        return matchedIds.includes(file.fileId);
      }
      if (weekIndexes?.length) {
        return file.weekIndexList.some((weekIndex) => weekIndexes.includes(Number(weekIndex)));
      }
      return true;
    })
    .map((file) => ({
      fileId: file.fileId,
      title: file.title,
      source: file.source,
      weekLabel: formatWeekLabel(file.weekIndexList),
    }));
}

function normalizeRecommendationKey(value) {
  if (typeof value !== 'string') {
    return '';
  }

  return value
    .trim()
    .replace(/^[\s\[({]+|[\s\])}]+$/g, '')
    .replace(/\.[^.]+$/, '')
    .toLowerCase()
    .replace(/[\s_\-+./()[\]{}]+/g, '');
}

function buildRecommendationItemsByDocumentNames(files, documentNames = []) {
  const normalizedFiles = files.map((file) => ({
    ...file,
    normalizedTitle: normalizeRecommendationKey(file.title),
    normalizedPath: normalizeRecommendationKey(file.path),
  }));

  const items = [];
  const seen = new Set();

  documentNames.forEach((name) => {
    const normalizedName = normalizeRecommendationKey(name);
    if (!normalizedName) {
      return;
    }

    const matchedFile = normalizedFiles.find((file) => (
      normalizedName === file.normalizedTitle
      || normalizedName === file.normalizedPath
      || file.normalizedTitle.includes(normalizedName)
      || normalizedName.includes(file.normalizedTitle)
      || file.normalizedPath.includes(normalizedName)
    ));

    if (!matchedFile) {
      return;
    }

    const dedupeKey = matchedFile.fileId ?? matchedFile.title;
    if (seen.has(dedupeKey)) {
      return;
    }
    seen.add(dedupeKey);
    items.push({
      fileId: matchedFile.fileId,
      title: matchedFile.title,
      source: matchedFile.source,
      weekLabel: formatWeekLabel(matchedFile.weekIndexList),
    });
  });

  return items;
}

function mergeRecommendationItems(...groups) {
  const merged = [];
  const seen = new Set();

  groups.flat().forEach((item) => {
    if (!item) {
      return;
    }
    const dedupeKey = item.fileId ?? item.title;
    if (dedupeKey == null || seen.has(dedupeKey)) {
      return;
    }
    seen.add(dedupeKey);
    merged.push(item);
  });

  return merged;
}

function getRecommendationStorageKey(userId, syllabusId) {
  return `${RECOMMENDATION_STORAGE_PREFIX}:${userId}:${syllabusId}`;
}

function loadRecommendationMemory(userId, syllabusId) {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(getRecommendationStorageKey(userId, syllabusId));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveRecommendationMemory(userId, syllabusId, items) {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(getRecommendationStorageKey(userId, syllabusId), JSON.stringify(items));
}

function updateRecommendationMemory(userId, syllabusId, currentItems) {
  const previousItems = loadRecommendationMemory(userId, syllabusId);
  const nextItems = [];
  const currentMap = new Map();

  currentItems.forEach((item) => {
    const key = item.fileId ?? item.title;
    if (key == null) {
      return;
    }
    currentMap.set(key, item);
  });

  previousItems.forEach((stored) => {
    const key = stored.fileId ?? stored.title;
    if (key == null) {
      return;
    }

    if (currentMap.has(key)) {
      nextItems.push({
        ...currentMap.get(key),
        staleAskCount: 0,
      });
      currentMap.delete(key);
      return;
    }

    const staleAskCount = Number(stored.staleAskCount ?? 0) + 1;
    if (staleAskCount < RECOMMENDATION_EXPIRE_ASKS) {
      nextItems.push({
        ...stored,
        staleAskCount,
      });
    }
  });

  Array.from(currentMap.values()).reverse().forEach((item) => {
    nextItems.unshift({
      ...item,
      staleAskCount: 0,
    });
  });

  saveRecommendationMemory(userId, syllabusId, nextItems);
  return nextItems.map(({ staleAskCount, ...item }) => item);
}

async function buildRecommendationItemsByFileIds(fileIds = [], syllabusFiles = []) {
  const dedupedIds = Array.from(new Set(
    (Array.isArray(fileIds) ? fileIds : [])
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value)),
  ));

  if (!dedupedIds.length) {
    return [];
  }

  const fileDetails = await Promise.all(dedupedIds.map(async (fileId) => {
    try {
      return await getFileDetail(fileId);
    } catch {
      return null;
    }
  }));

  return fileDetails
    .filter(Boolean)
    .map((file) => {
      const meta = syllabusFiles.find((item) => item.fileId === file.fileId);
      return {
        fileId: file.fileId,
        title: file.title,
        source: meta?.source ?? 'related-file',
        weekLabel: formatWeekLabel(meta?.weekIndexList ?? []),
      };
    });
}

function pickDefaultWeeks(personalSyllabus) {
  const period = Array.isArray(personalSyllabus?.period) ? personalSyllabus.period : [];
  const weakWeeks = period.filter((item) => item.competance === 'weak').map((item) => Number(item.week_index));

  if (weakWeeks.length) {
    return weakWeeks;
  }

  const noneWeeks = period.filter((item) => item.competance === 'none').map((item) => Number(item.week_index));
  return noneWeeks.length ? [noneWeeks[0]] : [];
}

function applyStudyHours(personalSyllabus, weekIndex, studyTimeSpent) {
  const next = cloneData(personalSyllabus);
  const target = (next?.period ?? []).find((item) => String(item.week_index) === String(weekIndex));

  if (!target) {
    return next;
  }

  const hours = Number(studyTimeSpent) || 0;
  let increment = 0;

  if (hours === 1) {
    increment = 2;
  } else if (hours === 2) {
    increment = 4;
  } else if (hours >= 3) {
    increment = 5;
  }

  let progress = Number(target.competance_progress ?? 0) + increment;
  let level = target.competance ?? 'normal';

  if (progress >= 5) {
    if (level === 'weak') {
      level = 'normal';
    } else if (level === 'normal') {
      level = 'master';
    }
    progress = 0;
  } else if (progress <= -5) {
    if (level === 'master') {
      level = 'normal';
    } else if (level === 'normal') {
      level = 'weak';
    }
    progress = 0;
  }

  target.competance = level;
  target.competance_progress = progress;
  target.updated_at = 1775700000;
  next.reviewed_at = 1775700000;

  return next;
}

export async function listStudentSyllabusesRaw(payload = {}) {
  const userId = requireUserId({ ...payload, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/syllabus_list', {
      user_id: userId,
      manage: false,
    });
  }

  return cloneData(RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_LEARNING_RESPONSE_FOR_USER_7);
}

export async function getPersonalSyllabusRaw(syllabusId, userId = null) {
  const resolvedUserId = requireUserId({ userId, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/learning_personal_syllabus_detail', {
      user_id: resolvedUserId,
      syllabus_id: syllabusId,
    });
  }

  return cloneData(RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7[syllabusId]);
}

export async function askQuestionRaw(payload = {}) {
  const userId = requireUserId({ ...payload, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/learning_ask_question', {
      user_id: userId,
      syllabus_id: payload.syllabusId ?? payload.syllabus_id,
      question: payload.question ?? '',
    });
  }

  return {
    ...cloneData(RAW_ASK_QUESTION_RESPONSE_FOR_USER_7_SYLLABUS_1),
    request: {
      user_id: userId,
      syllabus_id: payload.syllabusId ?? null,
      question: payload.question ?? '',
    },
  };
}

function parseLearningProfileResponse(response) {
  return {
    success: Boolean(response?.success),
    profile: response?.profile ?? response?.learning_profile ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

export async function getLearningProfileRaw(payload = {}) {
  const userId = requireUserId({ ...payload, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/user_learning_profile', {
      user_id: userId,
      syllabus_id: payload.syllabusId ?? payload.syllabus_id ?? null,
      dialogue_text: payload.dialogueText ?? payload.dialogue_text ?? null,
    });
  }

  return {
    success: true,
    profile: {
      user_id: userId,
      learning_goal: '未提供',
      knowledge_mastery: {},
    },
    error_message: '',
    error_code: '',
  };
}

export async function getLearningProfile(payload = {}) {
  const parsed = parseLearningProfileResponse(await getLearningProfileRaw(payload));
  return parsed;
}

export async function initPersonalSyllabusRaw(payload = {}) {
  const userId = requireUserId({ ...payload, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/learning_init_personal_syllabus', {
      user_id: userId,
      syllabus_id: payload.syllabusId ?? payload.syllabus_id,
    });
  }

  return {
    success: true,
    syllabus: {
      syllabus_id: payload.syllabusId ?? null,
      user_id: userId,
      personal_syllabus_path: `./schedule/student_alt/user_${userId}/${payload.syllabusId ?? 0}_personal.json`,
    },
    error_message: '',
    error_code: '',
  };
}

export async function updatePersonalSyllabusRaw(payload = {}) {
  const userId = requireUserId({ ...payload, allowMockFallback: USE_MOCK_API });
  if (!USE_MOCK_API) {
    return apiPost('/api/learning_update_personal_syllabus', {
      user_id: userId,
      syllabus_id: payload.syllabusId ?? payload.syllabus_id,
      week_index: payload.weekIndex ?? payload.week_index,
      study_time_spent: payload.studyTimeSpent ?? payload.study_time_spent,
    });
  }

  const source = cloneData(
    RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7[payload.syllabusId]?.syllabus
      ?? RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7[1]?.syllabus
      ?? null,
  );
  const updated = source ? applyStudyHours(source, payload.weekIndex, payload.studyTimeSpent) : null;

  return {
    success: Boolean(updated),
    syllabus: updated,
    request: payload,
    error_message: updated ? '' : 'not_found',
    error_code: updated ? '' : 'not_found',
  };
}

export async function getStudentDashboardData() {
  const list = parseStudentSyllabusListResponse(await listStudentSyllabusesRaw());

  const syllabuses = await Promise.all(
    list.map(async (item) => {
      const personal = item.personalSyllabusPath ? parsePersonalSyllabusResponse(await getPersonalSyllabusRaw(item.syllabusId)) : null;
      const syllabusFiles = await listSyllabusFiles([item.syllabusId]);
      const defaultWeeks = pickDefaultWeeks(personal);

      return {
        syllabusId: item.syllabusId,
        title: item.title,
        isLearning: item.isLearning,
        dayOneTime: item.dayOneTime,
        personalSyllabus: personal,
        syllabusFiles,
        defaultRecommendations: buildRecommendationItems(syllabusFiles, { weekIndexes: defaultWeeks }),
      };
    }),
  );

  return { syllabuses };
}

export async function initPersonalSyllabus(payload = {}) {
  return parseInitPersonalSyllabusResponse(await initPersonalSyllabusRaw(payload));
}

export async function getPersonalSyllabus(payload = {}) {
  return parsePersonalSyllabusResponse(await getPersonalSyllabusRaw(
    payload.syllabusId ?? payload.syllabus_id,
    payload.userId ?? payload.user_id ?? null,
  ));
}

export async function updatePersonalSyllabus(payload = {}) {
  return parseUpdatePersonalSyllabusResponse(await updatePersonalSyllabusRaw(payload));
}

export async function askQuestion(payload = {}) {
  const parsed = parseAskQuestionResponse(await askQuestionRaw(payload));
  const syllabusFiles = payload.syllabusId ? await listSyllabusFiles([payload.syllabusId]) : [];
  const rawDocumentNames = Array.isArray(parsed.raw?.document_names) ? parsed.raw.document_names : [];

  const fileIdRecommendationItems = await buildRecommendationItemsByFileIds(parsed.matchedFiles, syllabusFiles);
  const documentNameRecommendationItems = buildRecommendationItemsByDocumentNames(syllabusFiles, rawDocumentNames);
  const mergedRecommendationItems = mergeRecommendationItems(fileIdRecommendationItems, documentNameRecommendationItems);

  const userId = getCurrentUserId();
  const rememberedRecommendationItems = payload.syllabusId && userId
    ? updateRecommendationMemory(userId, payload.syllabusId, mergedRecommendationItems)
    : mergedRecommendationItems;

  return {
    ...parsed,
    recommendedMaterials: rememberedRecommendationItems,
  };
}

export {
  parseAskQuestionResponse,
  parseInitPersonalSyllabusResponse,
  parsePersonalSyllabusResponse,
  parseStudentSyllabusListResponse,
  parseUpdatePersonalSyllabusResponse,
};
