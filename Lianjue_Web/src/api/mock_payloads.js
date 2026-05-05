const BASE_PERIOD = [
  { week_index: '1', content: '课程导论、课程目标、考核方式与核心概念。', importance: 'low', day_one: '3-2' },
  { week_index: '2', content: '大数据定义、特征、生命周期与应用场景。', importance: 'medium' },
  { week_index: '3', content: '数据来源、多源异构与数据采集基础。', importance: 'medium' },
  { week_index: '4', content: 'ETL 流程、数据抽取策略与常见采集工具。', importance: 'medium' },
  { week_index: '5', content: '分布式文件系统与 HDFS。', importance: 'high' },
  { week_index: '6', content: 'NoSQL 与 HBase。', importance: 'high' },
  { week_index: '7', content: '关系型数据库与非关系型数据库对比。', importance: 'medium' },
  { week_index: '8', content: '特征表示、特征提取与建模方法。', importance: 'high' },
  { week_index: '9', content: '关联规则挖掘与常用算法。', importance: 'high' },
  { week_index: '10', content: '常用数据挖掘算法实践。', importance: 'high' },
  { week_index: '11', content: '大数据可视化方法与技术。', importance: 'medium' },
  { week_index: '12', content: 'MapReduce 与 Spark。', importance: 'high' },
  { week_index: '13', content: 'GPU、TPU、FPGA 与计算加速。', importance: 'high' },
  { week_index: '14', content: '大数据安全与隐私保护。', importance: 'medium' },
  { week_index: '15', content: '大数据在行业中的应用。', importance: 'medium' },
  { week_index: '16', content: '行业案例分析与课程总结。', importance: 'medium' },
];

const RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA = {
  title: 'Big Data Overview',
  graph_name: 'RAG',
  period: BASE_PERIOD.map((item) => ({ ...item })),
};

const RAW_GET_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_BIG_DATA = {
  title: 'Big Data Overview',
  day_one: '2026-03-02',
  graph_name: 'RAG',
  period: BASE_PERIOD.map((item) => ({
    ...item,
    original_content: item.content,
    enhanced_content: `${item.content} (enhanced for final syllabus editing)`,
  })),
};

const RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA = {
  material_title: '大数据概论_20260402223302',
  involved_weeks: [4],
  questions: [
    { type: 'single', question_index: 1, related_knowledge: '数据抽取、转换和装载（ETL）流程', query_key: 'ETL 流程' },
    { type: 'single', question_index: 2, related_knowledge: '常见的数据采集工具与技术', query_key: '采集工具' },
    { type: 'judge', question_index: 3, related_knowledge: '数据感知强调对数据的理解和解释', query_key: '数据感知' },
    { type: 'judge', question_index: 4, related_knowledge: '这些技术和方法在多行业中的应用', query_key: '行业应用' },
    { type: 'short', question_index: 5, related_knowledge: '大数据感知与获取的过程及应用', query_key: '大数据感知与获取' },
  ],
};

const RAW_GET_MATERIAL_DETAIL_INFO_OUTPUT_JSON_BIG_DATA = {
  material_title: '大数据概论_20260402223302',
  involved_weeks: [4],
  questions: [
    {
      type: 'single',
      question_index: 1,
      related_knowledge: '数据抽取、转换和装载（ETL）流程',
      query_key: 'ETL 流程',
      question_content: '在大数据感知与获取中，哪一过程负责将原始数据转化为结构化信息？',
      options: { A: 'ETL', B: 'OCR', C: 'API', D: 'NLP' },
      answer: 'A',
      reason: 'ETL 负责抽取、转换和装载，是原始数据进入分析链路的核心步骤。',
    },
    {
      type: 'single',
      question_index: 2,
      related_knowledge: '常见的数据采集工具与技术',
      query_key: '采集工具',
      question_content: '下列哪一项不是典型的数据采集工具？',
      options: { A: 'Apache Nifi', B: 'Flume', C: 'Hadoop', D: 'Kafka' },
      answer: 'C',
      reason: 'Hadoop 更偏向存储和计算框架，而不是专门的数据采集工具。',
    },
    {
      type: 'judge',
      question_index: 3,
      related_knowledge: '数据感知强调对数据的理解和解释',
      query_key: '数据感知',
      question_content: '数据感知阶段包含数据清洗、预处理和特征提取。',
      answer: true,
      reason: '这些步骤共同决定后续建模与分析的可用性。',
    },
    {
      type: 'judge',
      question_index: 4,
      related_knowledge: '这些技术和方法在多行业中的应用',
      query_key: '行业应用',
      question_content: '数据驱动的决策和优化方法已经在物流、交通等行业中广泛应用。',
      answer: true,
      reason: '课程案例明确覆盖了多个行业中的典型应用场景。',
    },
    {
      type: 'short',
      question_index: 5,
      related_knowledge: '大数据感知与获取的过程及应用',
      query_key: '大数据感知与获取',
      question_content: '简述大数据感知与获取的主要过程及其应用。',
      answer:
        '大数据感知与获取包括从多源数据中采集原始信息，经由 ETL 完成转换与装载，再进行清洗和预处理，最终支撑分析、决策与行业应用。',
      reason: '回答覆盖数据来源、ETL、预处理和应用四个核心点。',
    },
  ],
};

const RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_FOR_USER_7_SYLLABUS_1 = {
  syllabus_id: 1,
  user_id: 7,
  review_count: 2,
  reviewed_at: 1775600000,
  period: RAW_GET_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_BIG_DATA.period.map((item, index) => ({
    week_index: item.week_index,
    content: item.enhanced_content,
    enhanced_content: item.enhanced_content,
    importance: item.importance,
    competance: index === 0 ? 'master' : index <= 2 ? 'normal' : index === 3 ? 'weak' : 'none',
    competance_progress: index === 0 ? 3 : index <= 2 ? 1 : index === 3 ? -2 : 0,
    suggested_competance_list: [],
    updated_at: 1775600000,
  })),
};

const RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_GRAPH_ID = {
  1: {
    success: true,
    files: [
      { file_id: 201, filename: '大数据概论教学日历.pdf', path: './schedule/calendar/bigdata_calendar.pdf', source: 'graph-file', week_index_list: [1, 2, 3, 4] },
      { file_id: 202, filename: 'ETL 流程.pdf', path: './graph/etl.pdf', source: 'graph-file', week_index_list: [4] },
      { file_id: 203, filename: '采集工具.pdf', path: './graph/tools.pdf', source: 'graph-file', week_index_list: [4] },
      { file_id: 204, filename: 'HDFS.pdf', path: './graph/hdfs.pdf', source: 'graph-file', week_index_list: [5] },
      { file_id: 206, filename: 'Spark 架构.pdf', path: './graph/spark.pdf', source: 'graph-file', week_index_list: [12] },
    ],
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    files: [{ file_id: 205, filename: '力学导入.pdf', path: './graph/physics_intro.pdf', source: 'graph-file', week_index_list: [1] }],
    error_message: '',
    error_code: '',
  },
};

const RAW_LIST_ALL_JOBS_RESPONSE_BY_GRAPH_ID = {
  1: {
    success: true,
    jobs: [
      {
        job_id: 801,
        file_id: 206,
        file_path: './graph/spark.pdf',
        graph_id: 1,
      graph_name: 'RAG',
      status: 'in_progress',
      stage: 'pdf_to_md',
      progress_index: 2,
      end_stage: 'knowledge_to_save',
    },
  ],
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    jobs: [],
    error_message: '',
    error_code: '',
  },
};

const RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID = {
  1: {
    success: true,
    files: [
      { file_id: 301, filename: '大数据概论_20260402223302.pdf', path: './material/material_pdf/bigdata_questions.pdf', source: 'syllabus-file', week_index_list: [4] },
      { file_id: 302, filename: 'ETL 流程讲义.pdf', path: './material/etl_brief.pdf', source: 'syllabus-file', week_index_list: [4] },
      { file_id: 303, filename: '采集工具讲义.pdf', path: './material/tools_brief.pdf', source: 'syllabus-file', week_index_list: [4] },
    ],
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    files: [],
    error_message: '',
    error_code: '',
  },
};

const RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_REQUEST_FOR_USER_7 = {
  user_id: 7,
  manage: true,
};

const RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7 = {
  success: true,
  syllabuses: [
    {
      syllabus_id: 1,
      title: '大数据概论',
      edu_calendar_path: './schedule/calendar/bigdata_calendar.pdf',
      syllabus_draft_path: './schedule/syllabus_draft/bigdata_20260322174534.json',
      syllabus_path: './schedule/syllabus/bigdata_20260322235507.json',
      day_one_time: '2026-03-02T00:00:00',
      syllabus_permission: 'owner',
      graph_name: 'RAG',
      graph_id: 1,
    },
    {
      syllabus_id: 2,
      title: '大学物理（A）',
      edu_calendar_path: null,
      syllabus_draft_path: null,
      syllabus_path: null,
      day_one_time: null,
      syllabus_permission: 'user',
      graph_name: null,
      graph_id: 2,
    },
  ],
  error_message: '',
  error_code: '',
};

const RAW_GET_SYLLABUS_STATUS_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW = {
  1: {
    success: true,
    status: {
      is_edu_calendar_path_null: false,
      is_syllabus_draft_path_null: false,
      is_syllabus_path_null: false,
    },
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    status: {
      is_edu_calendar_path_null: true,
      is_syllabus_draft_path_null: true,
      is_syllabus_path_null: true,
    },
    error_message: '',
    error_code: '',
  },
};

/*
  1: {
    success: true,
    syllabus: {
      syllabus: {
        syllabus_id: 1,
        title: '大数据概论',
        edu_calendar_path: './schedule/calendar/bigdata_calendar.pdf',
        syllabus_draft_path: './schedule/syllabus_draft/bigdata_20260322174534.json',
        syllabus_path: './schedule/syllabus/bigdata_20260322235507.json',
        day_one_time: '2026-03-02T00:00:00',
        graph_name: 'RAG',
      },
      draft: RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
      final: RAW_GET_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
    },
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    syllabus: {
      syllabus: {
        syllabus_id: 2,
        title: '大学物理（A）',
        edu_calendar_path: null,
        syllabus_draft_path: null,
        syllabus_path: null,
        day_one_time: null,
        graph_name: null,
      },
      draft: null,
      final: null,
    },
    error_message: '',
    error_code: '',
  },
*/

const RAW_GET_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW = {
  1: {
    success: true,
    syllabus: RAW_GET_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    syllabus: null,
    error_message: '',
    error_code: '',
  },
};

const RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW = {
  1: {
    success: true,
    syllabus_draft: RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    syllabus_draft: null,
    error_message: '',
    error_code: '',
  },
};

const RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID = {
  1: {
    success: true,
    materials: [
      {
        material_id: 101,
        file_id: 301,
        title: '大数据概论_20260402223302',
        draft_path: './material/draft_material_json/bigdata_1775140427.json',
        final_path: './material/material_json/bigdata_1775140508.json',
        pdf_path: './material/material_pdf/bigdata_1775142629.pdf',
        create_time: '2026-04-02 22:33',
      },
    ],
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    materials: [],
    error_message: '',
    error_code: '',
  },
};

const RAW_GET_MATERIAL_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID = {
  101: {
    success: true,
    material: RAW_GET_MATERIAL_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
    error_message: '',
    error_code: '',
  },
};

const RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID = {
  101: {
    success: true,
    material_draft: RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
    error_message: '',
    error_code: '',
  },
};

const RAW_GET_MATERIAL_STATUS_RESPONSE_BY_MATERIAL_ID = {
  101: {
    success: true,
    status: {
      is_material_draft_path_null: false,
      is_material_path_null: false,
    },
    error_message: '',
    error_code: '',
  },
};

const RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_LEARNING_REQUEST_FOR_USER_7 = {
  user_id: 7,
  manage: false,
};

const RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_LEARNING_RESPONSE_FOR_USER_7 = {
  success: true,
  syllabuses: [
    {
      syllabus_id: 1,
      title: '大数据概论',
      isLearning: true,
      personal_syllabus_path: './schedule/student_alt/user_7/1_personal.json',
      day_one_time: '2026-03-02T00:00:00',
    },
    {
      syllabus_id: 2,
      title: '大学物理（A）',
      isLearning: false,
      personal_syllabus_path: null,
      day_one_time: null,
    },
  ],
  error_message: '',
  error_code: '',
};

const RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7 = {
  1: {
    success: true,
    syllabus: RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_FOR_USER_7_SYLLABUS_1,
    error_message: '',
    error_code: '',
  },
  2: {
    success: true,
    syllabus: null,
    error_message: '',
    error_code: '',
  },
};

const RAW_ASK_QUESTION_RESPONSE_FOR_USER_7_SYLLABUS_1 = {
  success: true,
  answer: 'ETL 负责把原始数据抽取、转换并装载成可分析的结构化信息。按当前教学进度，它对应第 4 周的大数据感知与获取部分。',
  matched_files: [301, 302],
  competance_list: [{ week_index: 4, level: 'weak' }],
  raw: {
    answer: 'ETL 负责把原始数据抽取、转换并装载成可分析的结构化信息。按当前教学进度，它对应第 4 周的大数据感知与获取部分。',
    document_names: ['大数据概论_20260402223302.pdf', 'ETL 流程讲义.pdf'],
    competance_list: [{ week_index: 4, level: 'weak' }],
  },
  error_message: '',
  error_code: '',
};

export {
  RAW_ASK_QUESTION_RESPONSE_FOR_USER_7_SYLLABUS_1,
  RAW_GET_MATERIAL_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
  RAW_GET_MATERIAL_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID,
  RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
  RAW_GET_MATERIAL_DRAFT_DETAIL_INFO_RESPONSE_BY_MATERIAL_ID,
  RAW_GET_MATERIAL_STATUS_RESPONSE_BY_MATERIAL_ID,
  RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_FOR_USER_7_SYLLABUS_1,
  RAW_GET_PERSONAL_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7,
  RAW_GET_SYLLABUS_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
  RAW_GET_SYLLABUS_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW,
  RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_OUTPUT_JSON_BIG_DATA,
  RAW_GET_SYLLABUS_DRAFT_DETAIL_INFO_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW,
  RAW_GET_SYLLABUS_STATUS_RESPONSE_BY_SYLLABUS_ID_FOR_USER_7_MANAGE_VIEW,
  RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_GRAPH_ID,
  RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID,
  RAW_LIST_ALL_JOBS_RESPONSE_BY_GRAPH_ID,
  RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_LEARNING_REQUEST_FOR_USER_7,
  RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_LEARNING_RESPONSE_FOR_USER_7,
  RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_REQUEST_FOR_USER_7,
  RAW_LIST_ALL_SYLLABUSES_BRIEF_INFO_FOR_MANAGE_RESPONSE_FOR_USER_7,
  RAW_LIST_MATERIALS_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID,
};
