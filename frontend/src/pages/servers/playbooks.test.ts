import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  loadPlaybooks,
  parseAnsiblePlaybook,
  savePlaybooks,
} from "./playbooks";

describe("legacy playbook helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips browser playbooks", () => {
    const playbook = parseAnsiblePlaybook(`
- name: Read-only health check
  hosts: pilot
  tasks:
    - name: Show uptime
      command: uptime
`, "health.yml");

    savePlaybooks([playbook]);

    expect(loadPlaybooks()).toEqual([playbook]);
    expect(playbook.name).toBe("Read-only health check");
    expect(playbook.tasks[0]?.command).toBe("uptime");
  });

  it("returns an empty list for corrupted local storage", () => {
    localStorage.setItem("weu_playbooks", "not-json");
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(loadPlaybooks()).toEqual([]);

    errorSpy.mockRestore();
  });
});
