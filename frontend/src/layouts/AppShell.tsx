import {
  Suspense,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ChevronRight,
  LogOut,
  Menu,
  Moon,
  Sun,
  TerminalSquare,
  WifiOff,
  X,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/api/auth";
import { useSession, replaceSession } from "@/app/session";
import { useTheme } from "@/app/theme";
import { Button, ErrorState, LoadingState } from "@/components/ui";
import {
  matchesNavigation,
  sectionLanding,
  SERVER_HOME,
  visibleNavigation,
} from "./navigation";
import { SectionNavigation } from "./SectionNavigation";
import { ProjectSwitcher } from "@/features/governance/ProjectSwitcher";
import "./shell.css";

const compactNavigationQuery = "(max-width: 900px)";
function subscribeCompactNavigation(listener: () => void) {
  const query = window.matchMedia(compactNavigationQuery);
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}
function isCompactViewport() {
  return window.matchMedia(compactNavigationQuery).matches;
}

export default function AppShell() {
  const { user, loading, error, refresh } = useSession();
  const [navPath, setNavPath] = useState<string | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const { theme, toggle } = useTheme();
  const location = useLocation();
  const compactViewport = useSyncExternalStore(
    subscribeCompactNavigation,
    isCompactViewport,
    () => false,
  );
  const focused =
    location.pathname.includes("/terminal/") &&
    new URLSearchParams(location.search).get("focus") === "1";
  const compactNavigation = compactViewport || focused;
  const navOpen = compactNavigation && navPath === location.pathname;
  const menuRef = useRef<HTMLButtonElement>(null);
  const desktopSidebarRef = useRef<HTMLElement>(null);
  const compactSidebarRef = useRef<HTMLDivElement>(null);
  const projectDialogOpen = useRef(false);
  const navigate = useNavigate();
  const client = useQueryClient();
  const logout = useMutation({
    mutationFn: authApi.logout,
    onSuccess: async () => {
      await replaceSession(client, { authenticated: false, user: null });
      navigate("/login");
    },
  });
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  if (loading) return <LoadingState label="Открываем рабочее пространство…" />;
  if (error)
    return (
      <main className="page-content">
        <ErrorState error={error} retry={refresh} />
      </main>
    );
  if (!user)
    return (
      <Navigate
        to="/login"
        state={{ from: location.pathname + location.search }}
        replace
      />
    );
  const groups = visibleNavigation(user);
  const currentGroup = groups.find((group) =>
    group.items.some((item) => matchesNavigation(item, location.pathname)),
  );
  const currentItem =
    currentGroup?.items.find(
      (item) =>
        location.pathname === item.path ||
        location.pathname.startsWith(`${item.path}/`),
    ) ??
    currentGroup?.items.find((item) =>
      matchesNavigation(item, location.pathname),
    );
  const current = {
    label: currentItem?.label ?? "Страница",
    group: currentGroup?.label ?? "",
  };
  const focusNavigationTrigger = () => {
    if (menuRef.current && menuRef.current.offsetParent !== null) {
      menuRef.current.focus();
      return;
    }
    const sidebar = desktopSidebarRef.current;
    (
      sidebar?.querySelector<HTMLElement>(".nav-link[aria-current='page']") ??
      sidebar?.querySelector<HTMLElement>(".brand")
    )?.focus();
  };
  const sidebarContent = (projectTrigger: ReactNode) => (
    <>
      <div className="sidebar-heading">
        <Link
          to={SERVER_HOME}
          className="brand"
          onClick={() => setNavPath(null)}
        >
          <span className="brand-mark">
            <TerminalSquare size={21} />
          </span>
          webterm
        </Link>
        {compactNavigation && (
          <Dialog.Close asChild>
            <Button variant="ghost" size="icon" aria-label="Закрыть навигацию">
              <X size={18} />
            </Button>
          </Dialog.Close>
        )}
      </div>
      {projectTrigger}
      <nav className="sidebar-nav" aria-label="Основная навигация">
        {groups.map((group) => (
          <Link
            key={group.id}
            className={`nav-link${currentGroup?.id === group.id ? " active" : ""}${group.id === "settings" ? " nav-settings" : ""}`}
            aria-current={currentGroup?.id === group.id ? "page" : undefined}
            to={sectionLanding(group).path}
            onClick={() => setNavPath(null)}
          >
            <group.icon size={17} />
            <span>{group.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
  return (
    <Dialog.Root
      open={navOpen}
      onOpenChange={(open) => setNavPath(open ? location.pathname : null)}
    >
      <div className={`app-shell${focused ? " focus-terminal" : ""}`}>
        <a className="skip-link" href="#main-content">
          Перейти к содержимому
        </a>
        <ProjectSwitcher
          onOpenChange={(open) => {
            projectDialogOpen.current = open;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const sidebar =
              compactSidebarRef.current ?? desktopSidebarRef.current;
            const trigger = sidebar?.querySelector<HTMLButtonElement>(
              ".gov-project-switcher",
            );
            if (trigger) trigger.focus();
            else focusNavigationTrigger();
          }}
          renderTrigger={(trigger) =>
            compactNavigation ? (
              <Dialog.Portal>
                <Dialog.Overlay className="nav-overlay" />
                <Dialog.Content
                  id="app-sidebar"
                  className="sidebar compact-sidebar"
                  ref={compactSidebarRef}
                  onOpenAutoFocus={(event) => {
                    event.preventDefault();
                    const sidebar = compactSidebarRef.current;
                    (
                      sidebar?.querySelector<HTMLElement>(
                        ".nav-link[aria-current='page']",
                      ) ?? sidebar?.querySelector<HTMLElement>(".nav-link")
                    )?.focus();
                  }}
                  onCloseAutoFocus={(event) => {
                    event.preventDefault();
                    setNavPath(null);
                    if (!projectDialogOpen.current) focusNavigationTrigger();
                  }}
                >
                  <Dialog.Title className="sr-only">
                    Основная навигация
                  </Dialog.Title>
                  <Dialog.Description className="sr-only">
                    Выберите раздел или рабочий проект. Escape закрывает меню.
                  </Dialog.Description>
                  {sidebarContent(trigger)}
                </Dialog.Content>
              </Dialog.Portal>
            ) : (
              <aside
                id="app-sidebar"
                className="sidebar sidebar-desktop"
                ref={desktopSidebarRef}
              >
                {sidebarContent(trigger)}
              </aside>
            )
          }
        />
        <div className="shell-main">
          <div className="topbar">
            <div className="row">
              <Dialog.Trigger asChild ref={menuRef}>
                <Button
                  className="menu-toggle"
                  variant="ghost"
                  size="icon"
                  aria-label={
                    navOpen ? "Закрыть навигацию" : "Открыть навигацию"
                  }
                  aria-expanded={navOpen}
                  aria-controls="app-sidebar"
                >
                  {navOpen ? <X size={18} /> : <Menu size={18} />}
                </Button>
              </Dialog.Trigger>
              <div className="breadcrumbs">
                {current.group && current.group !== current.label && (
                  <>
                    <span>{current.group}</span>
                    <ChevronRight size={13} />
                  </>
                )}
                <span>{current.label}</span>
              </div>
            </div>
            <div className="topbar-actions">
              <Button
                variant="ghost"
                size="icon"
                aria-label={
                  theme === "light"
                    ? "Включить тёмную тему"
                    : "Включить светлую тему"
                }
                onClick={toggle}
              >
                {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
              </Button>
              <Dropdown.Root>
                <Dropdown.Trigger asChild>
                  <button className="account-button" aria-label="Меню аккаунта">
                    {user.username.slice(0, 2).toUpperCase()}
                  </button>
                </Dropdown.Trigger>
                <Dropdown.Portal>
                  <Dropdown.Content
                    className="menu-content"
                    align="end"
                    sideOffset={10}
                  >
                    <Dropdown.Label className="menu-label">
                      {user.username}
                      <div className="muted text-sm">{user.email}</div>
                    </Dropdown.Label>
                    <Dropdown.Item
                      className="menu-item"
                      disabled={logout.isPending}
                      onSelect={() => logout.mutate()}
                    >
                      <LogOut size={14} />
                      Выйти
                    </Dropdown.Item>
                  </Dropdown.Content>
                </Dropdown.Portal>
              </Dropdown.Root>
            </div>
          </div>
          {!online && (
            <div className="offline-banner" role="status">
              <WifiOff size={16} />
              Нет соединения. Данные могут быть устаревшими. Проверьте сеть.
            </div>
          )}
          {logout.error && <ErrorState error={logout.error} />}
          <main id="main-content" className="page-content" tabIndex={-1}>
            {currentGroup && !focused && (
              <SectionNavigation
                group={currentGroup}
                pathname={location.pathname}
              />
            )}
            <Suspense fallback={<LoadingState />}>
              <div key={user.active_project?.id ?? "default"}>
                <Outlet />
              </div>
            </Suspense>
          </main>
        </div>
      </div>
    </Dialog.Root>
  );
}
