import yaml from "js-yaml";

import type { Playbook, PlaybookTask } from "./types";

export function loadPlaybooks(): Playbook[] {
  try {
    const raw = localStorage.getItem("weu_playbooks");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function savePlaybooks(playbooks: Playbook[]) {
  localStorage.setItem("weu_playbooks", JSON.stringify(playbooks));
}

export function newTaskId() {
  return `t_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export function newPlaybookId() {
  return `pb_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

/** Parse Ansible playbook (YAML or JSON) into our Playbook format */
export function parseAnsiblePlaybook(content: string, filename: string): Playbook {
  // Try YAML first, then JSON
  let parsed: unknown;
  try {
    parsed = yaml.load(content);
  } catch {
    parsed = JSON.parse(content);
  }

  const tasks: PlaybookTask[] = [];
  let playbookName = filename.replace(/\.(ya?ml|json)$/i, "");
  let playbookDesc = "";

  // Ansible playbooks are arrays of plays
  const plays = Array.isArray(parsed) ? parsed : [parsed];

  for (const play of plays) {
    if (!play || typeof play !== "object") continue;
    const p = play as Record<string, unknown>;

    if (p.name && typeof p.name === "string" && !playbookDesc) {
      playbookName = p.name;
    }
    if (p.hosts && typeof p.hosts === "string") {
      playbookDesc = `hosts: ${p.hosts}`;
    }

    // Extract tasks from "tasks", "pre_tasks", "post_tasks", "handlers"
    for (const section of ["pre_tasks", "tasks", "post_tasks", "handlers"]) {
      const sectionTasks = (p as Record<string, unknown>)[section];
      if (!Array.isArray(sectionTasks)) continue;

      for (const task of sectionTasks) {
        if (!task || typeof task !== "object") continue;
        const t = task as Record<string, unknown>;
        const taskName = (t.name as string) || "";
        let command = "";
        const continueOnError = Boolean(t.ignore_errors);

        // Extract command from common Ansible modules
        if (typeof t.shell === "string") {
          command = t.shell;
        } else if (typeof t.command === "string") {
          command = t.command;
        } else if (typeof t.raw === "string") {
          command = t.raw;
        } else if (typeof t.script === "string") {
          command = t.script;
        } else if (t.shell && typeof t.shell === "object") {
          command = (t.shell as Record<string, unknown>).cmd as string || "";
        } else if (t.command && typeof t.command === "object") {
          command = (t.command as Record<string, unknown>).cmd as string || "";
        } else if (typeof t.apt === "object" || typeof t.apt === "string") {
          const apt = typeof t.apt === "string" ? { name: t.apt } : t.apt as Record<string, unknown>;
          const pkg = apt.name || apt.pkg || "";
          const state = apt.state || "present";
          command = `apt-get ${state === "absent" ? "remove" : "install"} -y ${pkg}`;
        } else if (typeof t.yum === "object" || typeof t.yum === "string") {
          const yum = typeof t.yum === "string" ? { name: t.yum } : t.yum as Record<string, unknown>;
          const pkg = yum.name || "";
          const state = yum.state || "present";
          command = `yum ${state === "absent" ? "remove" : "install"} -y ${pkg}`;
        } else if (typeof t.systemd === "object" || typeof t.service === "object") {
          const svc = (t.systemd || t.service) as Record<string, unknown>;
          const name = svc.name || "";
          const state = svc.state || "started";
          const stateMap: Record<string, string> = { started: "start", stopped: "stop", restarted: "restart", reloaded: "reload" };
          command = `systemctl ${stateMap[state as string] || state} ${name}`;
          if (svc.enabled === true) command += ` && systemctl enable ${name}`;
        } else if (typeof t.copy === "object") {
          const cp = t.copy as Record<string, unknown>;
          if (cp.content && cp.dest) {
            const escaped = String(cp.content).replace(/'/g, "'\\''");
            command = `echo '${escaped}' > ${cp.dest}`;
          } else if (cp.src && cp.dest) {
            command = `cp ${cp.src} ${cp.dest}`;
          }
        } else if (typeof t.file === "object") {
          const f = t.file as Record<string, unknown>;
          if (f.state === "directory") command = `mkdir -p ${f.path || f.dest || ""}`;
          else if (f.state === "absent") command = `rm -rf ${f.path || f.dest || ""}`;
          else if (f.mode) command = `chmod ${f.mode} ${f.path || f.dest || ""}`;
        } else if (typeof t.lineinfile === "object") {
          const l = t.lineinfile as Record<string, unknown>;
          command = `# lineinfile: ${l.path || l.dest || ""} line="${l.line || ""}"`;
        } else if (typeof t.template === "object") {
          const tmpl = t.template as Record<string, unknown>;
          command = `# template: ${tmpl.src} -> ${tmpl.dest}`;
        } else if (typeof t.git === "object") {
          const g = t.git as Record<string, unknown>;
          command = `git clone ${g.repo || ""} ${g.dest || ""}${g.version ? ` -b ${g.version}` : ""}`;
        } else if (typeof t.pip === "object") {
          const pip = t.pip as Record<string, unknown>;
          command = `pip install ${pip.name || ""}${pip.requirements ? ` -r ${pip.requirements}` : ""}`;
        } else if (typeof t.docker_container === "object") {
          const dc = t.docker_container as Record<string, unknown>;
          command = `# docker: ${dc.name} image=${dc.image || ""} state=${dc.state || "started"}`;
        } else {
          // Unknown module — show as comment with module name
          const moduleKeys = Object.keys(t).filter((k) => !["name", "when", "register", "become", "become_user", "tags", "notify", "ignore_errors", "changed_when", "failed_when", "loop", "with_items", "vars", "environment", "no_log", "delegate_to", "run_once", "block", "rescue", "always"].includes(k));
          if (moduleKeys.length > 0) {
            const mod = moduleKeys[0];
            const val = t[mod];
            command = `# ansible.${mod}: ${typeof val === "string" ? val : JSON.stringify(val)}`;
          }
        }

        if (command || taskName) {
          tasks.push({
            id: newTaskId(),
            command: command || `# ${taskName}`,
            description: taskName,
            continueOnError,
          });
        }
      }
    }
  }

  if (tasks.length === 0) {
    throw new Error("No tasks found in playbook. Ensure it contains tasks with shell/command/apt/systemd modules.");
  }

  return {
    id: newPlaybookId(),
    name: playbookName,
    description: playbookDesc,
    tasks,
    createdAt: new Date().toISOString(),
  };
}

/** Export playbook to JSON */
export function exportPlaybookAsJson(pb: Playbook) {
  const ansible = [{
    name: pb.name,
    hosts: "all",
    become: true,
    tasks: pb.tasks.map((t) => {
      const task: Record<string, unknown> = { name: t.description || t.command };
      if (t.command.startsWith("#")) {
        task.debug = { msg: t.command };
      } else {
        task.shell = t.command;
      }
      if (t.continueOnError) task.ignore_errors = true;
      return task;
    }),
  }];
  const blob = new Blob([JSON.stringify(ansible, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${pb.name.replace(/\s+/g, "_").toLowerCase()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
