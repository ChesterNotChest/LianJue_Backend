import { useState } from 'react';
import LoginLayout from '../layouts/LoginLayout';
import { loginUser, registerUser } from '../api/user_api';
import { clearAuth, getStoredAuth } from '../api/session';

function EntryCard({ title, detail, disabled, onClick }) {
  return (
    <button type="button" className="entry-card" onClick={onClick} disabled={disabled}>
      <span className="entry-card-label">{title}</span>
      <span className="entry-card-text">{detail}</span>
    </button>
  );
}

export default function AuthPage({ navigate }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({
    userName: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const storedAuth = getStoredAuth();

  const updateField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (!form.userName.trim() || !form.password) {
      setError('请输入账号和密码');
      return;
    }

    if (mode === 'register') {
      if (!form.email.trim()) {
        setError('请输入邮箱');
        return;
      }
      if (form.password !== form.confirmPassword) {
        setError('两次输入的密码不一致');
        return;
      }
    }

    setBusy(true);
    try {
      const action = mode === 'login' ? loginUser : registerUser;
      const response = await action({
        userName: form.userName.trim(),
        email: form.email.trim(),
        password: form.password,
      });

      if (!response.success || !response.user?.user_id) {
        throw new Error(response.errorMessage || `${mode} failed`);
      }

      setSuccess(mode === 'login' ? '登录成功' : '注册成功，已自动登录');
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  const enterRoute = (pathname) => {
    if (!getStoredAuth()?.user_id) {
      setError('请先完成登录或注册');
      return;
    }
    navigate(pathname);
  };

  const isLoggedIn = Boolean(storedAuth?.user_id);

  return (
    <LoginLayout
      aside={(
        <div className="auth-hero-copy">
          <h1 className="layout-title auth-title auth-title-wide">联觉学习平台</h1>
        </div>
      )}
    >
      <section className="auth-card">
        <header className="auth-card-head">
          <p className="layout-eyebrow">{isLoggedIn ? 'Ready' : mode === 'login' ? 'Sign In' : 'Sign Up'}</p>
          <h2>{isLoggedIn ? '进入平台' : mode === 'login' ? '登录' : '注册'}</h2>
        </header>

        {isLoggedIn ? (
          <div className="auth-ready-stack">
            <p className="response-copy">{`当前登录: ${storedAuth.user_name} (#${storedAuth.user_id})`}</p>
            <div className="tile-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => {
                  clearAuth();
                  setSuccess('');
                  setError('');
                  navigate('/login');
                }}
              >
                登出
              </button>
            </div>
            <div className="auth-entry-grid auth-entry-grid-single">
              <EntryCard
                title="开始学习"
                detail="进入学生端，查看个人教学大纲、提问区、推荐材料与学习记录。"
                onClick={() => enterRoute('/student')}
              />
              <EntryCard
                title="管理大纲"
                detail="进入教师端，管理教学大纲、材料、习题以及相关构建流程。"
                onClick={() => enterRoute('/teacher')}
              />
            </div>
          </div>
        ) : (
          <>
            <div className="auth-actions auth-entry-grid auth-entry-grid-single">
              <EntryCard
                title="登录"
                detail="使用已有账号进入平台。"
                disabled={mode === 'login'}
                onClick={() => setMode('login')}
              />
              <EntryCard
                title="注册"
                detail="创建新账号并写入本地登录态。"
                disabled={mode === 'register'}
                onClick={() => setMode('register')}
              />
            </div>

            <form className="auth-form" onSubmit={submit}>
              <label className="field">
                <span>账号</span>
                <input
                  value={form.userName}
                  placeholder="输入账号"
                  onChange={(event) => updateField('userName', event.target.value)}
                />
              </label>
              {mode === 'register' ? (
                <label className="field">
                  <span>邮箱</span>
                  <input
                    value={form.email}
                    placeholder="输入邮箱"
                    onChange={(event) => updateField('email', event.target.value)}
                  />
                </label>
              ) : null}
              <label className="field">
                <span>密码</span>
                <input
                  type="password"
                  value={form.password}
                  placeholder="输入密码"
                  onChange={(event) => updateField('password', event.target.value)}
                />
              </label>
              {mode === 'register' ? (
                <label className="field">
                  <span>确认密码</span>
                  <input
                    type="password"
                    value={form.confirmPassword}
                    placeholder="再次输入密码"
                    onChange={(event) => updateField('confirmPassword', event.target.value)}
                  />
                </label>
              ) : null}
              <div className="tile-actions">
                <button type="submit" className="button button-primary" disabled={busy}>
                  {busy ? '处理中..' : mode === 'login' ? '登录' : '注册'}
                </button>
              </div>
            </form>
          </>
        )}

        {success ? <p className="response-copy">{success}</p> : null}
        {error ? <p className="response-copy">{error}</p> : null}
      </section>
    </LoginLayout>
  );
}
