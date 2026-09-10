import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  ErrorState,
  Field,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { usePermission } from "@/app/session";
import { formatDate } from "@/lib/utils";
import { agentProfilesApi, type AgentProfile } from "@/api/agent-profiles";
import { intelligenceApi, type Details } from "@/api/intelligence";
import { useOperation } from "./common";
import { SharedUsers } from "./SharedUsers";
function ProfileEditor({
  profile,
  onClose,
}: {
  profile?: AgentProfile;
  onClose: () => void;
}) {
  const [name, setName] = useState(profile?.name || "");
  const [description, setDescription] = useState(profile?.description || "");
  const [system, setSystem] = useState(profile?.system_prompt || "");
  const [instructions, setInstructions] = useState(profile?.instructions || "");
  const [iterations, setIterations] = useState(profile?.max_iterations || 10);
  const [sudo, setSudo] = useState(profile?.sudo_policy || "ask");
  const [tools, setTools] = useState(profile?.allowed_tools.join("\n") || "");
  const [skills, setSkills] = useState(profile?.skill_slugs.join(", ") || "");
  const [serverIds, setServerIds] = useState(
    profile?.server_scope.map((s) => s.id) || [],
  );
  const [mcpIds, setMcpIds] = useState(
    profile?.mcp_servers.map((s) => s.id) || [],
  );
  const [sharedUsers, setSharedUsers] = useState(
    profile?.shared_user_ids || [],
  );
  const [share, setShare] = useState("unchanged");
  const canServers = usePermission("servers");
  const canMcp = usePermission("studio_mcp");
  const canSkills = usePermission("studio_skills");
  const servers = useQuery({
    queryKey: ["intelligence", "servers"],
    queryFn: intelligenceApi.servers,
    enabled: canServers,
  });
  const mcps = useQuery({
    queryKey: ["intelligence", "mcp"],
    queryFn: intelligenceApi.mcps,
    enabled: canMcp,
  });
  const op = useOperation();
  async function save(e: FormEvent) {
    e.preventDefault();
    await op.run(
      async () => {
        const data: Details = {
          name,
          description,
          system_prompt: system,
          instructions,
          max_iterations: iterations,
          sudo_policy: sudo,
          allowed_tools: tools
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
        };
        if (canSkills)
          data.skill_slugs = skills
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
        if (canServers) data.server_scope_ids = serverIds;
        if (canMcp) data.mcp_server_ids = mcpIds;
        if (profile?.can_share) data.shared_user_ids = sharedUsers;
        if (profile?.can_share && share !== "unchanged")
          data.is_shared = share === "enable";
        await agentProfilesApi.save(profile?.id, data);
      },
      "Профиль сохранён",
      onClose,
    );
  }
  return (
    <Drawer
      open
      wide
      onOpenChange={(o) => !o && !op.pending && onClose()}
      title={profile ? "Настройка профиля агента" : "Новый профиль агента"}
      description="Профиль используется AI-узлами pipelines. Область и инструменты проверяются при выполнении."
    >
      <form onSubmit={save} className="stack">
        {op.feedback}
        <Field label="Название" htmlFor="ap-name">
          <input
            id="ap-name"
            required
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Назначение" htmlFor="ap-description">
          <textarea
            id="ap-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="Системные инструкции" htmlFor="ap-system">
          <textarea
            id="ap-system"
            rows={6}
            value={system}
            onChange={(e) => setSystem(e.target.value)}
          />
        </Field>
        <Field label="Рабочие инструкции" htmlFor="ap-instructions">
          <textarea
            id="ap-instructions"
            rows={4}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </Field>
        <div className="form-grid">
          <Field label="Максимум шагов" htmlFor="ap-iterations">
            <input
              id="ap-iterations"
              required
              type="number"
              min={1}
              max={100}
              value={iterations}
              onChange={(e) => setIterations(Number(e.target.value))}
            />
          </Field>
          <Field label="Политика sudo" htmlFor="ap-sudo">
            <select
              id="ap-sudo"
              value={sudo}
              onChange={(e) => setSudo(e.target.value)}
            >
              <option value="disabled">Запрещено</option>
              <option value="ask">Запрашивать согласование</option>
              <option value="approved">Разрешено для выполнения</option>
            </select>
          </Field>
        </div>
        <Field
          label="Разрешённые инструменты"
          htmlFor="ap-tools"
          description="Точные имена инструментов, по одному на строке. Runtime дополнительно применяет политику роли."
        >
          <textarea
            id="ap-tools"
            rows={4}
            value={tools}
            onChange={(e) => setTools(e.target.value)}
            className="mono"
          />
        </Field>
        {canSkills && (
          <Field
            label="Навыки"
            htmlFor="ap-skills"
            description="Идентификаторы навыков через запятую."
          >
            <input
              id="ap-skills"
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
            />
          </Field>
        )}
        {canServers && (
          <Field label="Область серверов">
            <div className="intel-checkbox-list">
              {servers.isPending ? (
                <LoadingState />
              ) : servers.error ? (
                <ErrorState error={servers.error} />
              ) : (
                servers.data?.servers
                  .filter((s) => s.can_edit)
                  .map((s) => (
                    <label key={s.id}>
                      <input
                        type="checkbox"
                        checked={serverIds.includes(s.id)}
                        onChange={(e) =>
                          setServerIds(
                            e.target.checked
                              ? [...serverIds, s.id]
                              : serverIds.filter((id) => id !== s.id),
                          )
                        }
                      />
                      {s.name}
                    </label>
                  ))
              )}
            </div>
          </Field>
        )}
        {canMcp && (
          <Field label="MCP-подключения">
            <div className="intel-checkbox-list">
              {mcps.isPending ? (
                <LoadingState />
              ) : mcps.error ? (
                <ErrorState error={mcps.error} />
              ) : (
                mcps.data?.map((m) => (
                  <label key={m.id}>
                    <input
                      type="checkbox"
                      checked={mcpIds.includes(m.id)}
                      onChange={(e) =>
                        setMcpIds(
                          e.target.checked
                            ? [...mcpIds, m.id]
                            : mcpIds.filter((id) => id !== m.id),
                        )
                      }
                    />
                    {m.name}
                  </label>
                ))
              )}
            </div>
          </Field>
        )}
        {profile?.can_share && (
          <Field
            label="Общий доступ"
            htmlFor="ap-share"
            description="Персональные назначения сохраняются отдельно."
          >
            <select
              id="ap-share"
              value={share}
              onChange={(e) => setShare(e.target.value)}
            >
              <option value="unchanged">Оставить без изменений</option>
              <option value="enable">Включить общий доступ</option>
              <option value="disable">Отключить общий доступ</option>
            </select>
          </Field>
        )}
        {profile?.can_share && (
          <SharedUsers ids={sharedUsers} onChange={setSharedUsers} />
        )}
        <p className="muted">
          Модель и подключение AI управляются политикой организации в настройках
          AI.
        </p>
        <div className="row">
          <Button onClick={onClose} disabled={op.pending}>
            Отмена
          </Button>
          <Button variant="primary" type="submit" loading={op.pending}>
            Сохранить профиль
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
export function ProfilesPage() {
  const [editor, setEditor] = useState<AgentProfile | null | undefined>();
  const [remove, setRemove] = useState<AgentProfile>();
  const q = useQuery({
    queryKey: ["intelligence", "agent-profiles"],
    queryFn: agentProfilesApi.list,
  });
  const op = useOperation();
  return (
    <>
      <PageHeader
        eyebrow="Интеллект · Автоматизация"
        title="Профили агентов"
        description="Инструкции, навыки и область доступа для AI-узлов pipelines."
        actions={
          <Button variant="primary" onClick={() => setEditor(null)}>
            Создать профиль
          </Button>
        }
      />
      {op.feedback}
      <p className="muted">
        Профиль можно выбрать в{" "}
        <Link to="/automation/pipelines">редакторе pipeline</Link>.
      </p>
      <Panel title="Профили">
        {q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : (
          <DataTable
            rows={q.data || []}
            rowKey={(r) => r.id}
            searchValue={(r) => `${r.name} ${r.description}`}
            emptyTitle="Профилей пока нет"
            emptyDescription="Создайте профиль для повторяемой роли: анализа, диагностики или проверки результата."
            columns={[
              {
                key: "name",
                label: "Профиль",
                render: (r) => (
                  <>
                    <strong>{r.name}</strong>
                    <p className="muted">{r.description}</p>
                  </>
                ),
              },
              {
                key: "owner",
                label: "Владелец",
                render: (r) => r.owner_username,
              },
              {
                key: "scope",
                label: "Область",
                render: (r) =>
                  r.server_scope.map((s) => s.name).join(", ") ||
                  "Серверы не назначены",
              },
              {
                key: "skills",
                label: "Навыки",
                render: (r) => (
                  <>
                    {r.skill_slugs.join(", ") || "—"}
                    {r.skill_errors.length > 0 && (
                      <p className="text-danger">{r.skill_errors.join("; ")}</p>
                    )}
                  </>
                ),
              },
              {
                key: "date",
                label: "Обновлён",
                render: (r) => formatDate(r.updated_at),
              },
              {
                key: "actions",
                label: "",
                render: (r) =>
                  r.can_edit ? (
                    <div className="row">
                      <Button size="sm" onClick={() => setEditor(r)}>
                        Настроить
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setRemove(r)}
                      >
                        Удалить
                      </Button>
                    </div>
                  ) : (
                    <span className="muted">Только чтение</span>
                  ),
              },
            ]}
          />
        )}
      </Panel>
      {editor !== undefined && (
        <ProfileEditor
          profile={editor || undefined}
          onClose={() => setEditor(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(o) => !o && setRemove(undefined)}
        title="Удалить профиль агента?"
        description={`AI-узлы, использующие «${remove?.name}», могут потребовать перенастройки.`}
        typedText={remove?.name}
        pending={op.pending}
        onConfirm={() =>
          remove &&
          void op.run(
            () => agentProfilesApi.remove(remove.id),
            "Профиль удалён",
            () => setRemove(undefined),
          )
        }
      />
    </>
  );
}
