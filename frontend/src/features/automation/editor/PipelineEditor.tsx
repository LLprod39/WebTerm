import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlowProvider,
  addEdge,
  useReactFlow,
  type Connection,
  type Edge,
} from "@xyflow/react";
import { Play, ShieldCheck } from "lucide-react";
import { api } from "@/api/client";
import {
  automationApi,
  studioBase,
  type NodeManifest,
  type Pipeline,
  type Values,
} from "@/api/automation";
import { usePermission } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  Drawer,
  Feedback,
  Field,
} from "@/components/ui";
import { downloadText } from "@/lib/utils";
import { KeyValues, ValidationResult } from "../shared";
import { useUnsavedEdits } from "../unsaved";
import { pipelineValidationError } from "../validation";
import {
  buildNode,
  duplicateNode,
  fromCanvas,
  graphSignature,
  insertBetween,
  layoutHorizontal,
  looksVertical,
  nextNodePosition,
  nodeIssues,
  toCanvas,
  type CanvasNode,
} from "../graph";
import { EditorTopBar } from "./EditorTopBar";
import { FlowCanvas } from "./FlowCanvas";
import { NodePicker, type PickerPending } from "./NodePicker";
import { NodeSettings } from "./NodeSettings";
import { ContextMenu, type ContextTarget } from "./ContextMenu";
import { useHistory } from "./useHistory";
import {
  DEFAULT_EDGE_OPTIONS,
  type StepEdgeData,
} from "./edges/StepEdge";
import "./editor.css";

type SettingsMode = "node" | "process" | null;

function decorateNodes(
  nodes: CanvasNode[],
  edges: Edge[],
  manifests: NodeManifest[],
  actions: NonNullable<CanvasNode["data"]["actions"]>,
): CanvasNode[] {
  const connected = new Map<string, string[]>();
  for (const edge of edges) {
    const handle = edge.sourceHandle || "out";
    connected.set(edge.source, [
      ...(connected.get(edge.source) ?? []),
      handle,
    ]);
  }
  return nodes.map((node) => {
    const manifest = manifests.find((m) => m.type === node.data.backend.type);
    return {
      ...node,
      data: {
        ...node.data,
        connectedHandles: [...new Set(connected.get(node.id) ?? [])],
        issueCount: nodeIssues(node, manifest).length,
        actions,
      },
    };
  });
}

function PipelineEditorInner({
  pipeline,
  manifests,
}: {
  pipeline: Pipeline;
  manifests: NodeManifest[];
}) {
  const initialNodes = useMemo(
    () => toCanvas(pipeline.nodes ?? [], manifests),
    [pipeline.nodes, manifests],
  );
  const initialEdges = useMemo(
    () =>
      (pipeline.edges ?? []).map((edge) => ({
        ...edge,
        ...DEFAULT_EDGE_OPTIONS,
      })) as Edge<StepEdgeData>[],
    [pipeline.edges],
  );

  const history = useHistory({ nodes: initialNodes, edges: initialEdges });
  const { present, push, setPresent, undo, redo } = history;
  const nodes = present.nodes;
  const edges = present.edges as Edge<StepEdgeData>[];

  const [name, setName] = useState(pipeline.name);
  const [description, setDescription] = useState(pipeline.description);
  const [savedSignature, setSaved] = useState(() =>
    graphSignature(
      initialNodes,
      pipeline.edges ?? [],
      pipeline.name,
      pipeline.description,
    ),
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [settingsMode, setSettingsMode] = useState<SettingsMode>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pending, setPending] = useState<PickerPending>(null);
  const [showMinimap, setShowMinimap] = useState(true);
  const [layoutHint, setLayoutHint] = useState(() =>
    looksVertical(initialNodes),
  );
  const [runOpen, setRunOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [remove, setRemove] = useState(false);
  const [context, setContext] = useState<Values>({});
  const [entry, setEntry] = useState("");
  const [notice, setNotice] = useState("");
  const [menu, setMenu] = useState<{
    open: boolean;
    x: number;
    y: number;
    target: ContextTarget;
  }>({ open: false, x: 0, y: 0, target: null });
  const clipboard = useRef<CanvasNode[]>([]);
  const [canPaste, setCanPaste] = useState(false);
  const paramTimer = useRef<number | null>(null);
  const { fitView, screenToFlowPosition } = useReactFlow();
  const navigate = useNavigate();
  const client = useQueryClient();
  const canRuns = usePermission("studio_runs");
  const servers = useQuery({
    queryKey: ["automation", "studio-servers"],
    queryFn: ({ signal }) => automationApi.studioServers(signal),
  });

  const dirty =
    graphSignature(nodes, edges, name, description) !== savedSignature;
  useUnsavedEdits(dirty);

  const selectedNode = nodes.find((n) => n.id === selected);
  const selectedManifest = manifests.find(
    (m) => m.type === selectedNode?.data.backend.type,
  );
  const issues = selectedNode
    ? nodeIssues(selectedNode, selectedManifest)
    : [];
  const manual = nodes.filter(
    (n) =>
      n.data.backend.type === "trigger/manual" &&
      n.data.backend.data.is_active === true,
  );

  const payload = useCallback(
    () => ({ ...fromCanvas(nodes, edges), name, description }),
    [description, edges, name, nodes],
  );

  const save = useMutation({
    mutationFn: (body: ReturnType<typeof payload>) =>
      automationApi.savePipeline(pipeline.id, body),
    onSuccess: (_result, body) => {
      setSaved(JSON.stringify(body));
      setNotice("Процесс сохранён");
      void client.invalidateQueries({ queryKey: ["automation", "pipelines"] });
    },
  });
  const preflight = useMutation({
    mutationFn: () =>
      automationApi.preflight(pipeline.id, { context, entry_node_id: entry }),
  });
  const run = useMutation({
    mutationFn: () =>
      automationApi.runPipeline(pipeline.id, { context, entry_node_id: entry }),
    onSuccess: (result) => navigate(`/automation/runs/pipeline/${result.id}`),
  });
  const deletion = useMutation({
    mutationFn: () => api.delete(`${studioBase}pipelines/${pipeline.id}/`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["automation", "pipelines"] });
      navigate("/automation/pipelines");
    },
  });
  const clone = useMutation({
    mutationFn: () =>
      api.post<Pipeline>(`${studioBase}pipelines/${pipeline.id}/clone/`),
    onSuccess: (result) => navigate(`/automation/pipelines/${result.id}`),
  });

  const invalidate = () => {
    preflight.reset();
    save.reset();
    setNotice("");
  };

  const commit = useCallback(
    (nextNodes: CanvasNode[], nextEdges: Edge[], record = true) => {
      const snapshot = { nodes: nextNodes, edges: nextEdges };
      if (record) push(snapshot);
      else setPresent(snapshot);
      preflight.reset();
      save.reset();
      setNotice("");
    },
    [preflight, push, save, setPresent],
  );

  const openPicker = (next: PickerPending) => {
    setPending(next);
    setPickerOpen(true);
    setSettingsMode(null);
  };

  const closePicker = () => {
    setPickerOpen(false);
    setPending(null);
  };

  const deleteNode = useCallback(
    (id: string) => {
      commit(
        nodes.filter((node) => node.id !== id),
        edges.filter((edge) => edge.source !== id && edge.target !== id),
      );
      if (selected === id) {
        setSelected(null);
        setSettingsMode(null);
      }
    },
    [commit, edges, nodes, selected],
  );

  const duplicate = useCallback(
    (id: string) => {
      const source = nodes.find((node) => node.id === id);
      if (!source) return;
      const copy = duplicateNode(source, manifests);
      commit([...nodes, copy], edges);
      setSelected(copy.id);
      setSettingsMode("node");
    },
    [commit, edges, manifests, nodes],
  );

  const nodeActions = useMemo(
    () => ({
      onAddOutput: (nodeId: string, handle: string) => {
        setSelected(nodeId);
        openPicker({ kind: "output", source: nodeId, handle });
      },
      onConfigure: (nodeId: string) => {
        setSelected(nodeId);
        setSettingsMode("node");
        closePicker();
      },
      onDuplicate: (nodeId: string) => duplicate(nodeId),
      onDelete: (nodeId: string) => deleteNode(nodeId),
    }),
    [deleteNode, duplicate],
  );

  const displayNodes = useMemo(
    () => decorateNodes(nodes, edges, manifests, nodeActions),
    [nodes, edges, manifests, nodeActions],
  );

  const placeAndSelect = (manifest: NodeManifest, position: { x: number; y: number }) => {
    const created = buildNode(manifest, position);
    let nextEdges = edges;
    if (pending?.kind === "output" && !manifest.type.startsWith("trigger/")) {
      nextEdges = addEdge(
        {
          id: crypto.randomUUID(),
          source: pending.source,
          target: created.id,
          sourceHandle: pending.handle,
          ...DEFAULT_EDGE_OPTIONS,
        },
        edges,
      );
    } else if (pending?.kind === "insert" && !manifest.type.startsWith("trigger/")) {
      const mid = {
        x: position.x,
        y: position.y,
      };
      const edge = edges.find((item) => item.id === pending.edgeId);
      if (edge) {
        const sourceNode = nodes.find((node) => node.id === edge.source);
        created.position = {
          x:
            ((sourceNode?.position.x ?? 0) +
              (nodes.find((node) => node.id === edge.target)?.position.x ??
                mid.x)) /
              2,
          y: mid.y,
        };
        created.data.backend.position = created.position;
        nextEdges = insertBetween(edges, pending.edgeId, created).map(
          (item) => ({ ...item, ...DEFAULT_EDGE_OPTIONS }),
        );
      }
    } else if (
      selected &&
      !manifest.type.startsWith("trigger/") &&
      pending?.kind !== "position"
    ) {
      const source = nodes.find((node) => node.id === selected);
      nextEdges = addEdge(
        {
          id: crypto.randomUUID(),
          source: selected,
          target: created.id,
          sourceHandle: source?.data.handles[0] ?? "out",
          ...DEFAULT_EDGE_OPTIONS,
        },
        edges,
      );
    }
    commit([...nodes, created], nextEdges);
    setSelected(created.id);
    setSettingsMode("node");
    closePicker();
  };

  const onPick = (manifest: NodeManifest) => {
    if (pending?.kind === "position") {
      placeAndSelect(manifest, { x: pending.x, y: pending.y });
      return;
    }
    if (pending?.kind === "output") {
      const source = nodes.find((node) => node.id === pending.source);
      placeAndSelect(
        manifest,
        source
          ? {
              x: source.position.x + 280,
              y: source.position.y,
            }
          : nextNodePosition(nodes, selected),
      );
      return;
    }
    if (pending?.kind === "insert") {
      const edge = edges.find((item) => item.id === pending.edgeId);
      const source = nodes.find((node) => node.id === edge?.source);
      const target = nodes.find((node) => node.id === edge?.target);
      placeAndSelect(manifest, {
        x: ((source?.position.x ?? 0) + (target?.position.x ?? 280)) / 2,
        y: ((source?.position.y ?? 0) + (target?.position.y ?? 0)) / 2,
      });
      return;
    }
    placeAndSelect(manifest, nextNodePosition(nodes, selected));
  };

  const arrange = () => {
    const laid = layoutHorizontal(nodes, edges);
    commit(laid, edges);
    setLayoutHint(false);
    requestAnimationFrame(() => fitView({ padding: 0.2, duration: 280 }));
  };

  const updateNodeData = (data: Values) => {
    if (!selected) return;
    const next = nodes.map((node) =>
      node.id === selected
        ? {
            ...node,
            data: {
              ...node.data,
              backend: { ...node.data.backend, data },
            },
          }
        : node,
    );
    setPresent({ nodes: next, edges });
    invalidate();
    if (paramTimer.current) window.clearTimeout(paramTimer.current);
    paramTimer.current = window.setTimeout(() => {
      push({ nodes: next, edges });
    }, 400);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      const meta = event.ctrlKey || event.metaKey;

      if (event.key === "Escape") {
        closePicker();
        setSettingsMode(null);
        setMenu((current) => ({ ...current, open: false }));
        return;
      }
      if (typing) {
        if (meta && event.key.toLowerCase() === "s") {
          event.preventDefault();
          if (dirty && name.trim()) save.mutate(payload());
        }
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        openPicker(
          selected
            ? {
                kind: "output",
                source: selected,
                handle:
                  nodes.find((node) => node.id === selected)?.data.handles[0] ??
                  "out",
              }
            : { kind: "free" },
        );
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        if (selected) {
          event.preventDefault();
          deleteNode(selected);
        }
        return;
      }
      if (meta && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
        return;
      }
      if (meta && event.key.toLowerCase() === "y") {
        event.preventDefault();
        redo();
        return;
      }
      if (meta && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (dirty && name.trim()) save.mutate(payload());
        return;
      }
      if (meta && event.key.toLowerCase() === "d" && selected) {
        event.preventDefault();
        duplicate(selected);
        return;
      }
      if (meta && event.key.toLowerCase() === "c" && selected) {
        const node = nodes.find((item) => item.id === selected);
        if (node) {
          clipboard.current = [structuredClone(node)];
          setCanPaste(true);
        }
        return;
      }
      if (meta && event.key.toLowerCase() === "v" && clipboard.current.length) {
        event.preventDefault();
        const copies = clipboard.current.map((node) =>
          duplicateNode(node, manifests),
        );
        commit([...nodes, ...copies], edges);
        setSelected(copies[0]?.id ?? null);
        return;
      }
      if (event.shiftKey && event.altKey && event.key.toLowerCase() === "t") {
        event.preventDefault();
        const laid = layoutHorizontal(nodes, edges);
        commit(laid, edges);
        setLayoutHint(false);
        requestAnimationFrame(() => fitView({ padding: 0.2, duration: 280 }));
        return;
      }
      if (event.key.toLowerCase() === "f" && !meta) {
        event.preventDefault();
        fitView({ padding: 0.2, duration: 220 });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    commit,
    deleteNode,
    dirty,
    duplicate,
    edges,
    fitView,
    manifests,
    name,
    nodes,
    payload,
    redo,
    save,
    selected,
    undo,
  ]);

  return (
    <div className="auto-editor-page">
      <EditorTopBar
        name={name}
        dirty={dirty}
        canRuns={canRuns}
        pipelineId={pipeline.id}
        layoutHint={layoutHint}
        savePending={save.isPending}
        onName={(value) => {
          setName(value);
          invalidate();
        }}
        onSave={() => save.mutate(payload())}
        onRun={() => setRunOpen(true)}
        onAddStep={() =>
          openPicker(
            selected
              ? {
                  kind: "output",
                  source: selected,
                  handle:
                    nodes.find((node) => node.id === selected)?.data
                      .handles[0] ?? "out",
                }
              : { kind: "free" },
          )
        }
        onProcessSettings={() => {
          setSelected(null);
          setSettingsMode("process");
          closePicker();
        }}
        onLayout={arrange}
        onDownload={() =>
          downloadText(
            `${pipeline.name}.json`,
            JSON.stringify(payload(), null, 2),
            "application/json",
          )
        }
        onClone={() => clone.mutate()}
        onDelete={() => setRemove(true)}
      />

      <Feedback
        error={save.error || deletion.error || clone.error}
        success={notice}
      />
      {pipelineValidationError(save.error) && (
        <div className="auto-editor-validation">
          <ValidationResult
            value={pipelineValidationError(save.error)!}
            onNode={(nodeId) => {
              setSelected(nodeId);
              setSettingsMode("node");
            }}
          />
        </div>
      )}

      <div className="auto-editor-stage">
        <FlowCanvas
          nodes={displayNodes}
          edges={edges}
          showMinimap={showMinimap}
          onNodesChange={(next, record) => commit(next, edges, record)}
          onEdgesChange={(next, record) => commit(nodes, next, record)}
          onConnect={(connection: Connection) => {
            commit(
              nodes,
              addEdge(
                {
                  ...connection,
                  id: crypto.randomUUID(),
                  ...DEFAULT_EDGE_OPTIONS,
                },
                edges,
              ),
            );
          }}
          onConnectEndEmpty={(event, connection) => {
            if (!connection.nodeId) return;
            const point =
              "clientX" in event
                ? screenToFlowPosition({
                    x: event.clientX,
                    y: event.clientY,
                  })
                : nextNodePosition(nodes, connection.nodeId);
            openPicker({
              kind: "output",
              source: connection.nodeId,
              handle: connection.handleId || "out",
            });
            setPending({
              kind: "output",
              source: connection.nodeId,
              handle: connection.handleId || "out",
            });
            void point;
          }}
          onSelectNode={(id) => {
            setSelected(id);
            if (id) setSettingsMode("node");
          }}
          onPaneClick={() => {
            setSelected(null);
            if (!pickerOpen) setSettingsMode(null);
          }}
          onDropType={(type, position) => {
            const manifest = manifests.find((item) => item.type === type);
            if (!manifest) return;
            setPending({ kind: "position", ...position });
            placeAndSelect(manifest, position);
          }}
          onLayout={arrange}
          onToggleMinimap={() => setShowMinimap((value) => !value)}
          onContextMenu={(target, x, y) =>
            setMenu({ open: true, x, y, target })
          }
          onInsertEdge={(edgeId) =>
            openPicker({ kind: "insert", edgeId })
          }
          onDeleteEdge={(edgeId) =>
            commit(
              nodes,
              edges.filter((edge) => edge.id !== edgeId),
            )
          }
        />

        <NodePicker
          key={`${pickerOpen}-${pending?.kind ?? "none"}-${pending && "source" in pending ? pending.source : ""}-${pending && "edgeId" in pending ? pending.edgeId : ""}`}
          open={pickerOpen}
          manifests={manifests}
          pending={pending}
          onClose={closePicker}
          onPick={onPick}
        />
        <NodeSettings
          mode={settingsMode}
          node={selectedNode}
          manifest={selectedManifest}
          servers={servers.data ?? []}
          issues={issues}
          name={name}
          description={description}
          onName={(value) => {
            setName(value);
            invalidate();
          }}
          onDescription={(value) => {
            setDescription(value);
            invalidate();
          }}
          onChange={updateNodeData}
          onDelete={() => selected && deleteNode(selected)}
          onClose={() => setSettingsMode(null)}
        />
      </div>

      <ContextMenu
        open={menu.open}
        x={menu.x}
        y={menu.y}
        target={menu.target}
        onOpenChange={(open) => setMenu((current) => ({ ...current, open }))}
        onConfigure={(id) => {
          setSelected(id);
          setSettingsMode("node");
        }}
        onDuplicate={duplicate}
        onDeleteNode={deleteNode}
        onInsert={(edgeId) => openPicker({ kind: "insert", edgeId })}
        onDeleteEdge={(edgeId) =>
          commit(
            nodes,
            edges.filter((edge) => edge.id !== edgeId),
          )
        }
        onAddHere={(x, y) => openPicker({ kind: "position", x, y })}
        onLayout={arrange}
        onSelectAll={() =>
          setPresent({
            nodes: nodes.map((node) => ({ ...node, selected: true })),
            edges,
          })
        }
        onPaste={() => {
          if (!clipboard.current.length) return;
          const copies = clipboard.current.map((node) =>
            duplicateNode(node, manifests),
          );
          commit([...nodes, ...copies], edges);
        }}
        canPaste={canPaste}
      />

      <Drawer
        open={runOpen}
        onOpenChange={setRunOpen}
        title="Проверка и запуск процесса"
      >
        <div className="auto-form">
          <Field label="Ручной триггер" htmlFor="pipeline-entry">
            <select
              id="pipeline-entry"
              value={entry}
              onChange={(event) => {
                setEntry(event.target.value);
                preflight.reset();
              }}
            >
              <option value="">
                {manual.length === 1
                  ? "Единственный активный триггер"
                  : "Выберите триггер"}
              </option>
              {manual.map((node) => (
                <option key={node.id} value={node.id}>
                  {String(node.data.backend.data.label || node.id)}
                </option>
              ))}
            </select>
          </Field>
          {manual.length === 0 && (
            <p className="notice notice-warning">
              Включите ручной триггер в редакторе и сохраните процесс.
            </p>
          )}
          <KeyValues
            label="Контекст запуска"
            value={context}
            onChange={(value) => {
              setContext(value);
              preflight.reset();
            }}
          />
          <Feedback error={preflight.error || run.error} />
          {preflight.data && (
            <>
              <ValidationResult
                value={preflight.data.validation}
                onNode={(nodeId) => {
                  setSelected(nodeId);
                  setSettingsMode("node");
                  setRunOpen(false);
                }}
              />
              <p className="auto-muted">{preflight.data.dry_run.message}</p>
              {preflight.data.risk.level === "dangerous" && (
                <p className="notice notice-warning">
                  Процесс содержит опасные действия. Добавьте согласование или
                  измените команды перед запуском.
                </p>
              )}
            </>
          )}
          <Button
            loading={preflight.isPending}
            disabled={
              dirty || manual.length === 0 || (manual.length > 1 && !entry)
            }
            onClick={() => preflight.mutate()}
          >
            <ShieldCheck size={15} />
            Проверить готовность
          </Button>
          <Button
            variant="primary"
            disabled={
              !preflight.data?.ok ||
              preflight.data.risk.level === "dangerous" ||
              dirty
            }
            loading={run.isPending}
            onClick={() => setConfirm(true)}
          >
            <Play size={15} />
            Запустить процесс
          </Button>
        </div>
      </Drawer>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Выполнить рабочий процесс?"
        description={`Будут выполнены шаги процесса «${name}». Проверка готовности пройдена. Изменяющие шаги могут повлиять на инфраструктуру.`}
        onConfirm={() => run.mutate()}
        pending={run.isPending}
        confirmLabel="Запустить"
      />
      <ConfirmDialog
        open={remove}
        onOpenChange={setRemove}
        title="Удалить рабочий процесс?"
        description="Процесс, его триггеры и история запусков будут удалены."
        typedText={pipeline.name}
        onConfirm={() => deletion.mutate()}
        pending={deletion.isPending}
        confirmLabel="Удалить"
      />
    </div>
  );
}

export function PipelineEditor({
  pipeline,
  manifests,
}: {
  pipeline: Pipeline;
  manifests: NodeManifest[];
}) {
  return (
    <ReactFlowProvider>
      <PipelineEditorInner
        key={pipeline.id}
        pipeline={pipeline}
        manifests={manifests}
      />
    </ReactFlowProvider>
  );
}
