export default function MainLayout({ title, subtitle, actions, children }) {
  return (
    <div className="layout layout-main">
      <header className="layout-header">
        <div>
          <h1 className="layout-title">{title}</h1>
          {subtitle ? <p className="layout-subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="layout-actions">{actions}</div> : null}
      </header>
      <main className="layout-content">{children}</main>
    </div>
  );
}
