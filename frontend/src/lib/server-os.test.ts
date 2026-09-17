import { describe, expect, it } from "vitest";



import { inferServerOs, resolveServerOs } from "@/lib/server-os";



describe("inferServerOs", () => {

  it("defaults generic SSH to unknown", () => {

    expect(inferServerOs({ server_type: "ssh", name: "app-01", host: "10.0.0.1" })).toBe("unknown");

  });

  it("prefers backend detected_os over heuristics", () => {

    expect(

      resolveServerOs({

        server_type: "ssh",

        name: "app-01",

        host: "10.0.0.1",

        detected_os: "debian",

      }),

    ).toBe("debian");

  });



  it("detects linux distros from tags, notes, and username", () => {

    expect(inferServerOs({ server_type: "ssh", tags: "ubuntu,prod" })).toBe("ubuntu");

    expect(inferServerOs({ server_type: "ssh", notes: "Debian 12 bookworm" })).toBe("debian");

    expect(inferServerOs({ server_type: "ssh", name: "centos-legacy" })).toBe("centos");

    expect(inferServerOs({ server_type: "ssh", username: "ubuntu", host: "10.0.0.2" })).toBe("ubuntu");

    expect(inferServerOs({ server_type: "ssh", tags: "rhel,prod" })).toBe("rhel");

    expect(inferServerOs({ server_type: "ssh", notes: "Rocky Linux 9" })).toBe("rocky");

    expect(inferServerOs({ server_type: "ssh", name: "amzn-prod" })).toBe("amazon");

  });



  it("detects macOS, kubernetes, and docker hints", () => {

    expect(inferServerOs({ server_type: "ssh", notes: "macOS jump host" })).toBe("macos");

    expect(inferServerOs({ server_type: "ssh", name: "k8s-worker" })).toBe("kubernetes");

    expect(inferServerOs({ server_type: "ssh", tags: "docker,swarm" })).toBe("docker");

  });



  it("detects windows from text on SSH servers", () => {

    expect(inferServerOs({ server_type: "ssh", name: "win-dc", notes: "Windows Server 2022" })).toBe("windows");

  });

});


