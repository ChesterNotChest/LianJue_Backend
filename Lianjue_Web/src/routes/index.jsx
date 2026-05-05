import AuthPage from '../pages/AuthPage';
import TeacherDashboard from '../pages/TeacherDashboard';
import StudentDashboard from '../pages/StudentDashboard';
import NotFound from '../pages/NotFound';

const routes = [
  { path: '/', component: AuthPage, name: 'Auth' },
  { path: '/login', component: AuthPage, name: 'Login' },
  { path: '/teacher', component: TeacherDashboard, name: 'TeacherDashboard' },
  { path: '/student', component: StudentDashboard, name: 'StudentDashboard' },
  { path: '*', component: NotFound, name: 'NotFound' },
];

export function resolveRoute(pathname) {
  return routes.find((route) => route.path === pathname) ?? routes.at(-1);
}

export function navigateTo(pathname) {
  if (window.location.pathname === pathname) {
    return;
  }

  window.history.pushState({}, '', pathname);
  window.dispatchEvent(new Event('lianjue:navigate'));
}

export default routes;
