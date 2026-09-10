import test from "node:test";
import assert from "node:assert/strict";
import { get } from "node:http";
import { preview } from "vite";

test("production preview accepts the configured corporate host and rejects unknown hosts", async () => {
  const previous = process.env.WEBTERM_FRONTEND_ALLOWED_HOSTS;
  process.env.WEBTERM_FRONTEND_ALLOWED_HOSTS = "qa.webterm.invalid,*";
  const server = await preview({
    logLevel: "silent",
    preview: { host: "127.0.0.1", port: 0, strictPort: true },
  });
  const port = server.httpServer.address().port;
  const status = (host) =>
    new Promise((resolve, reject) => {
      get(
        { hostname: "127.0.0.1", port, path: "/", headers: { Host: host } },
        (response) => {
          response.resume();
          response.once("end", () => resolve(response.statusCode));
        },
      ).once("error", reject);
    });
  try {
    assert.equal(await status("qa.webterm.invalid"), 200);
    assert.equal(await status("untrusted.webterm.invalid"), 403);
    assert.equal(await status("localhost"), 200);
  } finally {
    await new Promise((resolve, reject) =>
      server.httpServer.close((error) => (error ? reject(error) : resolve())),
    );
    if (previous === undefined)
      delete process.env.WEBTERM_FRONTEND_ALLOWED_HOSTS;
    else process.env.WEBTERM_FRONTEND_ALLOWED_HOSTS = previous;
  }
});
