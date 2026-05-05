import { useEffect, useMemo, useState } from 'react';
import MainLayout from '../layouts/MainLayout';
import {
  Button,
  DisabledBlock,
  EmptyState,
  LoadingPlaceholder,
  MaterialShelf,
  StatusPill,
  SyllabusSwitcher,
  WeekAxis,
} from '../components/DashboardShared';
import {
  askQuestion,
  getPersonalSyllabus,
  getStudentDashboardData,
  getLearningProfile,
  initPersonalSyllabus,
  updatePersonalSyllabus,
} from '../api/learning_api';
import { downloadFile } from '../api/file_transmit_api';
import { getCurrentUserId } from '../api/session';

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function pickDefaultWeekIndex(personalSyllabus) {
  const period = Array.isArray(personalSyllabus?.period) ? personalSyllabus.period : [];

  return (
    period.find((item) => item.competance === 'weak')?.week_index
    ?? period.find((item) => item.competance === 'none')?.week_index
    ?? period[0]?.week_index
    ?? ''
  );
}

function getCurrentWeekIndex(dayOneTime, periodLength) {
  if (!dayOneTime || !periodLength) {
    return null;
  }

  const dayOneDate = new Date(dayOneTime);
  if (Number.isNaN(dayOneDate.getTime())) {
    return null;
  }

  const diffMs = Date.now() - dayOneDate.getTime();
  if (diffMs < 0) {
    return 1;
  }

  const weekIndex = Math.floor(diffMs / (7 * 24 * 60 * 60 * 1000)) + 1;
  return Math.min(Math.max(weekIndex, 1), periodLength);
}

function FileDropzone({ files, onFilesChange, title = '选择文件 / dropbox' }) {
  const [isDragging, setIsDragging] = useState(false);

  const applyFiles = (fileList) => {
    onFilesChange(Array.from(fileList ?? []));
  };

  return (
    <label
      className={['dropzone', 'file-dropzone', isDragging ? 'is-dragging' : ''].filter(Boolean).join(' ')}
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
        multiple
        onChange={(event) => applyFiles(event.target.files)}
      />
      <div className="file-dropzone-copy">
        <strong>{title}</strong>
        <small>
          {files.length ? files.map((file) => file.name).join(' / ') : '支持点击选择或拖拽到这里'}
        </small>
      </div>
    </label>
  );
}

export default function StudentDashboard({ navigate }) {
  const [syllabuses, setSyllabuses] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [isBooting, setIsBooting] = useState(true);
  const [error, setError] = useState('');
  const [learningProfile, setLearningProfile] = useState(null);
  const [dialogueTextForProfile, setDialogueTextForProfile] = useState('');
  const [advancedJsonText, setAdvancedJsonText] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);
  const [questionInput, setQuestionInput] = useState('');
  const [questionAsked, setQuestionAsked] = useState(false);
  const [answer, setAnswer] = useState('');
  const [askBusy, setAskBusy] = useState(false);
  const [initBusy, setInitBusy] = useState(false);
  const [studyBusy, setStudyBusy] = useState(false);
  const [studyHours, setStudyHours] = useState('2');
  const [selectedWeekIndex, setSelectedWeekIndex] = useState('');
  const [studyRecordFiles, setStudyRecordFiles] = useState([]);
  const [expandedTimelineWeekId, setExpandedTimelineWeekId] = useState(null);
  const [isAnswerExpanded, setIsAnswerExpanded] = useState(false);

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
        const response = await getStudentDashboardData();
        if (cancelled) {
          return;
        }
        setSyllabuses(response.syllabuses);
        setActiveId(response.syllabuses[0]?.syllabusId ?? null);
        try {
          const profileRes = await getLearningProfile();
          if (!cancelled && profileRes && profileRes.success) {
            setLearningProfile(profileRes.profile ?? null);
          }
        } catch (pfErr) {
          // ignore learning profile fetch errors for now
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

  const active = syllabuses.find((item) => item.syllabusId === activeId) ?? syllabuses[0] ?? null;
  const weekOptions = useMemo(() => active?.personalSyllabus?.period ?? [], [active?.personalSyllabus]);
  const currentWeekIndex = useMemo(
    () => getCurrentWeekIndex(active?.dayOneTime, weekOptions.length),
    [active?.dayOneTime, weekOptions.length],
  );
  const disabled = isBooting || !active || !active.isLearning || !active.personalSyllabus;
  const showStudentShell = Boolean(active) || isBooting;
  const isStudentLoading = isBooting && !active;

  useEffect(() => {
    if (!weekOptions.length) {
      setSelectedWeekIndex('');
      return;
    }

    const stillExists = weekOptions.some((item) => String(item.week_index) === String(selectedWeekIndex));
    if (!stillExists) {
      setSelectedWeekIndex(String(pickDefaultWeekIndex(active?.personalSyllabus)));
    }
  }, [active?.personalSyllabus, selectedWeekIndex, weekOptions]);

  useEffect(() => {
    setExpandedTimelineWeekId(null);
    setIsAnswerExpanded(false);
  }, [activeId]);

  const patchActive = (updater) => {
    setSyllabuses((current) => current.map((item) => (
      item.syllabusId === activeId ? updater(cloneData(item)) : item
    )));
  };

  const switchSyllabus = (offset) => {
    if (!syllabuses.length) {
      return;
    }

    const currentIndex = syllabuses.findIndex((item) => item.syllabusId === activeId);
    const nextIndex = (currentIndex + offset + syllabuses.length) % syllabuses.length;
    setActiveId(syllabuses[nextIndex].syllabusId);
    setQuestionAsked(false);
    setQuestionInput('');
    setAnswer('');
    setStudyRecordFiles([]);
  };

  const recommendationItems = questionAsked
    ? active?.recommendedMaterials ?? []
    : active?.defaultRecommendations ?? [];
  const recommendationDownloadItems = recommendationItems.map((item) => ({
    ...item,
    onDownload: async (downloadItem) => {
      try {
        const result = await downloadFile(downloadItem.fileId, downloadItem.title);
        if (!result.success) {
          throw new Error(result.error_message || '下载失败');
        }
      } catch (actionError) {
        setError(actionError instanceof Error ? actionError.message : '下载失败');
      }
    },
  }));

  return (
    <MainLayout
      title="学生 Dashboard"
      actions={(
        <div className="header-actions">
          <Button variant="secondary" onClick={() => navigate('/login')}>返回登录</Button>
          <Button
            variant="primary"
            disabled={!active || initBusy}
            onClick={async () => {
              if (!active) {
                return;
              }

              setInitBusy(true);
              setError('');

              try {
                const currentUserId = getCurrentUserId();
                await initPersonalSyllabus({ syllabusId: active.syllabusId });
                const personalSyllabus = await getPersonalSyllabus({ syllabusId: active.syllabusId });
                patchActive((item) => {
                  item.isLearning = true;
                  item.personalSyllabus = personalSyllabus ?? item.personalSyllabus ?? {
                    syllabus_id: item.syllabusId,
                    user_id: currentUserId,
                    review_count: 0,
                    reviewed_at: 0,
                    period: [],
                  };
                  return item;
                });
              } catch (actionError) {
                setError(actionError instanceof Error ? actionError.message : '初始化失败');
              } finally {
                setInitBusy(false);
              }
            }}
          >
            {active?.isLearning ? '已选择学习' : initBusy ? '处理中...' : '选择学习'}
          </Button>
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
            learningLabel={active?.isLearning ? '学习中' : '未学习'}
          />
          {active ? (
            <div className="status-strip">
              <StatusPill tone={active.isLearning && active.personalSyllabus ? 'success' : 'warning'}>
                {active.isLearning && active.personalSyllabus ? 'personal_syllabus 已就绪' : '待初始化'}
              </StatusPill>
              <StatusPill tone={questionAsked ? 'success' : 'neutral'}>
                {questionAsked ? 'AI 推荐' : '默认推荐'}
              </StatusPill>
            </div>
          ) : null}

          <div style={{ marginTop: 12, marginBottom: 8, display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 420px', minWidth: 320 }}>
              <label className="field">
                <span>对话摘要（可选）</span>
                <textarea
                  rows={3}
                  value={dialogueTextForProfile}
                  placeholder="填写最近的对话或学习目标，例如：我想在两周内掌握函数与循环"
                  onChange={(e) => setDialogueTextForProfile(e.target.value)}
                />
              </label>
            </div>

            <div style={{ width: 260, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>高级数据 (JSON，可选)</span>
                <textarea
                  rows={3}
                  value={advancedJsonText}
                  placeholder='例如：{"learning_records": [...], "answer_records": [...]}'
                  onChange={(e) => setAdvancedJsonText(e.target.value)}
                />
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  variant="primary"
                  disabled={profileLoading}
                  onClick={async () => {
                    setProfileLoading(true);
                    setError('');
                    try {
                      let extra = {};
                      if (advancedJsonText && advancedJsonText.trim()) {
                        try {
                          const parsed = JSON.parse(advancedJsonText);
                          extra = parsed && typeof parsed === 'object' ? parsed : {};
                        } catch (pe) {
                          throw new Error('高级数据 JSON 解析失败');
                        }
                      }

                      const payload = {
                        syllabusId: active?.syllabusId ?? null,
                        dialogueText: dialogueTextForProfile || undefined,
                        ...extra,
                      };

                      const res = await getLearningProfile(payload);
                      if (!res || !res.success) {
                        throw new Error(res?.errorMessage || res?.error_message || '画像请求失败');
                      }
                      setLearningProfile(res.profile ?? null);
                    } catch (err) {
                      setError(err instanceof Error ? err.message : String(err));
                    } finally {
                      setProfileLoading(false);
                    }
                  }}
                >
                  {profileLoading ? '刷新中...' : '刷新画像'}
                </Button>
                <Button variant="ghost" onClick={() => { setDialogueTextForProfile(''); setAdvancedJsonText(''); setError(''); }}>
                  清空
                </Button>
              </div>
            </div>
          </div>
          {learningProfile ? (
            <div className="learning-profile-panel" style={{ marginTop: 12 }}>
              <h4 style={{ margin: '6px 0' }}>学习画像</h4>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div style={{ minWidth: 260, flex: '1 1 320px' }}>
                  <div style={{ marginBottom: 8 }}><strong>学习目标：</strong>{learningProfile.learning_goal ?? '未提供'}</div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                    <StatusPill tone="neutral">目标层级: {learningProfile.target_level ?? '未知'}</StatusPill>
                    <StatusPill tone="neutral">学习风格: {learningProfile.learning_style ?? '未知'}</StatusPill>
                    <StatusPill tone="neutral">频率: {learningProfile.study_frequency ?? '未知'}</StatusPill>
                    <StatusPill tone="neutral">时长: {learningProfile.study_duration ?? '未知'}</StatusPill>
                  </div>

                  <div style={{ marginBottom: 8 }}>
                    <strong>风险/关注：</strong>
                    <div style={{ marginTop: 6 }}>
                      <div>困难主题: {Array.isArray(learningProfile.bottleneck_topics) && learningProfile.bottleneck_topics.length ? learningProfile.bottleneck_topics.join('，') : '无'}</div>
                      <div>退学风险: {learningProfile.dropout_risk ?? '未知'}</div>
                    </div>
                  </div>
                </div>

                <div style={{ flex: '1 1 360px', minWidth: 260 }}>
                  <div style={{ marginBottom: 6 }}><strong>知识掌握</strong></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {learningProfile.knowledge_mastery && typeof learningProfile.knowledge_mastery === 'object' ? (
                      Object.entries(learningProfile.knowledge_mastery).slice(0, 8).map(([k, v]) => {
                        const score = Number(v) || 0;
                        const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
                        return (
                          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ width: 110, fontSize: 13 }}>{k}</div>
                            <div style={{ flex: 1, height: 10, background: '#eee', borderRadius: 6, overflow: 'hidden' }}>
                              <div style={{ width: `${pct}%`, height: '100%', background: '#56a3ff' }} />
                            </div>
                            <div style={{ width: 40, textAlign: 'right', fontSize: 12 }}>{pct}%</div>
                          </div>
                        );
                      })
                    ) : (
                      <div>暂无知识掌握数据</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </section>

        {error ? <EmptyState>{error}</EmptyState> : null}
        {!error && !active && !isBooting ? <EmptyState>暂无教学大纲。</EmptyState> : null}

        {showStudentShell ? (
          <section className="dashboard-grid dashboard-grid-student">
            <article className="tile-card tile-teal tile-span-full">
              <div className="tile-card-head">
                <h3>个人教学大纲</h3>
                <div className="tile-head-controls">
                  <StatusPill tone={disabled ? 'warning' : 'success'}>
                    {disabled ? '待初始化' : '可交互'}
                  </StatusPill>
                </div>
              </div>
              {isStudentLoading ? (
                <LoadingPlaceholder size="axis" />
              ) : (
                <DisabledBlock disabled={disabled} message="请先点击“选择学习”初始化 personal_syllabus">
                  <WeekAxis
                    items={active.personalSyllabus?.period ?? []}
                    mode="competance"
                    currentWeek={currentWeekIndex}
                    expandedItemId={expandedTimelineWeekId}
                    onToggleExpand={(itemId) => {
                      setExpandedTimelineWeekId((current) => (current === itemId ? null : itemId));
                    }}
                  />
                </DisabledBlock>
              )}
            </article>

            <div className={['student-focus-row', isAnswerExpanded ? 'is-answer-expanded' : ''].filter(Boolean).join(' ')}>
              <article className="tile-card tile-blue student-question-tile">
                <div className="tile-card-head">
                  <h3>提问</h3>
                  <div className="tile-head-controls">
                    <StatusPill tone={questionAsked ? 'success' : 'neutral'}>
                      {questionAsked ? '已提问' : '待提问'}
                    </StatusPill>
                    <Button variant="ghost" onClick={() => setIsAnswerExpanded((current) => !current)}>
                      {isAnswerExpanded ? '收起' : '展开回答'}
                    </Button>
                  </div>
                </div>
                {isStudentLoading ? (
                  <LoadingPlaceholder size="answer" />
                ) : (
                  <DisabledBlock disabled={disabled} message="请先选择学习">
                    <div className={['question-grid', isAnswerExpanded ? 'is-answer-expanded' : ''].filter(Boolean).join(' ')}>
                      <section className="response-panel">
                        <label className="field">
                          <span>问题</span>
                          <textarea
                            rows="4"
                            value={questionInput}
                            placeholder="例如：ETL 在这里具体负责什么？"
                            onChange={(event) => setQuestionInput(event.target.value)}
                          />
                        </label>
                        <div className="tile-actions">
                          <Button
                            variant="primary"
                            disabled={askBusy || !questionInput.trim()}
                            onClick={async () => {
                              setAskBusy(true);
                              setError('');

                              try {
                                const response = await askQuestion({
                                  syllabusId: active.syllabusId,
                                  question: questionInput,
                                });
                                const personalSyllabus = await getPersonalSyllabus({ syllabusId: active.syllabusId });
                                setQuestionAsked(true);
                                setAnswer(response.answer);
                                patchActive((item) => {
                                  item.recommendedMaterials = response.recommendedMaterials;
                                  item.personalSyllabus = personalSyllabus ?? item.personalSyllabus;
                                  return item;
                                });
                              } catch (actionError) {
                                setError(actionError instanceof Error ? actionError.message : '提问失败');
                              } finally {
                                setAskBusy(false);
                              }
                            }}
                          >
                            {askBusy ? '处理中...' : '提交提问'}
                          </Button>
                        </div>
                      </section>
                      <section className={['response-panel', 'response-panel-answer', isAnswerExpanded ? 'is-expanded' : ''].filter(Boolean).join(' ')}>
                        <strong className="response-title">回答</strong>
                        <p className={['response-copy', isAnswerExpanded ? 'is-expanded' : 'is-condensed'].filter(Boolean).join(' ')}>
                          {answer || '尚未提问。'}
                        </p>
                      </section>
                    </div>
                  </DisabledBlock>
                )}
              </article>

              <article className="tile-card tile-slate student-recommendation-tile">
                <div className="tile-card-head">
                  <h3>推荐材料</h3>
                  <StatusPill tone={questionAsked ? 'success' : 'warning'}>
                    {questionAsked ? 'AI' : '默认'}
                  </StatusPill>
                </div>
                {isStudentLoading ? (
                  <LoadingPlaceholder size="shelf" />
                ) : (
                  <DisabledBlock disabled={disabled} message="请先选择学习">
                    <MaterialShelf items={recommendationDownloadItems} emptyText="暂无可展示的推荐材料。" />
                  </DisabledBlock>
                )}
              </article>
            </div>

            <article className="tile-card tile-amber tile-span-full">
              <div className="tile-card-head">
                <h3>学习内容记录</h3>
                <StatusPill tone={disabled ? 'warning' : 'success'}>
                  {disabled ? '不可提交' : '可提交'}
                </StatusPill>
              </div>
              {isStudentLoading ? (
                <LoadingPlaceholder size="record" />
              ) : (
                <DisabledBlock disabled={disabled} message="请先选择学习">
                  <div className="study-record-grid">
                    <section>
                      <DisabledBlock disabled message="正在开发">
                        <div className="study-mode is-disabled-mode">
                          <strong className="study-mode-title">方式 A</strong>
                          <FileDropzone
                            files={studyRecordFiles}
                            onFilesChange={setStudyRecordFiles}
                            title="上传学习记录 / dropbox"
                          />
                          <label className="field">
                            <span>补充说明</span>
                            <textarea rows="3" placeholder="输入学习记录说明" />
                          </label>
                        </div>
                      </DisabledBlock>
                    </section>

                    <section className="study-mode">
                      <strong className="study-mode-title">方式 B</strong>
                      <label className="field">
                        <span>学习周次</span>
                        <select
                          className="select-field"
                          value={selectedWeekIndex}
                          onChange={(event) => setSelectedWeekIndex(event.target.value)}
                        >
                          <option value="">请选择周次</option>
                          {weekOptions.map((item) => (
                            <option key={item.week_index} value={item.week_index}>
                              {`第${item.week_index}周`}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>付出小时数</span>
                        <input
                          inputMode="numeric"
                          value={studyHours}
                          onChange={(event) => setStudyHours(event.target.value)}
                        />
                      </label>
                      <div className="tile-actions">
                        <Button
                          variant="primary"
                          disabled={studyBusy || !selectedWeekIndex}
                          onClick={async () => {
                            setStudyBusy(true);
                            setError('');

                            try {
                              const response = await updatePersonalSyllabus({
                                syllabusId: active.syllabusId,
                                weekIndex: Number(selectedWeekIndex),
                                studyTimeSpent: Number(studyHours) || 0,
                              });

                              if (!response.success || !response.syllabus) {
                                throw new Error(response.errorMessage || '提交失败');
                              }

                              patchActive((item) => {
                                item.personalSyllabus = response.syllabus;
                                return item;
                              });
                            } catch (actionError) {
                              setError(actionError instanceof Error ? actionError.message : '提交记录失败');
                            } finally {
                              setStudyBusy(false);
                            }
                          }}
                        >
                          {studyBusy ? '处理中...' : '提交记录'}
                        </Button>
                      </div>
                    </section>
                  </div>
                </DisabledBlock>
              )}
            </article>
          </section>
        ) : null}
      </section>
    </MainLayout>
  );
}
