import { describe, expect, it } from "vitest";

import { extractAnsibleHostsHints } from "./extractAnsibleHostsHints";

describe("extractAnsibleHostsHints", () => {
  it("collects unique hosts values from YAML", () => {
    const yaml = `
- hosts: web
  tasks: []
- hosts: "db:&primary"
  tasks: []
- hosts: web
  tasks: []
`;
    expect(extractAnsibleHostsHints(yaml)).toEqual(["web", "db:&primary"]);
  });
});
