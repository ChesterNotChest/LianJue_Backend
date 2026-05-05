export default function NotFound({ navigate }) {
  return (
    <section className="not-found">
      <p className="layout-eyebrow">404</p>
      <h1 className="layout-title">{'\u9875\u9762\u672a\u627e\u5230'}</h1>
      <p className="layout-subtitle">
        {'\u53ef\u7528\u5165\u53e3\u4ec5\u5305\u62ec /login\uff0c/teacher\uff0c/student\u3002'}
      </p>
      <div className="tile-actions">
        <button type="button" className="button button-primary" onClick={() => navigate('/login')}>
          {'\u8fd4\u56de\u767b\u5f55'}
        </button>
      </div>
    </section>
  );
}
