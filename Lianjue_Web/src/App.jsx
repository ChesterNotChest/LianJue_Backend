import { useEffect, useState } from 'react';
import './App.css';
import routes, { navigateTo, resolveRoute } from './routes';

function App() {
  const [path, setPath] = useState(() => window.location.pathname || '/');

  useEffect(() => {
    const syncRoute = () => {
      setPath(window.location.pathname || '/');
    };

    window.addEventListener('popstate', syncRoute);
    window.addEventListener('lianjue:navigate', syncRoute);

    return () => {
      window.removeEventListener('popstate', syncRoute);
      window.removeEventListener('lianjue:navigate', syncRoute);
    };
  }, []);

  const activeRoute = resolveRoute(path);
  const ActiveComponent = activeRoute.component;

  return (
    <div className="app-shell">
      <ActiveComponent
        currentPath={path}
        routes={routes}
        navigate={navigateTo}
      />
    </div>
  );
}

export default App;
