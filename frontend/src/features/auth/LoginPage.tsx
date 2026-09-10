import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Eye,
  EyeOff,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import { authApi } from "@/api/auth";
import { useSession, replaceSession } from "@/app/session";
import { Button, Field, Feedback, LoadingState } from "@/components/ui";
export default function LoginPage() {
  const { user, loading } = useSession();
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [local, setLocal] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      authApi.login(username.trim(), password, local ? "local" : "auto"),
    onSuccess: async (session) => {
      await replaceSession(client, session);
      setPassword("");
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from?.startsWith("/") && !from.startsWith("//") ? from : "/", {
        replace: true,
      });
    },
  });
  if (loading) return <LoadingState />;
  if (user) return <Navigate to="/" replace />;
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <div className="login-page">
      <aside className="login-intro">
        <a className="brand" href="/login">
          <span className="brand-mark">
            <TerminalSquare size={22} />
          </span>
          webterm
        </a>
        <div>
          <div className="eyebrow">Управление инфраструктурой</div>
          <h2>
            Ваша инфраструктура.
            <br />
            Под вашим контролем.
          </h2>
          <p>
            Серверы, автоматизация и AI —<br />в одном рабочем пространстве.
          </p>
        </div>
      </aside>
      <main className="login-main">
        <div className="login-form">
          <h1>Вход в WebTerm</h1>
          <p className="muted">Войдите в рабочее пространство вашей команды.</p>
          <form onSubmit={submit} aria-busy={mutation.isPending}>
            <fieldset
              className="stack login-fields"
              disabled={mutation.isPending}
            >
              <Field label="Имя пользователя" htmlFor="username">
                <input
                  id="username"
                  name="username"
                  autoComplete="username"
                  autoFocus
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Ваш логин"
                />
              </Field>
              <Field label="Пароль" htmlFor="password">
                <div className="password-field">
                  <input
                    id="password"
                    name="password"
                    type={show ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={show ? "Скрыть пароль" : "Показать пароль"}
                    onClick={() => setShow(!show)}
                  >
                    {show ? <EyeOff size={17} /> : <Eye size={17} />}
                  </Button>
                </div>
              </Field>
              <details className="login-advanced">
                <summary>Дополнительные параметры входа</summary>
                <label className="checkbox-field text-sm">
                  <input
                    type="checkbox"
                    checked={local}
                    onChange={(e) => setLocal(e.target.checked)}
                  />
                  Локальная учётная запись
                </label>
                <p className="muted text-sm">
                  Включите, если используете отдельную учётную запись WebTerm
                  вместо корпоративного каталога.
                </p>
              </details>
              <Feedback error={mutation.error} />
              <Button
                type="submit"
                variant="primary"
                loading={mutation.isPending}
              >
                {mutation.isPending ? "Входим…" : "Войти"}
                <ArrowRight size={16} />
              </Button>
            </fieldset>
          </form>
          <div className="login-security">
            <ShieldCheck size={17} />
            <span>Доступ регулируется политиками вашей организации.</span>
          </div>
        </div>
      </main>
    </div>
  );
}
