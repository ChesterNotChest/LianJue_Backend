function updatePointerPosition(element, clientX, clientY) {
  const rect = element.getBoundingClientRect();
  const offsetX = clientX - rect.left;
  const offsetY = clientY - rect.top;
  const ratioX = rect.width ? offsetX / rect.width : 0.5;
  const ratioY = rect.height ? offsetY / rect.height : 0.5;

  element.style.setProperty('--pointer-x', `${Math.round(ratioX * 100)}%`);
  element.style.setProperty('--pointer-y', `${Math.round(ratioY * 100)}%`);
  element.style.setProperty('--pointer-shift-x', `${((ratioX - 0.5) * 20).toFixed(2)}px`);
  element.style.setProperty('--pointer-shift-y', `${((ratioY - 0.5) * 20).toFixed(2)}px`);
}

export default function LoginLayout({ children, aside }) {
  return (
    <div
      className="layout layout-login"
      onMouseMove={(event) => updatePointerPosition(event.currentTarget, event.clientX, event.clientY)}
      onMouseLeave={(event) => updatePointerPosition(
        event.currentTarget,
        event.currentTarget.getBoundingClientRect().left + event.currentTarget.getBoundingClientRect().width / 2,
        event.currentTarget.getBoundingClientRect().top + event.currentTarget.getBoundingClientRect().height / 2,
      )}
    >
      <section className="login-hero">
        {aside}
      </section>
      <section className="login-panel">{children}</section>
    </div>
  );
}
