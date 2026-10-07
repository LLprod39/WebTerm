import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { isTypingTarget, usePipelineEditorHotkeys } from "./usePipelineEditorHotkeys";

describe("isTypingTarget", () => {
  it("detects input, textarea, and contenteditable", () => {
    const input = document.createElement("input");
    const textarea = document.createElement("textarea");
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(isTypingTarget(input)).toBe(true);
    expect(isTypingTarget(textarea)).toBe(true);
    expect(isTypingTarget(editable)).toBe(true);
    expect(isTypingTarget(document.createElement("button"))).toBe(false);
  });
});

describe("usePipelineEditorHotkeys", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("invokes undo/redo/save and ignores typing targets", () => {
    const undo = vi.fn();
    const redo = vi.fn();
    const onSave = vi.fn();
    renderHook(() => usePipelineEditorHotkeys({ undo, redo, onSave }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "z", ctrlKey: true }));
    expect(undo).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "z", ctrlKey: true, shiftKey: true }));
    expect(redo).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "y", metaKey: true }));
    expect(redo).toHaveBeenCalledTimes(2);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "s", ctrlKey: true }));
    expect(onSave).toHaveBeenCalledTimes(1);

    const input = document.createElement("input");
    document.body.appendChild(input);
    const typingEvent = new KeyboardEvent("keydown", { key: "z", ctrlKey: true, bubbles: true });
    Object.defineProperty(typingEvent, "target", { value: input });
    window.dispatchEvent(typingEvent);
    expect(undo).toHaveBeenCalledTimes(1);

    input.remove();
  });
});
