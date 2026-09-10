import { existsSync, realpathSync } from "node:fs";
import { isAbsolute, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

// Storybook 10 normalizes cross-drive static paths as ./D:/..., which is invalid
// on Windows. Keep assets inside node_modules on the project's junction path.
// This preset does not change dependency resolution or copy any installed files.
export function staticDirs(entries = []) {
  if (process.platform !== "win32") return entries;

  const localModules = fileURLToPath(
    new URL("../node_modules/", import.meta.url),
  );
  const realModules = realpathSync(localModules);
  if (
    parse(localModules).root.toLowerCase() ===
    parse(realModules).root.toLowerCase()
  ) {
    return entries;
  }

  return entries.map((entry) => {
    if (typeof entry !== "object" || !entry || !isAbsolute(entry.from))
      return entry;

    const suffix = relative(realModules, entry.from);
    if (isAbsolute(suffix) || suffix === ".." || suffix.startsWith(`..${sep}`))
      return entry;

    const localFrom = resolve(localModules, suffix);
    return existsSync(localFrom) ? { ...entry, from: localFrom } : entry;
  });
}
