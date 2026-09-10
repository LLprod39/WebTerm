import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
  Drawer,
  ConfirmDialog,
  Tabs,
} from "@/components/ui";
const meta: Meta = { title: "WebTerm/Design system" };
export default meta;
type Story = StoryObj;
export const Controls: Story = {
  render: () => (
    <div className="stack">
      <PageHeader
        eyebrow="WebTerm / Design system"
        title="Рабочие элементы"
        description="Одна система. Светлая и тёмная схемы."
      />
      <div className="row">
        <Button variant="primary">Основное действие</Button>
        <Button>Дополнительное</Button>
        <Button variant="danger">Удалить</Button>
        <Button disabled>Недоступно</Button>
        <Button loading>Выполняется</Button>
      </div>
      <div className="row">
        {["healthy", "warning", "critical", "running", "unknown"].map(
          (status) => (
            <StatusBadge key={status} status={status} />
          ),
        )}
      </div>
      <div className="form-grid">
        <Field label="Название сервера" htmlFor="story-server">
          <input id="story-server" placeholder="Production API" />
        </Field>
        <Field
          label="Адрес"
          htmlFor="story-host"
          error="Укажите корректный адрес"
        >
          <input id="story-host" aria-invalid defaultValue="" />
        </Field>
      </div>
    </div>
  ),
};
function InteractivePatterns() {
  const [drawer, setDrawer] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [tab, setTab] = useState("overview");
  return (
    <div className="stack">
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "overview", label: "Обзор" },
          { value: "activity", label: "События", count: 12 },
        ]}
      />
      <Panel
        title={tab === "overview" ? "Рабочая область" : "Последние события"}
      >
        <div className="section-body row">
          <Button onClick={() => setDrawer(true)}>Открыть настройки</Button>
          <Button variant="danger" onClick={() => setConfirm(true)}>
            Удалить объект
          </Button>
        </div>
      </Panel>
      <Drawer
        open={drawer}
        onOpenChange={setDrawer}
        title="Настройки сервера"
        description="Доступная форма с фокусом и закрытием по Escape."
      >
        <div className="stack">
          <Field label="Название" htmlFor="story-name">
            <input id="story-name" defaultValue="production-api-01" />
          </Field>
          <Field label="Контекст" htmlFor="story-notes">
            <textarea
              id="story-notes"
              defaultValue="Критический сервис. Изменения согласуются с владельцем."
            />
          </Field>
          <Button variant="primary" onClick={() => setDrawer(false)}>
            Сохранить
          </Button>
        </div>
      </Drawer>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Удалить сервер?"
        description="Запись сервера и предоставленный доступ будут удалены."
        typedText="production-api-01"
        confirmLabel="Удалить сервер"
        onConfirm={() => setConfirm(false)}
      />
    </div>
  );
}
export const DialogsAndTabs: Story = { render: () => <InteractivePatterns /> };
export const Loading: Story = {
  render: () => (
    <Panel title="Серверы">
      <Skeleton />
    </Panel>
  ),
};
export const Empty: Story = {
  render: () => (
    <Panel title="Серверы">
      <EmptyState
        title="Добавьте первый сервер"
        description="Подключите инфраструктуру для работы с SSH и мониторингом."
        action={<Button variant="primary">Добавить сервер</Button>}
      />
    </Panel>
  ),
};
export const Error: Story = {
  render: () => (
    <ErrorState
      error={
        new globalThis.Error(
          "Соединение прервано. Ваши изменения не отправлены.",
        )
      }
      retry={() => {}}
    />
  ),
};
export const LongContent: Story = {
  render: () => (
    <Panel title="Длинные технические значения">
      <DataTable
        rows={[
          {
            id: 1,
            name: "production-europe-west-primary-postgresql-replica-02.infrastructure.internal.example",
            status: "warning",
          },
          { id: 2, name: "api-gateway-01", status: "healthy" },
        ]}
        rowKey={(r) => r.id}
        searchValue={(r) => r.name}
        columns={[
          {
            key: "name",
            label: "Сервер",
            render: (r) => <span className="mono">{r.name}</span>,
          },
          {
            key: "status",
            label: "Состояние",
            render: (r) => <StatusBadge status={r.status} />,
          },
        ]}
      />
    </Panel>
  ),
};
