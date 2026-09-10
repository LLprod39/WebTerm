import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import {
  hasPendingProjectChanges,
  hasUnsavedProjectChanges,
  useUnsavedProjectChange,
} from "./unsaved-project-change";

afterEach(cleanup);

it("keeps the draft protected through repeated cancelled attempts until saved", () => {
  const hook = renderHook(({ dirty }) => useUnsavedProjectChange(dirty), {
    initialProps: { dirty: false },
  });
  expect(hasUnsavedProjectChanges()).toBe(false);
  hook.rerender({ dirty: true });
  expect(hasUnsavedProjectChanges()).toBe(true);
  expect(hasUnsavedProjectChanges()).toBe(true);
  hook.rerender({ dirty: false });
  expect(hasUnsavedProjectChanges()).toBe(false);
});

it("a clean or unmounted page cannot remove another page's draft protection", () => {
  const first = renderHook(() => useUnsavedProjectChange(true));
  const second = renderHook(({ dirty }) => useUnsavedProjectChange(dirty), {
    initialProps: { dirty: false },
  });
  expect(hasUnsavedProjectChanges()).toBe(true);
  second.rerender({ dirty: true });
  first.unmount();
  expect(hasUnsavedProjectChanges()).toBe(true);
  second.unmount();
  expect(hasUnsavedProjectChanges()).toBe(false);
});

it("protects an active save independently of dirty state and releases it on completion or unmount", () => {
  const hook = renderHook(
    ({ dirty, pending }) => useUnsavedProjectChange(dirty, pending),
    { initialProps: { dirty: false, pending: true } },
  );
  expect(hasPendingProjectChanges()).toBe(true);
  expect(hasUnsavedProjectChanges()).toBe(false);
  hook.rerender({ dirty: true, pending: false });
  expect(hasPendingProjectChanges()).toBe(false);
  expect(hasUnsavedProjectChanges()).toBe(true);
  hook.rerender({ dirty: true, pending: true });
  expect(hasPendingProjectChanges()).toBe(true);
  hook.unmount();
  expect(hasPendingProjectChanges()).toBe(false);
  expect(hasUnsavedProjectChanges()).toBe(false);
});
