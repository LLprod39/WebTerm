// Poll counter driving the simulated live playbook run in demo mode.
let demoPlaybookRunPolls = 0;

/** Playbooks demo fallbacks (templates, runs, inventory, CRUD). */
export function demoPlaybooksFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  if (path.includes("/servers/api/playbooks/ansible/status")) {
    return {
      success: true,
      ansible: {
        available: true,
        method: "demo",
        binary: "ansible-playbook",
        version: "ansible-core 2.17 (demo)",
        message: "Demo mode",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/guided/generate")) {
    return {
      success: true,
      playbook: {
        id: 9,
        name: "Guided demo",
        description: "demo",
        kind: "ansible",
        category: "custom",
        visibility: "private",
        tags: ["guided"],
        fidelity: { engine: "ansible", score: 1 },
        task_count: 1,
        is_template_clone: true,
        template_slug: "guided:demo",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "uptime", description: "up", continue_on_error: false }],
        source_yaml: "- name: demo\n  hosts: all\n  tasks: []\n",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/guided")) {
    return {
      success: true,
      recipes: [
        {
          slug: "health-check",
          name: "Health check",
          description: "Demo recipe",
          category: "diagnose",
          icon: "heart",
          fields: [],
        },
      ],
    } as T;
  }
  if (path.includes("/servers/api/playbooks/templates/") && path.includes("/install/")) {
    return {
      success: true,
      playbook: {
        id: 1,
        name: "Health snapshot",
        description: "Demo template",
        kind: "runbook",
        category: "diagnose",
        visibility: "private",
        tags: ["health"],
        fidelity: {},
        task_count: 2,
        is_template_clone: true,
        template_slug: "health-snapshot",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [
          { id: "t1", command: "uptime", description: "Uptime", continue_on_error: false },
          { id: "t2", command: "df -h", description: "Disk", continue_on_error: false },
        ],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/templates")) {
    return {
      success: true,
      templates: [
        {
          slug: "health-snapshot",
          name: "Health snapshot",
          description: "Uptime, load, disk, memory",
          kind: "runbook",
          category: "diagnose",
          tags: ["health"],
          task_count: 5,
          tasks_preview: [{ description: "Uptime", command: "uptime" }],
        },
      ],
    } as T;
  }
  if (path.includes("/servers/api/playbooks/runs/") && path.includes("/cancel/")) {
    demoPlaybookRunPolls = 99;
    return { success: true, run: { id: 1, status: "cancelled", playbook_name: "Demo", host_results: [], summary: {} } } as T;
  }
  if (path.includes("/servers/api/playbooks/runs/") && path.includes("/rerun-failed/")) {
    demoPlaybookRunPolls = 0;
    return { success: true, run: { id: 2, status: "pending", playbook_name: "Demo", host_results: [], summary: {} } } as T;
  }
  if (path.includes("/servers/api/playbooks/runs/")) {
    // Simulate a live run: first polls stream progress, then the run completes.
    demoPlaybookRunPolls += 1;
    const step = Math.min(demoPlaybookRunPolls, 5);
    const live = step < 5;
    const logAll = [
      "PLAY [Health snapshot] *********************************************************",
      "",
      "TASK [Gathering Facts] *********************************************************",
      "ok: [demo-linux]",
      "",
      "TASK [Uptime] ******************************************************************",
      "changed: [demo-linux]",
      "",
      "TASK [Disk] ********************************************************************",
      "changed: [demo-linux]",
      "",
      "PLAY RECAP *********************************************************************",
      "demo-linux                 : ok=3    changed=2    unreachable=0    failed=0    skipped=0",
    ];
    const logCut = [4, 7, 10, 13, logAll.length][step - 1] ?? logAll.length;
    const taskNames = ["Gathering Facts", "Uptime", "Disk", "Disk", ""];
    const statusFor = (n: number) => (step > n ? "success" : step === n ? "running" : "pending");
    return {
      success: true,
      run: {
        id: 1,
        playbook_id: 1,
        status: live ? "running" : "completed",
        playbook_name: "Health snapshot",
        target_server_ids: [1],
        target_group_ids: [],
        options: { concurrency: 2, dry_run: false },
        summary: live
          ? {}
          : { hosts_total: 1, hosts_ok: 1, hosts_failed: 0, tasks_ok: 3, tasks_failed: 0, tasks_skipped: 0, engine: "ansible", ansible_method: "demo" },
        progress: {
          engine: "ansible",
          play: "Health snapshot",
          task: taskNames[step - 1],
          task_number: Math.min(step, 3),
          tasks_total: 3,
          hosts_total: 1,
          counts: { ok: Math.min(step, 3), changed: Math.max(0, Math.min(step, 3) - 1), failed: 0, skipped: 0, unreachable: 0 },
          finished: !live,
        },
        live_log: logAll.slice(0, logCut).join("\n"),
        inventory_preview: "[all]\ndemo ansible_host=10.0.0.1",
        error_message: "",
        cancel_requested: false,
        started_at: new Date(Date.now() - step * 1200).toISOString(),
        finished_at: live ? null : new Date().toISOString(),
        created_at: new Date(Date.now() - step * 1200).toISOString(),
        host_results: [
          {
            server_id: 1,
            server_name: "demo-linux",
            host: "10.0.0.1",
            status: live ? "running" : "success",
            task_results: [
              { task_id: "t0", command: "Gathering Facts", description: "Gathering Facts", status: statusFor(1), output: "", exit_code: 0 },
              { task_id: "t1", command: "uptime", description: "Uptime", status: statusFor(2), output: step > 2 ? "up 3 days, load 0.42" : "", exit_code: 0 },
              { task_id: "t2", command: "df -h", description: "Disk", status: statusFor(3), output: step > 3 ? "/ 40% used" : "", exit_code: 0 },
            ],
          },
        ],
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/runs")) {
    return { success: true, runs: [] } as T;
  }
  if (path.includes("/servers/api/playbooks/inventory/preview")) {
    return {
      success: true,
      inventory: "[all]\ndemo ansible_host=10.0.0.1\n",
      hosts: [{ id: 1, name: "demo-linux", host: "10.0.0.1", port: 22, username: "root", group_id: null, detected_os: "ubuntu" }],
      count: 1,
    } as T;
  }
  if (path.includes("/servers/api/playbooks/import")) {
    return {
      success: true,
      playbook: {
        id: 2,
        name: "Imported",
        description: "hosts: all",
        kind: "ansible",
        category: "custom",
        visibility: "private",
        tags: ["imported"],
        fidelity: { runnable: 1, total: 1, score: 1, unsupported_modules: [] },
        task_count: 1,
        is_template_clone: false,
        template_slug: "",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "echo ok", description: "demo", continue_on_error: false }],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/") && path.includes("/run/")) {
    demoPlaybookRunPolls = 0;
    return {
      success: true,
      run: {
        id: 1,
        playbook_id: 1,
        status: "running",
        playbook_name: "Demo",
        target_server_ids: [1],
        target_group_ids: [],
        options: {},
        summary: {},
        inventory_preview: "",
        error_message: "",
        cancel_requested: false,
        started_at: new Date().toISOString(),
        finished_at: null,
        created_at: new Date().toISOString(),
        host_results: [],
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/") && (path.includes("/update/") || path.includes("/duplicate/") || path.includes("/create/"))) {
    return {
      success: true,
      playbook: {
        id: 1,
        name: "Demo playbook",
        description: "",
        kind: "runbook",
        category: "custom",
        visibility: "private",
        tags: [],
        fidelity: {},
        task_count: 1,
        is_template_clone: false,
        template_slug: "",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "uptime", description: "", continue_on_error: false }],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/") && path.includes("/delete/")) {
    return { success: true } as T;
  }
  if (path.match(/\/servers\/api\/playbooks\/\d+\/?$/)) {
    return {
      success: true,
      playbook: {
        id: 1,
        name: "Demo playbook",
        description: "Demo mode",
        kind: "runbook",
        category: "diagnose",
        visibility: "private",
        tags: ["demo"],
        fidelity: {},
        task_count: 1,
        is_template_clone: false,
        template_slug: "",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "uptime", description: "Uptime", continue_on_error: false }],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks")) {
    return { success: true, playbooks: [], count: 0 } as T;
  }
  return undefined;
}
